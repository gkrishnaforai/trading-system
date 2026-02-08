package services

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

type JobType string

const (
	JobTypePortfolioDataLoad JobType = "portfolio_data_load"
	JobTypePortfolioAnalysis JobType = "portfolio_analysis"
)

type DataLoadJobPayload struct {
	RunID       string   `json:"run_id"`
	PortfolioID string   `json:"portfolio_id"`
	Symbol      string   `json:"symbol"`
	DataTypes   []string `json:"data_types"`
	Force       bool     `json:"force"`
	Attempt     int      `json:"attempt"`
	MaxAttempts int      `json:"max_attempts"`
}

type PortfolioAnalysisJobPayload struct {
	RunID       string `json:"run_id"`
	PortfolioID string `json:"portfolio_id"`
	Symbol      string `json:"symbol"`
	AssetType   string `json:"asset_type"`
	TargetDate  string `json:"target_date"`
	Attempt     int    `json:"attempt"`
	MaxAttempts int    `json:"max_attempts"`
}

type DLQRequeueResult struct {
	Requested int      `json:"requested"`
	Requeued  int      `json:"requeued"`
	Deleted   int      `json:"deleted"`
	Errors    []string `json:"errors"`
}

// RequeueDLQEntries reads entries by ID from dlqKey, re-enqueues their fields to main streamKey,
// and optionally deletes the DLQ entries.
// Industry standard: requeue is "at least once"; we preserve original payload/error fields for auditability.
func (q *RedisStreamJobQueue) RequeueDLQEntries(ctx context.Context, dlqKey string, streamKey string, ids []string, deleteAfter bool) DLQRequeueResult {
	res := DLQRequeueResult{Requested: len(ids), Errors: []string{}}
	if len(ids) == 0 {
		return res
	}
	if dlqKey == "" {
		dlqKey = "ts:jobs:dlq"
	}
	if streamKey == "" {
		streamKey = q.streamKey
	}

	for _, id := range ids {
		id = strings.TrimSpace(id)
		if id == "" {
			continue
		}
		msgs, err := q.client.XRange(ctx, dlqKey, id, id).Result()
		if err != nil {
			res.Errors = append(res.Errors, fmt.Sprintf("id=%s: xrange failed: %v", id, err))
			continue
		}
		if len(msgs) == 0 {
			res.Errors = append(res.Errors, fmt.Sprintf("id=%s: not found", id))
			continue
		}
		m := msgs[0]
		if len(m.Values) == 0 {
			res.Errors = append(res.Errors, fmt.Sprintf("id=%s: tombstone/empty values", id))
			continue
		}

		vals := map[string]any{}
		for k, v := range m.Values {
			vals[k] = v
		}
		// Preserve provenance
		vals["requeued_from_dlq_id"] = id
		vals["requeued_at"] = time.Now().UTC().Format(time.RFC3339Nano)
		// Ensure main stream required fields exist
		if _, ok := vals["job_type"]; !ok {
			vals["job_type"] = string(JobTypePortfolioDataLoad)
		}
		if _, ok := vals["enqueued_at"]; !ok {
			vals["enqueued_at"] = time.Now().UTC().Format(time.RFC3339Nano)
		}
		if _, err := q.client.XAdd(ctx, &redis.XAddArgs{Stream: streamKey, Values: vals}).Result(); err != nil {
			res.Errors = append(res.Errors, fmt.Sprintf("id=%s: xadd failed: %v", id, err))
			continue
		}
		res.Requeued += 1

		if deleteAfter {
			if n, err := q.client.XDel(ctx, dlqKey, id).Result(); err != nil {
				res.Errors = append(res.Errors, fmt.Sprintf("id=%s: xdel failed: %v", id, err))
			} else {
				res.Deleted += int(n)
			}
		}
	}

	return res
}

