package handlers

import (
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"
	"github.com/trading-system/go-api/internal/services"
)

type JobQueueAdminHandler struct {
	queue *services.RedisStreamJobQueue
}

func NewJobQueueAdminHandler(queue *services.RedisStreamJobQueue) *JobQueueAdminHandler {
	return &JobQueueAdminHandler{queue: queue}
}

type dlqRequeueRequest struct {
	DLQKey      string   `json:"dlq_key"`
	StreamKey   string   `json:"stream_key"`
	IDs         []string `json:"ids"`
	DeleteAfter bool     `json:"delete_after"`
}

// POST /api/v1/admin/job-queue/dlq/requeue
// Body: {"dlq_key":"ts:jobs:dlq","stream_key":"ts:jobs","ids":["..."],"delete_after":true}
func (h *JobQueueAdminHandler) RequeueDLQ(c *gin.Context) {
	if h.queue == nil {
		c.JSON(http.StatusOK, gin.H{
			"success": true,
			"enabled": false,
			"message": "job queue not enabled",
		})
		return
	}

	var req dlqRequeueRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "error": "invalid json body"})
		return
	}

	res := h.queue.RequeueDLQEntries(
		c.Request.Context(),
		strings.TrimSpace(req.DLQKey),
		strings.TrimSpace(req.StreamKey),
		req.IDs,
		bool(req.DeleteAfter),
	)

	c.JSON(http.StatusOK, gin.H{
		"success":   true,
		"result":    res,
		"server_ts": time.Now().UTC().Format(time.RFC3339Nano),
	})
}

type streamDeleteRequest struct {
	Key string   `json:"key"`
	IDs []string `json:"ids"`
}

// POST /api/v1/admin/job-queue/stream/delete
// Body: {"key":"ts:jobs:dlq","ids":["..."]}
func (h *JobQueueAdminHandler) DeleteStreamEntries(c *gin.Context) {
	if h.queue == nil {
		c.JSON(http.StatusOK, gin.H{
			"success": true,
			"enabled": false,
			"message": "job queue not enabled",
		})
		return
	}

	var req streamDeleteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "error": "invalid json body"})
		return
	}

	res := h.queue.DeleteStreamEntries(c.Request.Context(), strings.TrimSpace(req.Key), req.IDs)
	if len(res.Errors) > 0 && res.Deleted == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "result": res})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success":   true,
		"result":    res,
		"server_ts": time.Now().UTC().Format(time.RFC3339Nano),
	})
}

type jobQueueStreamInfo struct {
	Key              string                            `json:"key"`
	Exists           bool                              `json:"exists"`
	Length           int64                             `json:"length"`
	EntriesAdded     int64                             `json:"entries_added"`
	LastGeneratedID  string                            `json:"last_generated_id"`
	RecordedFirstID  string                            `json:"recorded_first_entry_id"`
	Groups           int64                             `json:"groups"`
	GroupsInfo       []jobQueueGroupInfo               `json:"groups_info"`
	ConsumersByGroup map[string][]jobQueueConsumerInfo `json:"consumers_by_group"`
	PendingByGroup   map[string]jobQueuePendingSummary `json:"pending_by_group"`
	RecentEntries    []jobQueueEntry                   `json:"recent_entries"`
	Error            string                            `json:"error,omitempty"`
}

type jobQueueGroupInfo struct {
	Name            string `json:"name"`
	Consumers       int64  `json:"consumers"`
	Pending         int64  `json:"pending"`
	Lag             int64  `json:"lag"`
	LastDeliveredID string `json:"last_delivered_id"`
}

type jobQueueConsumerInfo struct {
	Name     string `json:"name"`
	Pending  int64  `json:"pending"`
	IdleMS   int64  `json:"idle_ms"`
	Inactive int64  `json:"inactive"`
}

type jobQueuePendingSummary struct {
	Count     int64    `json:"count"`
	Lower     string   `json:"lower"`
	Higher    string   `json:"higher"`
	Consumers []string `json:"consumers"`
}

type jobQueueEntry struct {
	ID     string                 `json:"id"`
	Values map[string]interface{} `json:"values"`
}

