package services

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/robfig/cron/v3"
	"github.com/trading-system/go-api/internal/models"
	"github.com/trading-system/go-api/internal/repositories"
)

type SchedulerService struct {
	schedules   *repositories.ScheduleRepository
	auditRepo   *repositories.IngestionAuditRepository
	jobQueue    *RedisStreamJobQueue
	useJobQueue bool
}

func NewSchedulerService(schedules *repositories.ScheduleRepository, auditRepo *repositories.IngestionAuditRepository, jobQueue *RedisStreamJobQueue, useJobQueue bool) *SchedulerService {
	return &SchedulerService{schedules: schedules, auditRepo: auditRepo, jobQueue: jobQueue, useJobQueue: useJobQueue}
}

type ScheduleConfig struct {
	Symbols          []string `json:"symbols"`
	Force            *bool    `json:"force"`
	IncludeDataTypes []string `json:"include_data_types"`
	ExcludeDataTypes []string `json:"exclude_data_types"`
	DataTypes        []string `json:"data_types"`
	AssetType        string   `json:"asset_type"`
	TargetDate       string   `json:"target_date"`
}

func (s *SchedulerService) NextRunAt(cronExpr string, tz string, from time.Time) (time.Time, error) {
	loc := time.UTC
	if strings.TrimSpace(tz) != "" {
		l, err := time.LoadLocation(tz)
		if err != nil {
			return time.Time{}, fmt.Errorf("invalid timezone: %w", err)
		}
		loc = l
	}
	parser := cron.NewParser(cron.Minute | cron.Hour | cron.Dom | cron.Month | cron.Dow)
	sched, err := parser.Parse(strings.TrimSpace(cronExpr))
	if err != nil {
		return time.Time{}, fmt.Errorf("invalid cron: %w", err)
	}
	base := from.In(loc)
	next := sched.Next(base)
	return next.UTC(), nil
}