// DeleteStreamEntries deletes message IDs from the provided stream key.
func (q *RedisStreamJobQueue) DeleteStreamEntries(ctx context.Context, key string, ids []string) DLQRequeueResult {
	res := DLQRequeueResult{Requested: len(ids), Errors: []string{}}
	if len(ids) == 0 {
		return res
	}
	if key == "" {
		res.Errors = append(res.Errors, "stream key is required")
		return res
	}
	for _, id := range ids {
		id = strings.TrimSpace(id)
		if id == "" {
			continue
		}
		n, err := q.client.XDel(ctx, key, id).Result()
		if err != nil {
			res.Errors = append(res.Errors, fmt.Sprintf("id=%s: xdel failed: %v", id, err))
			continue
		}
		res.Deleted += int(n)
	}
	return res
}

type RedisStreamJobQueue struct {
	client        *redis.Client
	streamKey     string
	remainingPref string
	hasFailPref   string
}

func (q *RedisStreamJobQueue) Client() *redis.Client {
	return q.client
}

func NewRedisStreamJobQueue(redisURL string) (*RedisStreamJobQueue, error) {
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("failed to parse redis URL: %w", err)
	}
	c := redis.NewClient(opt)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := c.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("failed to connect to redis: %w", err)
	}
	return &RedisStreamJobQueue{
		client:        c,
		streamKey:     "ts:jobs",
		remainingPref: "ts:run:remaining:",
		hasFailPref:   "ts:run:has_failures:",
	}, nil
}

func (q *RedisStreamJobQueue) Close() error {
	return q.client.Close()
}

func (q *RedisStreamJobQueue) SetRunRemaining(ctx context.Context, runID string, n int) error {
	key := q.remainingPref + runID
	return q.client.Set(ctx, key, n, 24*time.Hour).Err()
}

func (q *RedisStreamJobQueue) MarkRunHasFailures(ctx context.Context, runID string) error {
	key := q.hasFailPref + runID
	return q.client.Set(ctx, key, 1, 24*time.Hour).Err()
}

func (q *RedisStreamJobQueue) EnqueueDataLoadJob(ctx context.Context, payload DataLoadJobPayload) (string, error) {
	if payload.Attempt <= 0 {
		payload.Attempt = 1
	}
	if payload.MaxAttempts <= 0 {
		payload.MaxAttempts = 3
	}
	b, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("failed to marshal job payload: %w", err)
	}

	jobID := uuid.New().String()
	id, err := q.client.XAdd(ctx, &redis.XAddArgs{
		Stream: q.streamKey,
		MaxLen: 10000,
		Approx: true,
		Values: map[string]any{
			"job_id":      jobID,
			"job_type":    string(JobTypePortfolioDataLoad),
			"payload":     string(b),
			"enqueued_at": time.Now().UTC().Format(time.RFC3339Nano),
		},
	}).Result()
	if err != nil {
		return "", fmt.Errorf("failed to enqueue job: %w", err)
	}
	return id, nil
}

func (q *RedisStreamJobQueue) EnqueuePortfolioAnalysisJob(ctx context.Context, payload PortfolioAnalysisJobPayload) (string, error) {
	if payload.Attempt <= 0 {
		payload.Attempt = 1
	}
	if payload.MaxAttempts <= 0 {
		payload.MaxAttempts = 3
	}
	b, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("failed to marshal job payload: %w", err)
	}

	jobID := uuid.New().String()
	id, err := q.client.XAdd(ctx, &redis.XAddArgs{
		Stream: q.streamKey,
		MaxLen: 10000,
		Approx: true,
		Values: map[string]any{
			"job_id":      jobID,
			"job_type":    string(JobTypePortfolioAnalysis),
			"payload":     string(b),
			"enqueued_at": time.Now().UTC().Format(time.RFC3339Nano),
		},
	}).Result()
	if err != nil {
		return "", fmt.Errorf("failed to enqueue job: %w", err)
	}
	return id, nil
}
