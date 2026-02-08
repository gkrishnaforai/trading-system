package services

import (
	"fmt"
	"sort"
	"strings"
)

type JobProfile string

const (
	JobProfileIntradayAlerts JobProfile = "intraday_alerts"
	JobProfileIntradayAlertsWithIntradayPrices JobProfile = "intraday_alerts_with_intraday_prices"
	JobProfileDailyAnalysis JobProfile = "daily_analysis"
	JobProfileBootstrap JobProfile = "bootstrap"
)

func AvailableJobProfiles() []JobProfile {
	return []JobProfile{
		JobProfileIntradayAlerts,
		JobProfileIntradayAlertsWithIntradayPrices,
		JobProfileDailyAnalysis,
		JobProfileBootstrap,
	}
}

func ResolveJobProfileDataTypes(profile string) ([]string, error) {
	p := strings.TrimSpace(strings.ToLower(profile))
	if p == "" {
		return nil, fmt.Errorf("profile must be non-empty")
	}

	switch JobProfile(p) {
	case JobProfileIntradayAlerts:
		return []string{
			"price_current",
			"news",
			"stock_grades",
			"price_targets",
			"consensus_data",
		}, nil
	case JobProfileIntradayAlertsWithIntradayPrices:
		return []string{
			"price_current",
			"price_intraday_5m",
			"news",
			"stock_grades",
			"price_targets",
			"consensus_data",
		}, nil
	case JobProfileDailyAnalysis:
		return []string{
			"price_historical",
			"fundamentals",
			"financial_ratios",
			"key_metrics_ttm",
			"financial_scores",
			"indicators",
			"earnings",
		}, nil
	case JobProfileBootstrap:
		return []string{
			"price_historical",
			"fundamentals",
			"income_statements",
			"balance_sheets",
			"cash_flow_statements",
			"financial_ratios",
			"key_metrics_ttm",
			"financial_scores",
			"stock_grades",
			"analyst_ratings",
			"consensus_data",
			"price_targets",
			"ratings_snapshot",
			"historical_grades",
			"earnings",
			"corporate_actions",
		}, nil
	default:
		return nil, fmt.Errorf("unknown profile: %s", p)
	}
}

func JobProfilesAsMap() map[string][]string {
	out := map[string][]string{}
	for _, p := range AvailableJobProfiles() {
		dts, err := ResolveJobProfileDataTypes(string(p))
		if err != nil {
			continue
		}
		sort.Strings(dts)
		out[string(p)] = dts
	}
	return out
}