func (s *SchedulerService) Tick(ctx context.Context, now time.Time, limit int) (map[string]any, error) {
	_ = ctx
	if s.schedules == nil {
		return nil, fmt.Errorf("schedule repository is nil")
	}
	if s.auditRepo == nil {
		return nil, fmt.Errorf("audit repository is nil")
	}
	if !s.useJobQueue || s.jobQueue == nil {
		return map[string]any{"success": false, "error": "job queue not enabled"}, nil
	}

	processed := 0
	triggered := 0
	failed := 0
	results := []map[string]any{}

	// Process due schedules inside a transaction using SELECT ... FOR UPDATE SKIP LOCKED
	// so that multiple scheduler ticks (or multiple scheduler containers) do not duplicate work.
	err := s.schedules.WithTx(func(tx *sql.Tx) error {
		due, err := s.schedules.GetDueForUpdate(tx, now, limit)
		if err != nil {
			return err
		}
		processed = len(due)
		for _, sched := range due {
			res := map[string]any{
				"schedule_id":  sched.ScheduleID,
				"kind":         sched.Kind,
				"portfolio_id": sched.PortfolioID,
				"profile":      sched.Profile,
				"success":      false,
			}

			runID, runErr := s.runSchedule(sched)
			if runID != "" {
				res["run_id"] = runID
			}
			if runErr != nil {
				failed += 1
				res["error"] = runErr.Error()
				results = append(results, res)
				// Even on failure, advance next_run_at to avoid tight retry loops.
				next, nerr := s.NextRunAt(sched.CronExpression, sched.Timezone, now)
				if nerr == nil && runID != "" {
					_ = s.schedules.UpdateAfterTick(tx, sched.ScheduleID, now, next, runID)
				}
				continue
			}
			triggered += 1
			res["success"] = true

			next, err := s.NextRunAt(sched.CronExpression, sched.Timezone, now)
			if err != nil {
				// If schedule is invalid, keep it from running again until fixed.
				failed += 1
				res["success"] = false
				res["error"] = err.Error()
				_ = s.schedules.DisableTx(tx, sched.ScheduleID)
				results = append(results, res)
				continue
			}
			if err := s.schedules.UpdateAfterTick(tx, sched.ScheduleID, now, next, runID); err != nil {
				failed += 1
				res["success"] = false
				res["error"] = err.Error()
				results = append(results, res)
				continue
			}
			results = append(results, res)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"success":   true,
		"now":       now.Format(time.RFC3339),
		"processed": processed,
		"triggered": triggered,
		"failed":    failed,
		"results":   results,
	}, nil
}

func (s *SchedulerService) RunOnce(schedule models.Schedule) (runID string, err error) {
	now := time.Now().UTC()
	runID, err = s.runSchedule(schedule)
	if runID == "" {
		return runID, err
	}
	next, nerr := s.NextRunAt(schedule.CronExpression, schedule.Timezone, now)
	if nerr == nil {
		_ = s.schedules.Update(schedule.ScheduleID, map[string]any{
			"last_run_at": now,
			"next_run_at": next,
			"last_run_id": runID,
		})
	}
	return runID, err
}

func (s *SchedulerService) parseConfig(raw json.RawMessage) ScheduleConfig {
	cfg := ScheduleConfig{}
	if len(raw) == 0 {
		return cfg
	}
	_ = json.Unmarshal(raw, &cfg)
	return cfg
}

func (s *SchedulerService) runSchedule(schedule models.Schedule) (runID string, err error) {
	cfg := s.parseConfig(schedule.Config)
	kind := strings.TrimSpace(strings.ToLower(schedule.Kind))
	profile := strings.TrimSpace(schedule.Profile)
	portfolioID := strings.TrimSpace(schedule.PortfolioID)
	if portfolioID == "" {
		return "", fmt.Errorf("portfolio_id is required")
	}

	switch kind {
	case "data_load":
		force := false
		if cfg.Force != nil {
			force = *cfg.Force
		}

		symbols := cfg.Symbols
		if len(symbols) == 0 {
			resolved, err := s.auditRepo.SymbolsForPortfolio(portfolioID)
			if err != nil {
				return "", err
			}
			symbols = resolved
		}
		if len(symbols) == 0 {
			return "", fmt.Errorf("no symbols resolved")
		}

		dataTypes := cfg.DataTypes
		if strings.TrimSpace(profile) != "" {
			resolved, err := ResolveJobProfileDataTypes(profile)
			if err != nil {
				return "", err
			}
			dataTypes = resolved
		}
		dataTypes = applyDataTypeOverridesLocal(dataTypes, cfg.IncludeDataTypes, cfg.ExcludeDataTypes)
		if len(dataTypes) == 0 {
			return "", fmt.Errorf("no data_types resolved")
		}

		runID = uuid.New().String()
		_ = s.auditRepo.CreateRun(runID, "running", map[string]any{
			"operation":          "refresh",
			"portfolio_id":       portfolioID,
			"symbols":            symbols,
			"profile":            profile,
			"data_types":         dataTypes,
			"include_data_types": normalizeDataTypesLocal(cfg.IncludeDataTypes),
			"exclude_data_types": normalizeDataTypesLocal(cfg.ExcludeDataTypes),
			"force":              force,
			"requested_at":       time.Now().UTC().Format(time.RFC3339),
			"triggered_by":       "scheduler",
			"schedule_id":        schedule.ScheduleID,
		})

		parentCtx := context.Background()
		ctx, cancel := context.WithTimeout(parentCtx, 15*time.Second)
		defer cancel()

		_ = s.jobQueue.SetRunRemaining(ctx, runID, len(symbols))

		enqueueFailed := 0
		for _, sym := range symbols {
			symCopy := sym
			if _, err := s.jobQueue.EnqueueDataLoadJob(ctx, DataLoadJobPayload{
				RunID:       runID,
				PortfolioID: portfolioID,
				Symbol:      symCopy,
				DataTypes:   dataTypes,
				Force:       force,
				Attempt:     1,
				MaxAttempts: 3,
			}); err != nil {
				enqueueFailed += 1
				errMsg := err.Error()
				_ = s.auditRepo.CreateEvent(runID, "error", "queue_enqueue_failed", &symCopy, nil, nil, &errMsg, nil, nil)
				continue
			}
			m := "job enqueued"
			_ = s.auditRepo.CreateEvent(runID, "info", "queue_job_enqueued", &symCopy, nil, &m, nil, map[string]any{"profile": profile, "data_types": dataTypes}, nil)
		}
		if enqueueFailed > 0 {
			failMsg := "some jobs failed to enqueue"
			_ = s.auditRepo.CreateEvent(runID, "error", "queue_enqueue_partial_failure", nil, nil, nil, &failMsg, map[string]any{"failed": enqueueFailed}, nil)
			_ = s.auditRepo.UpdateRunStatus(runID, "failed", map[string]any{"go_error": failMsg, "enqueue_failed": enqueueFailed})
			return runID, fmt.Errorf(failMsg)
		}

		fin := "enqueue completed"
		_ = s.auditRepo.CreateEvent(runID, "info", "queue_enqueue_finished", nil, nil, &fin, nil, map[string]any{"symbols_count": len(symbols)}, nil)
		return runID, nil

	case "analysis_run":
		assetType := strings.TrimSpace(cfg.AssetType)
		if assetType == "" {
			assetType = "stock"
		}
		assetType = strings.ToLower(assetType)

		resolvedProfile := string(AnalysisProfileDailySignals)
		if strings.TrimSpace(profile) != "" {
			p, err := ResolveAnalysisProfile(profile)
			if err != nil {
				return "", err
			}
			resolvedProfile = string(p)
		}

		targetDate := strings.TrimSpace(cfg.TargetDate)
		if targetDate == "" {
			targetDate = time.Now().UTC().Format("2006-01-02")
		}

		symbols := cfg.Symbols
		if len(symbols) == 0 {
			resolved, err := s.auditRepo.SymbolsForPortfolio(portfolioID)
			if err != nil {
				return "", err
			}
			symbols = resolved
		}
		if len(symbols) == 0 {
			return "", fmt.Errorf("no symbols resolved")
		}

		runID = uuid.New().String()
		_ = s.auditRepo.CreateRun(runID, "running", map[string]any{
			"operation":    "portfolio_analysis",
			"portfolio_id": portfolioID,
			"symbols":      symbols,
			"profile":      resolvedProfile,
			"asset_type":   assetType,
			"target_date":  targetDate,
			"requested_at": time.Now().UTC().Format(time.RFC3339),
			"triggered_by": "scheduler",
			"schedule_id":  schedule.ScheduleID,
		})

		parentCtx := context.Background()
		ctx, cancel := context.WithTimeout(parentCtx, 15*time.Second)
		defer cancel()

		_ = s.jobQueue.SetRunRemaining(ctx, runID, len(symbols))

		enqueueFailed := 0
		for _, sym := range symbols {
			symCopy := sym
			if _, err := s.jobQueue.EnqueuePortfolioAnalysisJob(ctx, PortfolioAnalysisJobPayload{
				RunID:       runID,
				PortfolioID: portfolioID,
				Symbol:      symCopy,
				AssetType:   assetType,
				TargetDate:  targetDate,
				Profile:     resolvedProfile,
				Attempt:     1,
				MaxAttempts: 3,
			}); err != nil {
				enqueueFailed += 1
				errMsg := err.Error()
				_ = s.auditRepo.CreateEvent(runID, "error", "queue_enqueue_failed", &symCopy, nil, nil, &errMsg, nil, nil)
				continue
			}
			m := "job enqueued"
			_ = s.auditRepo.CreateEvent(runID, "info", "queue_job_enqueued", &symCopy, nil, &m, nil, map[string]any{"asset_type": assetType, "target_date": targetDate, "profile": resolvedProfile}, nil)
		}
		if enqueueFailed > 0 {
			failMsg := "some jobs failed to enqueue"
			_ = s.auditRepo.CreateEvent(runID, "error", "queue_enqueue_partial_failure", nil, nil, nil, &failMsg, map[string]any{"failed": enqueueFailed}, nil)
			_ = s.auditRepo.UpdateRunStatus(runID, "failed", map[string]any{"go_error": failMsg, "enqueue_failed": enqueueFailed})
			return runID, fmt.Errorf(failMsg)
		}

		fin := "enqueue completed"
		_ = s.auditRepo.CreateEvent(runID, "info", "queue_enqueue_finished", nil, nil, &fin, nil, map[string]any{"symbols_count": len(symbols)}, nil)
		return runID, nil

	case "rebalance_run":
		resolvedProfile := string(AnalysisProfileWeeklyRebalance)
		if strings.TrimSpace(profile) != "" {
			p, err := ResolveAnalysisProfile(profile)
			if err != nil {
				return "", err
			}
			resolvedProfile = string(p)
		}
		if AnalysisProfile(resolvedProfile) != AnalysisProfileWeeklyRebalance {
			return "", fmt.Errorf("unsupported rebalance profile")
		}

		targetDate := strings.TrimSpace(cfg.TargetDate)
		if targetDate == "" {
			targetDate = time.Now().UTC().Format("2006-01-02")
		}

		runID = uuid.New().String()
		_ = s.auditRepo.CreateRun(runID, "running", map[string]any{
			"operation":    "portfolio_rebalance",
			"portfolio_id": portfolioID,
			"symbols":      cfg.Symbols,
			"profile":      resolvedProfile,
			"target_date":  targetDate,
			"requested_at": time.Now().UTC().Format(time.RFC3339),
			"triggered_by": "scheduler",
			"schedule_id":  schedule.ScheduleID,
		})

		parentCtx := context.Background()
		ctx, cancel := context.WithTimeout(parentCtx, 15*time.Second)
		defer cancel()

		_ = s.jobQueue.SetRunRemaining(ctx, runID, 1)

		if _, err := s.jobQueue.EnqueuePortfolioRebalanceJob(ctx, PortfolioRebalanceJobPayload{
			RunID:       runID,
			PortfolioID: portfolioID,
			TargetDate:  targetDate,
			Profile:     resolvedProfile,
			Attempt:     1,
			MaxAttempts: 3,
		}); err != nil {
			errMsg := err.Error()
			_ = s.auditRepo.CreateEvent(runID, "error", "queue_enqueue_failed", nil, nil, nil, &errMsg, nil, nil)
			_ = s.auditRepo.UpdateRunStatus(runID, "failed", map[string]any{"go_error": errMsg})
			return runID, err
		}
		fin := "enqueue completed"
		_ = s.auditRepo.CreateEvent(runID, "info", "queue_enqueue_finished", nil, nil, &fin, nil, map[string]any{"profile": resolvedProfile}, nil)
		return runID, nil

	default:
		return "", fmt.Errorf("unknown schedule kind")
	}
}

func normalizeDataTypesLocal(in []string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(in))
	for _, raw := range in {
		s := strings.TrimSpace(strings.ToLower(raw))
		if s == "" {
			continue
		}
		if _, ok := seen[s]; ok {
			continue
		}
		seen[s] = struct{}{}
		out = append(out, s)
	}
	sort.Strings(out)
	return out
}

func applyDataTypeOverridesLocal(base []string, include []string, exclude []string) []string {
	base = normalizeDataTypesLocal(base)
	include = normalizeDataTypesLocal(include)
	exclude = normalizeDataTypesLocal(exclude)

	excluded := map[string]struct{}{}
	for _, dt := range exclude {
		excluded[dt] = struct{}{}
	}

	seen := map[string]struct{}{}
	out := make([]string, 0, len(base)+len(include))
	for _, dt := range base {
		if _, ok := excluded[dt]; ok {
			continue
		}
		if _, ok := seen[dt]; ok {
			continue
		}
		seen[dt] = struct{}{}
		out = append(out, dt)
	}
	for _, dt := range include {
		if _, ok := excluded[dt]; ok {
			continue
		}
		if _, ok := seen[dt]; ok {
			continue
		}
		seen[dt] = struct{}{}
		out = append(out, dt)
	}
	return out
}