// GET /api/v1/admin/job-queue/status?stream_key=ts:jobs&dlq_key=ts:jobs:dlq&group=python-workers&limit=50
func (h *JobQueueAdminHandler) GetStatus(c *gin.Context) {
	if h.queue == nil {
		c.JSON(http.StatusOK, gin.H{
			"success":   true,
			"enabled":   false,
			"message":   "job queue not enabled",
			"stream":    nil,
			"dlq":       nil,
			"server_ts": time.Now().UTC().Format(time.RFC3339Nano),
		})
		return
	}

	streamKey := c.Query("stream_key")
	if streamKey == "" {
		streamKey = "ts:jobs"
	}
	dlqKey := c.Query("dlq_key")
	if dlqKey == "" {
		dlqKey = "ts:jobs:dlq"
	}
	group := c.Query("group")
	if group == "" {
		group = "python-workers"
	}

	limit := 50
	if v := c.Query("limit"); v != "" {
		if parsed, err := parseInt(v); err == nil && parsed > 0 {
			limit = parsed
		}
	}

	client := h.queue.Client()

	stream := h.getStreamInfo(c, client, streamKey, []string{group}, limit)
	dlq := h.getStreamInfo(c, client, dlqKey, nil, limit)

	c.JSON(http.StatusOK, gin.H{
		"success":   true,
		"enabled":   true,
		"server_ts": time.Now().UTC().Format(time.RFC3339Nano),
		"stream":    stream,
		"dlq":       dlq,
	})
}

func (h *JobQueueAdminHandler) getStreamInfo(c *gin.Context, client *redis.Client, key string, groups []string, limit int) jobQueueStreamInfo {
	info := jobQueueStreamInfo{
		Key:              key,
		ConsumersByGroup: map[string][]jobQueueConsumerInfo{},
		PendingByGroup:   map[string]jobQueuePendingSummary{},
	}

	si, err := client.XInfoStream(c.Request.Context(), key).Result()
	if err != nil {
		if err == redis.Nil {
			info.Exists = false
			return info
		}
		if redisHasNoSuchKey(err) {
			info.Exists = false
			return info
		}
		info.Exists = false
		info.Error = err.Error()
		return info
	}

	info.Exists = true
	info.Length = si.Length
	info.EntriesAdded = si.EntriesAdded
	info.LastGeneratedID = si.LastGeneratedID
	info.RecordedFirstID = si.RecordedFirstEntryID
	info.Groups = si.Groups

	msgs, err := client.XRevRangeN(c.Request.Context(), key, "+", "-", int64(limit)).Result()
	if err == nil {
		entries := make([]jobQueueEntry, 0, len(msgs))
		for _, m := range msgs {
			if len(m.Values) == 0 {
				// Redis Streams can return tombstone entries (e.g., after XDEL) where the ID exists
				// but the field map is empty. These are not actionable for operators.
				continue
			}
			vals := map[string]interface{}{}
			for k, v := range m.Values {
				vals[k] = v
			}
			entries = append(entries, jobQueueEntry{ID: m.ID, Values: vals})
		}
		info.RecentEntries = entries
	}

	if len(groups) > 0 {
		ginfo, err := client.XInfoGroups(c.Request.Context(), key).Result()
		if err == nil {
			rows := make([]jobQueueGroupInfo, 0, len(ginfo))
			for _, g := range ginfo {
				rows = append(rows, jobQueueGroupInfo{
					Name:            g.Name,
					Consumers:       g.Consumers,
					Pending:         g.Pending,
					Lag:             g.Lag,
					LastDeliveredID: g.LastDeliveredID,
				})
			}
			info.GroupsInfo = rows
		}

		for _, g := range groups {
			cons, err := client.XInfoConsumers(c.Request.Context(), key, g).Result()
			if err == nil {
				rows := make([]jobQueueConsumerInfo, 0, len(cons))
				for _, cc := range cons {
					rows = append(rows, jobQueueConsumerInfo{
						Name:     cc.Name,
						Pending:  cc.Pending,
						IdleMS:   int64(cc.Idle / time.Millisecond),
						Inactive: int64(cc.Inactive / time.Millisecond),
					})
				}
				info.ConsumersByGroup[g] = rows
			}
			pending, err := client.XPending(c.Request.Context(), key, g).Result()
			if err == nil {
				consumers := make([]string, 0)
				for name := range pending.Consumers {
					consumers = append(consumers, name)
				}
				info.PendingByGroup[g] = jobQueuePendingSummary{
					Count:     pending.Count,
					Lower:     pending.Lower,
					Higher:    pending.Higher,
					Consumers: consumers,
				}
			}
		}
	}

	return info
}

func redisHasNoSuchKey(err error) bool {
	if err == nil {
		return false
	}
	s := strings.ToLower(err.Error())
	return strings.Contains(s, "no such key") || strings.Contains(s, "nogroup")
}
