package services

import (
	"fmt"
	"sort"
	"strings"
)

type AnalysisProfile string

const (
	AnalysisProfileDailySignals    AnalysisProfile = "daily_signals"
	AnalysisProfileIntradaySignals AnalysisProfile = "intraday_signals"
	AnalysisProfileWeeklyRebalance AnalysisProfile = "weekly_rebalance"
)

func AvailableAnalysisProfiles() []AnalysisProfile {
	return []AnalysisProfile{
		AnalysisProfileDailySignals,
		AnalysisProfileIntradaySignals,
		AnalysisProfileWeeklyRebalance,
	}
}

func ResolveAnalysisProfile(profile string) (AnalysisProfile, error) {
	p := strings.TrimSpace(strings.ToLower(profile))
	if p == "" {
		return "", fmt.Errorf("profile must be non-empty")
	}

	switch AnalysisProfile(p) {
	case AnalysisProfileDailySignals, AnalysisProfileIntradaySignals, AnalysisProfileWeeklyRebalance:
		return AnalysisProfile(p), nil
	default:
		return "", fmt.Errorf("unknown profile: %s", p)
	}
}

func AnalysisProfilesAsMap() map[string]map[string]any {
	out := map[string]map[string]any{}
	for _, p := range AvailableAnalysisProfiles() {
		out[string(p)] = map[string]any{}
	}

	keys := make([]string, 0, len(out))
	for k := range out {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	ordered := map[string]map[string]any{}
	for _, k := range keys {
		ordered[k] = out[k]
	}
	return ordered
}
