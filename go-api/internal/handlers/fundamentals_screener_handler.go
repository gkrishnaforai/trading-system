package handlers

import (
	"context"
	"database/sql"
	"encoding/json"
	"math"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/database"
	"github.com/trading-system/go-api/internal/repositories"
	"github.com/trading-system/go-api/internal/services"
)

type FundamentalsScreenerHandler struct {
	marketDataRepo *repositories.MarketDataRepository
	pythonWorker   *services.PythonWorkerClient
}

func NewFundamentalsScreenerHandler(marketDataRepo *repositories.MarketDataRepository, pythonWorker *services.PythonWorkerClient) *FundamentalsScreenerHandler {
	return &FundamentalsScreenerHandler{marketDataRepo: marketDataRepo, pythonWorker: pythonWorker}
}

type presetWeights struct {
	Investment float64
	Entry      float64
	Catalyst   float64
}

func screenerPresetWeights(presetID string) (presetWeights, bool) {
	switch presetID {
	case "2x_6_12m":
		return presetWeights{Investment: 0.35, Entry: 0.45, Catalyst: 0.20}, true
	case "compounders_2030":
		return presetWeights{Investment: 0.70, Entry: 0.10, Catalyst: 0.20}, true
	case "spec_10x":
		return presetWeights{Investment: 0.40, Entry: 0.25, Catalyst: 0.35}, true
	case "buffett_ai":
		return presetWeights{Investment: 0.85, Entry: 0.05, Catalyst: 0.10}, true
	case "underappreciated_ai":
		return presetWeights{Investment: 0.45, Entry: 0.25, Catalyst: 0.30}, true
	default:
		return presetWeights{}, false
	}
}

func clamp01(v float64) float64 {
	if v < 0 {
		return 0
	}
	if v > 1 {
		return 1
	}
	return v
}

func clamp100(v float64) float64 {
	if v < 0 {
		return 0
	}
	if v > 100 {
		return 100
	}
	return v
}

func presetMaxMarketCap(presetID string) (float64, bool) {
	switch presetID {
	case "spec_10x":
		return 50e9, true
	default:
		return 0, false
	}
}

func presetRequiresAICatalyst(presetID string) bool {
	switch presetID {
	case "underappreciated_ai":
		return true
	default:
		return false
	}
}

func investmentScoreV0(result gin.H) float64 {
	missing := 0.0
	if v, ok := result["missing_required_fields"]; ok {
		switch vv := v.(type) {
		case int:
			missing = float64(vv)
		case int32:
			missing = float64(vv)
		case int64:
			missing = float64(vv)
		case float64:
			missing = vv
		case float32:
			missing = float64(vv)
		}
	}

	// Simple heuristic: penalize missing fields.
	// This is a placeholder until InvestmentEngine exists.
	base := 100.0 - (missing * 20.0)
	return clamp100(base)
}

func (h *FundamentalsScreenerHandler) maybeEnrichWithPresetScores(c *gin.Context, results []gin.H) []gin.H {
	presetID := strings.TrimSpace(c.Query("preset_id"))
	if presetID == "" {
		return results
	}

	weights, ok := screenerPresetWeights(presetID)
	if !ok {
		return results
	}
	if h.pythonWorker == nil {
		return results
	}

	// Collect symbols
	symbols := make([]string, 0, len(results))
	for _, r := range results {
		sym, _ := r["symbol"].(string)
		sym = strings.TrimSpace(strings.ToUpper(sym))
		if sym == "" {
			continue
		}
		symbols = append(symbols, sym)
	}
	if len(symbols) == 0 {
		return results
	}

	// Call python-worker factor engine entry-score
	tctx, cancel := context.WithTimeout(c.Request.Context(), 25*time.Second)
	defer cancel()

	var resp map[string]any
	err := h.pythonWorker.PostJSONDecode(tctx, "/admin/factor-engine/entry-score", gin.H{"symbols": symbols}, &resp)
	if err != nil {
		resp = map[string]any{}
	}

	// Call python-worker factor engine catalyst-score (best-effort)
	var catResp map[string]any
	_ = h.pythonWorker.PostJSONDecode(tctx, "/admin/factor-engine/catalyst-score", gin.H{"symbols": symbols}, &catResp)

	resultsMap, _ := resp["results"].(map[string]any)
	if resultsMap == nil {
		resultsMap = map[string]any{}
	}

	catResultsMap, _ := catResp["results"].(map[string]any)

	requireAICat := presetRequiresAICatalyst(presetID)

	getEntryScore := func(sym string) (float64, bool) {
		entryAny, ok := resultsMap[sym]
		if !ok {
			return 0, false
		}
		entry, _ := entryAny.(map[string]any)
		if entry == nil {
			return 0, false
		}
		if okv, ok := entry["ok"].(bool); ok && !okv {
			return 0, false
		}
		factors, _ := entry["factors"].(map[string]any)
		if factors == nil {
			return 0, false
		}
		esAny, ok := factors["entry.score"]
		if !ok {
			return 0, false
		}
		esRec, _ := esAny.(map[string]any)
		if esRec == nil {
			return 0, false
		}
		vAny, ok := esRec["value"]
		if !ok {
			return 0, false
		}
		switch vv := vAny.(type) {
		case float64:
			return vv, true
		case float32:
			return float64(vv), true
		case int:
			return float64(vv), true
		case int64:
			return float64(vv), true
		case json.Number:
			if f, err := vv.Float64(); err == nil {
				return f, true
			}
		}
		return 0, false
	}

	getCatalystScore := func(sym string) (float64, bool) {
		if catResultsMap == nil {
			return 0, false
		}
		catAny, ok := catResultsMap[sym]
		if !ok {
			return 0, false
		}
		cat, _ := catAny.(map[string]any)
		if cat == nil {
			return 0, false
		}
		if okv, ok := cat["ok"].(bool); ok && !okv {
			return 0, false
		}
		factors, _ := cat["factors"].(map[string]any)
		if factors == nil {
			return 0, false
		}
		sAny, ok := factors["catalyst.score"]
		if !ok {
			return 0, false
		}
		sRec, _ := sAny.(map[string]any)
		if sRec == nil {
			return 0, false
		}
		vAny, ok := sRec["value"]
		if !ok {
			return 0, false
		}
		switch vv := vAny.(type) {
		case float64:
			return vv, true
		case float32:
			return float64(vv), true
		case int:
			return float64(vv), true
		case int64:
			return float64(vv), true
		case json.Number:
			if f, err := vv.Float64(); err == nil {
				return f, true
			}
		}
		return 0, false
	}

	getAICatalyst := func(sym string) (bool, *int) {
		if catResultsMap == nil {
			return false, nil
		}
		catAny, ok := catResultsMap[sym]
		if !ok {
			return false, nil
		}
		cat, _ := catAny.(map[string]any)
		if cat == nil {
			return false, nil
		}
		if okv, ok := cat["ok"].(bool); ok && !okv {
			return false, nil
		}
		factors, _ := cat["factors"].(map[string]any)
		if factors == nil {
			return false, nil
		}

		recent := false
		if rAny, ok := factors["catalyst.ai_news_recent_30d"]; ok {
			rRec, _ := rAny.(map[string]any)
			if rRec != nil {
				if vAny, ok := rRec["value"]; ok {
					switch vv := vAny.(type) {
					case bool:
						recent = vv
					case string:
						recent = strings.EqualFold(vv, "true") || vv == "1"
					}
				}
			}
		}

		var cntPtr *int
		if cAny, ok := factors["catalyst.ai_news_30d_count"]; ok {
			cRec, _ := cAny.(map[string]any)
			if cRec != nil {
				if vAny, ok := cRec["value"]; ok {
					switch vv := vAny.(type) {
					case float64:
						ci := int(vv)
						cntPtr = &ci
					case int:
						ci := vv
						cntPtr = &ci
					case int64:
						ci := int(vv)
						cntPtr = &ci
					case json.Number:
						if f, err := vv.Float64(); err == nil {
							ci := int(f)
							cntPtr = &ci
						}
					}
				}
			}
		}

		return recent, cntPtr
	}

	out := make([]gin.H, 0, len(results))
	for i := range results {
		sym, _ := results[i]["symbol"].(string)
		sym = strings.TrimSpace(strings.ToUpper(sym))
		if sym == "" {
			continue
		}

		inv := investmentScoreV0(results[i])
		entry, hasEntry := getEntryScore(sym)
		if !hasEntry {
			entry = 0
		}
		cat, hasCat := getCatalystScore(sym)
		if !hasCat {
			cat = 0
		}

		aiRecent, aiCnt := getAICatalyst(sym)
		results[i]["ai_catalyst_recent_30d"] = aiRecent
		results[i]["ai_catalyst_30d_count"] = aiCnt
		if requireAICat && !aiRecent {
			continue
		}

		overall := (inv * weights.Investment) + (entry * weights.Entry) + (cat * weights.Catalyst)

		results[i]["preset_id"] = presetID
		results[i]["preset_investment_w"] = clamp01(weights.Investment)
		results[i]["preset_entry_w"] = clamp01(weights.Entry)
		results[i]["preset_catalyst_w"] = clamp01(weights.Catalyst)
		results[i]["investment_score"] = clamp100(inv)
		results[i]["entry_score"] = clamp100(entry)
		results[i]["catalyst_score"] = clamp100(cat)
		results[i]["overall_score"] = clamp100(overall)
		out = append(out, results[i])
	}

	return out
}

type stockMeta struct {
	Symbol    string
	Sector    *string
	Industry  *string
	MarketCap *float64
}

type incomeStatementRow struct {
	Date                         time.Time
	Revenue                      *float64
	GrossProfit                  *float64
	OperatingIncome              *float64
	ResearchAndDevelopment       *float64
	SellingGeneralAdministrative *float64
}

func screenerDescriptions(profile string) (string, string) {
	switch profile {
	case "quality_compounders":
		return "Durable, high-quality compounders with strong margins and balance sheets.", "What it finds:\n- Durable, high-quality businesses with consistent growth and strong profitability.\n- Typically established leaders with solid balance sheets.\n\nWho it’s for:\n- Long-term investors who want fewer blow-ups and smoother compounding.\n- Core portfolio / long-horizon allocations.\n\nTypical risk:\n- Valuation risk (great companies can be overpriced).\n- Can lag in risk-on rallies vs early-stage growth.\n\nTypical reward:\n- Higher probability of steady multi-year compounding.\n- Lower downside than speculative names during drawdowns."
	case "value":
		return "Cheaper valuation names (yields/multiples) with potential mean reversion.", "What it finds:\n- Stocks priced cheap vs earnings/cash flow (lower multiples, higher yields).\n- Often mature businesses, cyclicals, or temporarily out-of-favor companies.\n\nWho it’s for:\n- Investors comfortable buying unpopular/ignored names.\n- Those who want margin of safety and mean-reversion potential.\n\nTypical risk:\n- Value traps (cheap for a reason).\n- Cyclical exposure; earnings can drop in recessions.\n\nTypical reward:\n- Re-rating upside when sentiment improves.\n- Strong returns when fundamentals stabilize and multiples expand."
	case "growth":
		return "Higher growth companies (revenue/earnings) with acceptable quality checks.", "What it finds:\n- Higher growth businesses (revenue/earnings growth), sometimes with decent margins.\n- Often secular tailwinds, expanding TAM, category winners.\n\nWho it’s for:\n- Investors seeking higher upside and comfortable with volatility.\n- People who can hold through drawdowns.\n\nTypical risk:\n- Multiple compression when rates rise or growth slows.\n- Execution risk; growth can decelerate unexpectedly.\n\nTypical reward:\n- Bigger upside if growth persists and margins expand.\n- Multi-bagger potential in strong macro/liquidity regimes."
	case "garp":
		return "Balanced growth-at-a-reasonable-price (growth + quality + valuation discipline).", "What it finds:\n- A blend: solid growth + acceptable valuation + profitability/quality checks.\n- Tends to avoid the most expensive story stocks.\n\nWho it’s for:\n- Investors who want growth exposure without paying any price.\n- Good for an all-weather growth allocation.\n\nTypical risk:\n- Can underperform pure growth in mania phases.\n- Still exposed to growth slowdowns (usually less fragile).\n\nTypical reward:\n- Better risk-adjusted returns than pure growth in many cycles.\n- Captures growth upside with fewer valuation blow-ups."
	case "inflection":
		return "Early signs of accelerating growth and improving margins (higher upside, higher noise).", "What it finds:\n- Early leading indicators of improvement (growth acceleration, margin inflection, reinvestment/R&D signals).\n- Often earlier-cycle names before the crowd.\n\nWho it’s for:\n- Investors who want earlier entries and accept uncertainty.\n- A satellite sleeve around a core portfolio.\n\nTypical risk:\n- False positives; inflection may not persist.\n- Higher volatility and drawdowns; earnings and narrative risk.\n\nTypical reward:\n- Large upside if the inflection becomes sustained growth.\n- Earlier entry points than traditional growth screens."
	default:
		return "", ""
	}
}

func (h *FundamentalsScreenerHandler) ScreenQualityCompounders(c *gin.Context) {
	limit := 5000
	if v := strings.TrimSpace(c.Query("limit")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	if limit > 5000 {
		limit = 5000
	}

	offset := 0
	if v := strings.TrimSpace(c.Query("offset")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed >= 0 {
			offset = parsed
		}
	}

	symbolPrefix := strings.TrimSpace(c.Query("symbol_prefix"))
	if symbolPrefix != "" {
		symbolPrefix = strings.ToUpper(symbolPrefix)
	}

	onlyPass := false
	if v := strings.TrimSpace(c.Query("only_pass")); v != "" {
		onlyPass = strings.EqualFold(v, "1") || strings.EqualFold(v, "true") || strings.EqualFold(v, "yes")
	}

	presetID := strings.TrimSpace(c.Query("preset_id"))
	presetMaxMC := 0.0
	if v, ok := presetMaxMarketCap(presetID); ok {
		presetMaxMC = v
	}

	minMarketCap := 5e9
	if v := strings.TrimSpace(c.Query("min_market_cap")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minMarketCap = parsed
		}
	}

	minRevenueGrowthPct := 8.0
	if v := strings.TrimSpace(c.Query("min_revenue_growth_yoy_pct")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minRevenueGrowthPct = parsed
		}
	}

	minOperatingMarginPct := 15.0
	if v := strings.TrimSpace(c.Query("min_operating_margin_pct")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minOperatingMarginPct = parsed
		}
	}

	maxDebtToEquity := 1.0
	if v := strings.TrimSpace(c.Query("max_debt_to_equity")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			maxDebtToEquity = parsed
		}
	}

	allStocks, metaErr := loadAllStocksMeta(limit, offset, symbolPrefix)
	if metaErr != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": metaErr.Error()})
		return
	}

	symbols := make([]string, 0, len(allStocks))
	for _, s := range allStocks {
		if s.Symbol == "" {
			continue
		}
		symbols = append(symbols, s.Symbol)
	}

	snapshots, err := h.marketDataRepo.ListLatestFundamentalsSnapshotsForSymbols(symbols)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	latestBySymbol := map[string]map[string]interface{}{}
	asOfBySymbol := map[string]string{}
	for _, r := range snapshots {
		sym, _ := r["symbol"].(string)
		sym = strings.TrimSpace(strings.ToUpper(sym))
		if sym == "" {
			continue
		}
		payload, _ := r["payload"].(map[string]interface{})
		payload = payloadOrEmpty(payload)
		latestBySymbol[sym] = payload
		if asOf, ok := r["as_of_date"].(string); ok {
			asOfBySymbol[sym] = asOf
		}
	}

	results := make([]gin.H, 0)
	for _, meta := range allStocks {
		sym := strings.TrimSpace(strings.ToUpper(meta.Symbol))
		if sym == "" {
			continue
		}

		payload := latestBySymbol[sym]
		payload = payloadOrEmpty(payload)

		marketCap := firstFloat(meta.MarketCap, getFloat(payload, []string{"marketCap", "market_cap"}))
		revGrowthPct := normalizePct(getFloat(payload, []string{"revenueGrowthYoY", "revenue_growth_yoy", "revenueGrowth", "revenue_growth", "revenue_growth_yoy_pct", "revenue_growth_pct"}))
		opMarginPct := normalizePct(getFloat(payload, []string{"operatingMargin", "operating_margin"}))
		debtToEquity := getFloat(payload, []string{"debtToEquity", "debt_to_equity"})
		pe := getFloat(payload, []string{"peRatio", "pe_ratio", "priceEarningsRatio"})

		missing := 0
		if marketCap == nil {
			missing++
		}
		if revGrowthPct == nil {
			missing++
		}
		if opMarginPct == nil {
			missing++
		}
		if debtToEquity == nil {
			missing++
		}

		pass := true
		if marketCap == nil || *marketCap < minMarketCap {
			pass = false
		}
		if presetMaxMC > 0 && marketCap != nil && *marketCap > presetMaxMC {
			pass = false
		}
		if revGrowthPct == nil || *revGrowthPct < minRevenueGrowthPct {
			pass = false
		}
		if opMarginPct == nil || *opMarginPct < minOperatingMarginPct {
			pass = false
		}
		if debtToEquity == nil || *debtToEquity > maxDebtToEquity {
			pass = false
		}

		if onlyPass && !pass {
			continue
		}

		results = append(results, gin.H{
			"symbol":                    sym,
			"sector":                    meta.Sector,
			"industry":                  meta.Industry,
			"market_cap":                marketCap,
			"fundamentals_as_of":        asOfBySymbol[sym],
			"revenue_growth_yoy_pct":    revGrowthPct,
			"operating_margin_pct":      opMarginPct,
			"debt_to_equity":            debtToEquity,
			"pe_ratio":                  pe,
			"missing_required_fields":   missing,
			"pass":                      pass,
			"screen_profile":            "quality_compounders",
			"screen_min_market_cap":     minMarketCap,
			"screen_min_rev_growth_pct": minRevenueGrowthPct,
			"screen_min_op_margin_pct":  minOperatingMarginPct,
			"screen_max_debt_to_equity": maxDebtToEquity,
			"only_pass":                 onlyPass,
		})
	}

	shortDesc, longDesc := screenerDescriptions("quality_compounders")
	results = h.maybeEnrichWithPresetScores(c, results)
	c.JSON(http.StatusOK, gin.H{
		"success":                   true,
		"profile":                   "quality_compounders",
		"profile_description_short": shortDesc,
		"profile_description_long":  longDesc,
		"count":                     len(results),
		"results":                   results,
		"limit":                     limit,
		"offset":                    offset,
		"symbol_prefix":             symbolPrefix,
	})
}

func (h *FundamentalsScreenerHandler) ScreenValue(c *gin.Context) {
	limit := 5000
	if v := strings.TrimSpace(c.Query("limit")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	if limit > 5000 {
		limit = 5000
	}

	offset := 0
	if v := strings.TrimSpace(c.Query("offset")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed >= 0 {
			offset = parsed
		}
	}

	symbolPrefix := strings.TrimSpace(c.Query("symbol_prefix"))
	if symbolPrefix != "" {
		symbolPrefix = strings.ToUpper(symbolPrefix)
	}

	onlyPass := false
	if v := strings.TrimSpace(c.Query("only_pass")); v != "" {
		onlyPass = strings.EqualFold(v, "1") || strings.EqualFold(v, "true") || strings.EqualFold(v, "yes")
	}

	presetID := strings.TrimSpace(c.Query("preset_id"))
	presetMaxMC := 0.0
	if v, ok := presetMaxMarketCap(presetID); ok {
		presetMaxMC = v
	}

	minMarketCap := 2e9
	if v := strings.TrimSpace(c.Query("min_market_cap")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minMarketCap = parsed
		}
	}

	maxPE := 20.0
	if v := strings.TrimSpace(c.Query("max_pe")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			maxPE = parsed
		}
	}

	maxEvToEbitda := 12.0
	if v := strings.TrimSpace(c.Query("max_ev_to_ebitda")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			maxEvToEbitda = parsed
		}
	}

	minFcfYieldPct := 4.0
	if v := strings.TrimSpace(c.Query("min_fcf_yield_pct")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minFcfYieldPct = parsed
		}
	}

	minEarningsYieldPct := 5.0
	if v := strings.TrimSpace(c.Query("min_earnings_yield_pct")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minEarningsYieldPct = parsed
		}
	}

	maxDebtToEquity := 2.0
	if v := strings.TrimSpace(c.Query("max_debt_to_equity")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			maxDebtToEquity = parsed
		}
	}

	allStocks, metaErr := loadAllStocksMeta(limit, offset, symbolPrefix)
	if metaErr != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": metaErr.Error()})
		return
	}

	symbols := make([]string, 0, len(allStocks))
	for _, s := range allStocks {
		if s.Symbol == "" {
			continue
		}
		symbols = append(symbols, s.Symbol)
	}

	snapshots, err := h.marketDataRepo.ListLatestFundamentalsSnapshotsForSymbols(symbols)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	latestBySymbol := map[string]map[string]interface{}{}
	asOfBySymbol := map[string]string{}
	for _, r := range snapshots {
		sym, _ := r["symbol"].(string)
		sym = strings.TrimSpace(strings.ToUpper(sym))
		if sym == "" {
			continue
		}
		payload, _ := r["payload"].(map[string]interface{})
		payload = payloadOrEmpty(payload)
		latestBySymbol[sym] = payload
		if asOf, ok := r["as_of_date"].(string); ok {
			asOfBySymbol[sym] = asOf
		}
	}

	results := make([]gin.H, 0)
	for _, meta := range allStocks {
		sym := strings.TrimSpace(strings.ToUpper(meta.Symbol))
		if sym == "" {
			continue
		}
		payload := latestBySymbol[sym]
		payload = payloadOrEmpty(payload)

		marketCap := firstFloat(meta.MarketCap, getFloat(payload, []string{"marketCap", "market_cap", "market_capitalization", "market_capitalization_yahoo"}))
		pe := getFloat(payload, []string{"peRatio", "pe_ratio", "priceEarningsRatio"})
		evToEbitda := getFloat(payload, []string{"enterpriseToEbitda", "enterprise_to_ebitda", "ev_to_ebitda"})
		debtToEquity := getFloat(payload, []string{"debtToEquity", "debt_to_equity"})
		freeCashFlow := getFloat(payload, []string{"freeCashFlow", "free_cash_flow", "free_cash_flow_yahoo"})

		var earningsYieldPct *float64
		if pe != nil && *pe > 0 {
			y := 100.0 / *pe
			earningsYieldPct = &y
		}
		var fcfYieldPct *float64
		if freeCashFlow != nil && marketCap != nil && *marketCap > 0 {
			y := (*freeCashFlow / *marketCap) * 100.0
			fcfYieldPct = &y
		}

		missing := 0
		if marketCap == nil {
			missing++
		}
		if pe == nil {
			missing++
		}
		if evToEbitda == nil {
			missing++
		}
		if debtToEquity == nil {
			missing++
		}
		if fcfYieldPct == nil {
			missing++
		}
		if earningsYieldPct == nil {
			missing++
		}

		pass := true
		if marketCap == nil || *marketCap < minMarketCap {
			pass = false
		}
		if presetMaxMC > 0 && marketCap != nil && *marketCap > presetMaxMC {
			pass = false
		}
		if pe == nil || *pe <= 0 || *pe > maxPE {
			pass = false
		}
		if evToEbitda == nil || *evToEbitda <= 0 || *evToEbitda > maxEvToEbitda {
			pass = false
		}
		if fcfYieldPct == nil || *fcfYieldPct < minFcfYieldPct {
			pass = false
		}
		if earningsYieldPct == nil || *earningsYieldPct < minEarningsYieldPct {
			pass = false
		}
		if debtToEquity == nil || *debtToEquity > maxDebtToEquity {
			pass = false
		}

		if onlyPass && !pass {
			continue
		}

		results = append(results, gin.H{
			"symbol":                        sym,
			"sector":                        meta.Sector,
			"industry":                      meta.Industry,
			"market_cap":                    marketCap,
			"fundamentals_as_of":            asOfBySymbol[sym],
			"pe_ratio":                      pe,
			"ev_to_ebitda":                  evToEbitda,
			"debt_to_equity":                debtToEquity,
			"earnings_yield_pct":            earningsYieldPct,
			"fcf_yield_pct":                 fcfYieldPct,
			"missing_required_fields":       missing,
			"pass":                          pass,
			"screen_profile":                "value",
			"screen_min_market_cap":         minMarketCap,
			"screen_max_pe":                 maxPE,
			"screen_max_ev_to_ebitda":       maxEvToEbitda,
			"screen_min_fcf_yield_pct":      minFcfYieldPct,
			"screen_min_earnings_yield_pct": minEarningsYieldPct,
			"screen_max_debt_to_equity":     maxDebtToEquity,
			"only_pass":                     onlyPass,
		})
	}

	shortDesc, longDesc := screenerDescriptions("value")
	results = h.maybeEnrichWithPresetScores(c, results)
	c.JSON(http.StatusOK, gin.H{
		"success":                   true,
		"profile":                   "value",
		"profile_description_short": shortDesc,
		"profile_description_long":  longDesc,
		"count":                     len(results),
		"results":                   results,
		"limit":                     limit,
		"offset":                    offset,
		"symbol_prefix":             symbolPrefix,
	})
}

func (h *FundamentalsScreenerHandler) ScreenGrowth(c *gin.Context) {
	limit := 5000
	if v := strings.TrimSpace(c.Query("limit")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	if limit > 5000 {
		limit = 5000
	}

	offset := 0
	if v := strings.TrimSpace(c.Query("offset")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed >= 0 {
			offset = parsed
		}
	}

	symbolPrefix := strings.TrimSpace(c.Query("symbol_prefix"))
	if symbolPrefix != "" {
		symbolPrefix = strings.ToUpper(symbolPrefix)
	}

	onlyPass := false
	if v := strings.TrimSpace(c.Query("only_pass")); v != "" {
		onlyPass = strings.EqualFold(v, "1") || strings.EqualFold(v, "true") || strings.EqualFold(v, "yes")
	}

	presetID := strings.TrimSpace(c.Query("preset_id"))
	presetMaxMC := 0.0
	if v, ok := presetMaxMarketCap(presetID); ok {
		presetMaxMC = v
	}

	minMarketCap := 5e9
	if v := strings.TrimSpace(c.Query("min_market_cap")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minMarketCap = parsed
		}
	}

	minRevenueGrowthPct := 15.0
	if v := strings.TrimSpace(c.Query("min_revenue_growth_yoy_pct")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minRevenueGrowthPct = parsed
		}
	}

	minEarningsGrowthPct := 10.0
	if v := strings.TrimSpace(c.Query("min_earnings_growth_yoy_pct")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minEarningsGrowthPct = parsed
		}
	}

	minOperatingMarginPct := 10.0
	if v := strings.TrimSpace(c.Query("min_operating_margin_pct")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minOperatingMarginPct = parsed
		}
	}

	maxDebtToEquity := 1.5
	if v := strings.TrimSpace(c.Query("max_debt_to_equity")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			maxDebtToEquity = parsed
		}
	}

	allStocks, metaErr := loadAllStocksMeta(limit, offset, symbolPrefix)
	if metaErr != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": metaErr.Error()})
		return
	}

	symbols := make([]string, 0, len(allStocks))
	for _, s := range allStocks {
		if s.Symbol == "" {
			continue
		}
		symbols = append(symbols, s.Symbol)
	}

	snapshots, err := h.marketDataRepo.ListLatestFundamentalsSnapshotsForSymbols(symbols)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	latestBySymbol := map[string]map[string]interface{}{}
	asOfBySymbol := map[string]string{}
	for _, r := range snapshots {
		sym, _ := r["symbol"].(string)
		sym = strings.TrimSpace(strings.ToUpper(sym))
		if sym == "" {
			continue
		}
		payload, _ := r["payload"].(map[string]interface{})
		payload = payloadOrEmpty(payload)
		latestBySymbol[sym] = payload
		if asOf, ok := r["as_of_date"].(string); ok {
			asOfBySymbol[sym] = asOf
		}
	}

	results := make([]gin.H, 0)
	for _, meta := range allStocks {
		sym := strings.TrimSpace(strings.ToUpper(meta.Symbol))
		if sym == "" {
			continue
		}
		payload := latestBySymbol[sym]
		payload = payloadOrEmpty(payload)

		marketCap := firstFloat(meta.MarketCap, getFloat(payload, []string{"marketCap", "market_cap"}))
		revGrowthPct := normalizePct(getFloat(payload, []string{"revenueGrowthYoY", "revenue_growth_yoy", "revenueGrowth", "revenue_growth", "revenue_growth_yoy_pct", "revenue_growth_pct"}))
		earnGrowthPct := normalizePct(getFloat(payload, []string{"earningsGrowth", "earnings_growth", "earnings_growth_yoy", "earnings_growth_yoy_pct"}))
		opMarginPct := normalizePct(getFloat(payload, []string{"operatingMargin", "operating_margin"}))
		debtToEquity := getFloat(payload, []string{"debtToEquity", "debt_to_equity"})
		pe := getFloat(payload, []string{"peRatio", "pe_ratio", "priceEarningsRatio"})

		missing := 0
		if marketCap == nil {
			missing++
		}
		if revGrowthPct == nil {
			missing++
		}
		if earnGrowthPct == nil {
			missing++
		}
		if opMarginPct == nil {
			missing++
		}
		if debtToEquity == nil {
			missing++
		}

		pass := true
		if marketCap == nil || *marketCap < minMarketCap {
			pass = false
		}
		if presetMaxMC > 0 && marketCap != nil && *marketCap > presetMaxMC {
			pass = false
		}
		if revGrowthPct == nil || *revGrowthPct < minRevenueGrowthPct {
			pass = false
		}
		if earnGrowthPct == nil || *earnGrowthPct < minEarningsGrowthPct {
			pass = false
		}
		if opMarginPct == nil || *opMarginPct < minOperatingMarginPct {
			pass = false
		}
		if debtToEquity == nil || *debtToEquity > maxDebtToEquity {
			pass = false
		}

		if onlyPass && !pass {
			continue
		}

		results = append(results, gin.H{
			"symbol":                     sym,
			"sector":                     meta.Sector,
			"industry":                   meta.Industry,
			"market_cap":                 marketCap,
			"fundamentals_as_of":         asOfBySymbol[sym],
			"revenue_growth_yoy_pct":     revGrowthPct,
			"earnings_growth_yoy_pct":    earnGrowthPct,
			"operating_margin_pct":       opMarginPct,
			"debt_to_equity":             debtToEquity,
			"pe_ratio":                   pe,
			"missing_required_fields":    missing,
			"pass":                       pass,
			"screen_profile":             "growth",
			"screen_min_market_cap":      minMarketCap,
			"screen_min_rev_growth_pct":  minRevenueGrowthPct,
			"screen_min_earn_growth_pct": minEarningsGrowthPct,
			"screen_min_op_margin_pct":   minOperatingMarginPct,
			"screen_max_debt_to_equity":  maxDebtToEquity,
			"only_pass":                  onlyPass,
		})
	}

	shortDesc, longDesc := screenerDescriptions("growth")
	results = h.maybeEnrichWithPresetScores(c, results)
	c.JSON(http.StatusOK, gin.H{
		"success":                   true,
		"profile":                   "growth",
		"profile_description_short": shortDesc,
		"profile_description_long":  longDesc,
		"count":                     len(results),
		"results":                   results,
		"limit":                     limit,
		"offset":                    offset,
		"symbol_prefix":             symbolPrefix,
	})
}

func (h *FundamentalsScreenerHandler) ScreenGarp(c *gin.Context) {
	limit := 5000
	if v := strings.TrimSpace(c.Query("limit")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	if limit > 5000 {
		limit = 5000
	}

	offset := 0
	if v := strings.TrimSpace(c.Query("offset")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed >= 0 {
			offset = parsed
		}
	}

	symbolPrefix := strings.TrimSpace(c.Query("symbol_prefix"))
	if symbolPrefix != "" {
		symbolPrefix = strings.ToUpper(symbolPrefix)
	}

	onlyPass := false
	if v := strings.TrimSpace(c.Query("only_pass")); v != "" {
		onlyPass = strings.EqualFold(v, "1") || strings.EqualFold(v, "true") || strings.EqualFold(v, "yes")
	}

	minMarketCap := 5e9
	if v := strings.TrimSpace(c.Query("min_market_cap")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minMarketCap = parsed
		}
	}

	minRevenueGrowthPct := 10.0
	if v := strings.TrimSpace(c.Query("min_revenue_growth_yoy_pct")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minRevenueGrowthPct = parsed
		}
	}

	minOperatingMarginPct := 10.0
	if v := strings.TrimSpace(c.Query("min_operating_margin_pct")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minOperatingMarginPct = parsed
		}
	}

	minRuleOf40 := 40.0
	if v := strings.TrimSpace(c.Query("min_rule_of_40")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minRuleOf40 = parsed
		}
	}

	maxPEG := 2.5
	if v := strings.TrimSpace(c.Query("max_peg")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			maxPEG = parsed
		}
	}

	maxPE := 35.0
	if v := strings.TrimSpace(c.Query("max_pe")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			maxPE = parsed
		}
	}

	maxDebtToEquity := 1.5
	if v := strings.TrimSpace(c.Query("max_debt_to_equity")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			maxDebtToEquity = parsed
		}
	}

	allStocks, metaErr := loadAllStocksMeta(limit, offset, symbolPrefix)
	if metaErr != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": metaErr.Error()})
		return
	}

	symbols := make([]string, 0, len(allStocks))
	for _, s := range allStocks {
		if s.Symbol == "" {
			continue
		}
		symbols = append(symbols, s.Symbol)
	}

	snapshots, err := h.marketDataRepo.ListLatestFundamentalsSnapshotsForSymbols(symbols)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	latestBySymbol := map[string]map[string]interface{}{}
	asOfBySymbol := map[string]string{}
	for _, r := range snapshots {
		sym, _ := r["symbol"].(string)
		sym = strings.TrimSpace(strings.ToUpper(sym))
		if sym == "" {
			continue
		}
		payload, _ := r["payload"].(map[string]interface{})
		payload = payloadOrEmpty(payload)
		latestBySymbol[sym] = payload
		if asOf, ok := r["as_of_date"].(string); ok {
			asOfBySymbol[sym] = asOf
		}
	}

	results := make([]gin.H, 0)
	for _, meta := range allStocks {
		sym := strings.TrimSpace(strings.ToUpper(meta.Symbol))
		if sym == "" {
			continue
		}
		payload := latestBySymbol[sym]
		payload = payloadOrEmpty(payload)

		marketCap := firstFloat(meta.MarketCap, getFloat(payload, []string{"marketCap", "market_cap"}))
		revGrowthPct := normalizePct(getFloat(payload, []string{"revenueGrowthYoY", "revenue_growth_yoy", "revenueGrowth", "revenue_growth", "revenue_growth_yoy_pct", "revenue_growth_pct"}))
		opMarginPct := normalizePct(getFloat(payload, []string{"operatingMargin", "operating_margin"}))
		debtToEquity := getFloat(payload, []string{"debtToEquity", "debt_to_equity"})
		pe := getFloat(payload, []string{"peRatio", "pe_ratio", "priceEarningsRatio"})
		peg := getFloat(payload, []string{"pegRatio", "peg_ratio"})

		var ruleOf40 *float64
		if revGrowthPct != nil && opMarginPct != nil {
			v := *revGrowthPct + *opMarginPct
			ruleOf40 = &v
		}

		missing := 0
		if marketCap == nil {
			missing++
		}
		if revGrowthPct == nil {
			missing++
		}
		if opMarginPct == nil {
			missing++
		}
		if debtToEquity == nil {
			missing++
		}
		if pe == nil {
			missing++
		}
		if peg == nil {
			missing++
		}
		if ruleOf40 == nil {
			missing++
		}

		pass := true
		if marketCap == nil || *marketCap < minMarketCap {
			pass = false
		}
		if revGrowthPct == nil || *revGrowthPct < minRevenueGrowthPct {
			pass = false
		}
		if opMarginPct == nil || *opMarginPct < minOperatingMarginPct {
			pass = false
		}
		if debtToEquity == nil || *debtToEquity > maxDebtToEquity {
			pass = false
		}
		if pe == nil || *pe <= 0 || *pe > maxPE {
			pass = false
		}
		if peg == nil || *peg <= 0 || *peg > maxPEG {
			pass = false
		}
		if ruleOf40 == nil || *ruleOf40 < minRuleOf40 {
			pass = false
		}

		if onlyPass && !pass {
			continue
		}

		results = append(results, gin.H{
			"symbol":                    sym,
			"sector":                    meta.Sector,
			"industry":                  meta.Industry,
			"market_cap":                marketCap,
			"fundamentals_as_of":        asOfBySymbol[sym],
			"revenue_growth_yoy_pct":    revGrowthPct,
			"operating_margin_pct":      opMarginPct,
			"rule_of_40":                ruleOf40,
			"debt_to_equity":            debtToEquity,
			"pe_ratio":                  pe,
			"peg_ratio":                 peg,
			"missing_required_fields":   missing,
			"pass":                      pass,
			"screen_profile":            "garp",
			"screen_min_market_cap":     minMarketCap,
			"screen_min_rev_growth_pct": minRevenueGrowthPct,
			"screen_min_op_margin_pct":  minOperatingMarginPct,
			"screen_min_rule_of_40":     minRuleOf40,
			"screen_max_pe":             maxPE,
			"screen_max_peg":            maxPEG,
			"screen_max_debt_to_equity": maxDebtToEquity,
			"only_pass":                 onlyPass,
		})
	}

	shortDesc, longDesc := screenerDescriptions("garp")
	results = h.maybeEnrichWithPresetScores(c, results)
	c.JSON(http.StatusOK, gin.H{
		"success":                   true,
		"profile":                   "garp",
		"profile_description_short": shortDesc,
		"profile_description_long":  longDesc,
		"count":                     len(results),
		"results":                   results,
		"limit":                     limit,
		"offset":                    offset,
		"symbol_prefix":             symbolPrefix,
	})
}

func (h *FundamentalsScreenerHandler) ScreenInflection(c *gin.Context) {
	limit := 5000
	if v := strings.TrimSpace(c.Query("limit")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	if limit > 5000 {
		limit = 5000
	}

	offset := 0
	if v := strings.TrimSpace(c.Query("offset")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed >= 0 {
			offset = parsed
		}
	}

	symbolPrefix := strings.TrimSpace(c.Query("symbol_prefix"))
	if symbolPrefix != "" {
		symbolPrefix = strings.ToUpper(symbolPrefix)
	}

	onlyPass := false
	if v := strings.TrimSpace(c.Query("only_pass")); v != "" {
		onlyPass = strings.EqualFold(v, "1") || strings.EqualFold(v, "true") || strings.EqualFold(v, "yes")
	}

	presetID := strings.TrimSpace(c.Query("preset_id"))
	presetMaxMC := 0.0
	if v, ok := presetMaxMarketCap(presetID); ok {
		presetMaxMC = v
	}

	minMarketCap := 2e9
	if v := strings.TrimSpace(c.Query("min_market_cap")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minMarketCap = parsed
		}
	}

	maxDebtToEquity := 2.5
	if v := strings.TrimSpace(c.Query("max_debt_to_equity")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			maxDebtToEquity = parsed
		}
	}

	minPeriods := 3
	if v := strings.TrimSpace(c.Query("min_periods")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed >= 1 {
			minPeriods = parsed
		}
	}

	minScore := 60.0
	if v := strings.TrimSpace(c.Query("min_score")); v != "" {
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			minScore = parsed
		}
	}

	allStocks, metaErr := loadAllStocksMeta(limit, offset, symbolPrefix)
	if metaErr != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": metaErr.Error()})
		return
	}

	symbols := make([]string, 0, len(allStocks))
	for _, s := range allStocks {
		if s.Symbol == "" {
			continue
		}
		symbols = append(symbols, s.Symbol)
	}

	snapshots, err := h.marketDataRepo.ListBestFundamentalsSnapshotsForSymbolsPreferStatements(symbols, minPeriods)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	latestBySymbol := map[string]map[string]interface{}{}
	asOfBySymbol := map[string]string{}
	for _, r := range snapshots {
		sym, _ := r["symbol"].(string)
		sym = strings.TrimSpace(strings.ToUpper(sym))
		if sym == "" {
			continue
		}
		payload, _ := r["payload"].(map[string]interface{})
		payload = payloadOrEmpty(payload)
		latestBySymbol[sym] = payload
		if asOf, ok := r["as_of_date"].(string); ok {
			asOfBySymbol[sym] = asOf
		}
	}

	results := make([]gin.H, 0)
	for _, meta := range allStocks {
		sym := strings.TrimSpace(strings.ToUpper(meta.Symbol))
		if sym == "" {
			continue
		}
		payload := latestBySymbol[sym]
		payload = payloadOrEmpty(payload)

		marketCap := firstFloat(meta.MarketCap, getFloat(payload, []string{"marketCap", "market_cap"}))
		debtToEquity := getFloat(payload, []string{"debtToEquity", "debt_to_equity"})
		incomeSeries := extractIncomeStatementSeries(payload)
		periodsUsed := len(incomeSeries)

		reasons := make([]string, 0)
		missing := 0
		if marketCap == nil {
			missing++
			reasons = append(reasons, "MISSING_MARKET_CAP")
		}
		if debtToEquity == nil {
			missing++
			reasons = append(reasons, "MISSING_DEBT_TO_EQUITY")
		}
		if periodsUsed < minPeriods {
			missing++
			reasons = append(reasons, "INSUFFICIENT_STATEMENT_HISTORY")
		}

		var revGrowthFromStatementsPct *float64
		var revGrowthAccelPct *float64
		var grossMarginLatestPct *float64
		var opMarginLatestPct *float64
		var grossMarginDeltaPct *float64
		var opMarginDeltaPct *float64
		var rndPct *float64
		var sgaPct *float64

		if periodsUsed >= 2 {
			latest := incomeSeries[0]
			oldest := incomeSeries[periodsUsed-1]

			if latest.Revenue != nil && oldest.Revenue != nil && *oldest.Revenue != 0 {
				g := ((*latest.Revenue / *oldest.Revenue) - 1.0) * 100.0
				revGrowthFromStatementsPct = safeFloatPtr(g)
			}

			grossMarginLatestPct = pct(latest.GrossProfit, latest.Revenue)
			opMarginLatestPct = pct(latest.OperatingIncome, latest.Revenue)
			gmOld := pct(oldest.GrossProfit, oldest.Revenue)
			opOld := pct(oldest.OperatingIncome, oldest.Revenue)

			if grossMarginLatestPct != nil && gmOld != nil {
				d := *grossMarginLatestPct - *gmOld
				grossMarginDeltaPct = safeFloatPtr(d)
			}
			if opMarginLatestPct != nil && opOld != nil {
				d := *opMarginLatestPct - *opOld
				opMarginDeltaPct = safeFloatPtr(d)
			}

			if latest.ResearchAndDevelopment != nil && latest.Revenue != nil && *latest.Revenue != 0 {
				v := (*latest.ResearchAndDevelopment / *latest.Revenue) * 100.0
				rndPct = safeFloatPtr(v)
			}
			if latest.SellingGeneralAdministrative != nil && latest.Revenue != nil && *latest.Revenue != 0 {
				v := (*latest.SellingGeneralAdministrative / *latest.Revenue) * 100.0
				sgaPct = safeFloatPtr(v)
			}
		}

		if periodsUsed >= 3 {
			g1 := growthPct(incomeSeries[0].Revenue, incomeSeries[1].Revenue)
			g2 := growthPct(incomeSeries[1].Revenue, incomeSeries[2].Revenue)
			if g1 != nil && g2 != nil {
				v := *g1 - *g2
				revGrowthAccelPct = safeFloatPtr(v)
			}
		}

		score, scoreReasons := scoreInflection(revGrowthFromStatementsPct, revGrowthAccelPct, grossMarginDeltaPct, opMarginDeltaPct, rndPct)
		reasons = append(reasons, scoreReasons...)

		pass := true
		if marketCap == nil || *marketCap < minMarketCap {
			pass = false
		}
		if presetMaxMC > 0 && marketCap != nil && *marketCap > presetMaxMC {
			pass = false
		}
		if debtToEquity == nil || *debtToEquity > maxDebtToEquity {
			pass = false
		}
		if periodsUsed < minPeriods {
			pass = false
		}
		if score < minScore {
			pass = false
		}

		if onlyPass && !pass {
			continue
		}

		results = append(results, gin.H{
			"symbol":                             sym,
			"sector":                             meta.Sector,
			"industry":                           meta.Industry,
			"market_cap":                         marketCap,
			"fundamentals_as_of":                 asOfBySymbol[sym],
			"debt_to_equity":                     debtToEquity,
			"periods_used":                       periodsUsed,
			"revenue_growth_from_statements_pct": revGrowthFromStatementsPct,
			"revenue_growth_accel_pct":           revGrowthAccelPct,
			"gross_margin_latest_pct":            grossMarginLatestPct,
			"operating_margin_latest_pct":        opMarginLatestPct,
			"gross_margin_delta_pct":             grossMarginDeltaPct,
			"operating_margin_delta_pct":         opMarginDeltaPct,
			"rnd_pct":                            rndPct,
			"sga_pct":                            sgaPct,
			"inflection_score":                   score,
			"reason_codes":                       reasons,
			"missing_required_fields":            missing,
			"pass":                               pass,
			"screen_profile":                     "inflection",
			"screen_min_market_cap":              minMarketCap,
			"screen_max_debt_to_equity":          maxDebtToEquity,
			"screen_min_periods":                 minPeriods,
			"screen_min_score":                   minScore,
			"only_pass":                          onlyPass,
		})
	}

	shortDesc, longDesc := screenerDescriptions("inflection")
	results = h.maybeEnrichWithPresetScores(c, results)
	c.JSON(http.StatusOK, gin.H{
		"success":                   true,
		"profile":                   "inflection",
		"profile_description_short": shortDesc,
		"profile_description_long":  longDesc,
		"count":                     len(results),
		"results":                   results,
		"limit":                     limit,
		"offset":                    offset,
		"symbol_prefix":             symbolPrefix,
	})
}

func extractIncomeStatementSeries(payload map[string]interface{}) []incomeStatementRow {
	raw, ok := payload["income_statement"]
	if !ok || raw == nil {
		return nil
	}

	arr, ok := raw.([]interface{})
	if !ok || len(arr) == 0 {
		return nil
	}

	out := make([]incomeStatementRow, 0, len(arr))
	for _, item := range arr {
		m, ok := item.(map[string]interface{})
		if !ok || m == nil {
			continue
		}

		ds, _ := m["date"].(string)
		ds = strings.TrimSpace(ds)
		if ds == "" {
			continue
		}

		dt, err := time.Parse("2006-01-02", ds)
		if err != nil {
			continue
		}

		row := incomeStatementRow{
			Date:                         dt,
			Revenue:                      getFloat(m, []string{"revenue", "Revenue"}),
			GrossProfit:                  getFloat(m, []string{"grossProfit", "gross_profit"}),
			OperatingIncome:              getFloat(m, []string{"operatingIncome", "operating_income"}),
			ResearchAndDevelopment:       getFloat(m, []string{"researchAndDevelopmentExpenses", "research_and_development_expenses", "researchAndDevelopment"}),
			SellingGeneralAdministrative: getFloat(m, []string{"sellingGeneralAndAdministrativeExpenses", "selling_general_and_administrative_expenses", "sellingGeneralAndAdministrative"}),
		}
		out = append(out, row)
	}

	if len(out) <= 1 {
		return out
	}

	sort.Slice(out, func(i, j int) bool {
		return out[i].Date.After(out[j].Date)
	})

	return out
}

func safeFloatPtr(v float64) *float64 {
	if math.IsNaN(v) || math.IsInf(v, 0) {
		return nil
	}
	vv := v
	return &vv
}

func pct(numerator *float64, denominator *float64) *float64 {
	if numerator == nil || denominator == nil {
		return nil
	}
	if *denominator == 0 {
		return nil
	}
	v := (*numerator / *denominator) * 100.0
	return safeFloatPtr(v)
}

func growthPct(latest *float64, prev *float64) *float64 {
	if latest == nil || prev == nil {
		return nil
	}
	if *prev == 0 {
		return nil
	}
	v := ((*latest / *prev) - 1.0) * 100.0
	return safeFloatPtr(v)
}

func scoreInflection(
	revGrowthPct *float64,
	revGrowthAccelPct *float64,
	grossMarginDeltaPct *float64,
	opMarginDeltaPct *float64,
	rndPct *float64,
) (float64, []string) {
	score := 0.0
	reasons := make([]string, 0)

	// Growth level (0-35)
	if revGrowthPct == nil {
		reasons = append(reasons, "MISSING_REVENUE_GROWTH")
	} else {
		g := *revGrowthPct
		switch {
		case g <= 0:
			score += 0
		case g < 10:
			score += 10
		case g < 25:
			score += 20
		case g < 50:
			score += 28
		default:
			score += 35
		}
	}

	// Acceleration (0-15)
	if revGrowthAccelPct != nil && *revGrowthAccelPct > 0 {
		score += 15
		reasons = append(reasons, "GROWTH_ACCELERATING")
	}

	// Margin trajectory (0-30)
	if grossMarginDeltaPct != nil {
		if *grossMarginDeltaPct >= 2 {
			score += 10
			reasons = append(reasons, "GROSS_MARGIN_EXPANDING")
		} else if *grossMarginDeltaPct > 0 {
			score += 5
		}
	}
	if opMarginDeltaPct != nil {
		if *opMarginDeltaPct >= 5 {
			score += 20
			reasons = append(reasons, "OPERATING_LEVERAGE")
		} else if *opMarginDeltaPct > 0 {
			score += 10
		}
	}

	// Reinvestment (0-20)
	if rndPct != nil {
		r := *rndPct
		if r >= 5 && r <= 25 {
			score += 20
			reasons = append(reasons, "MEANINGFUL_RND")
		} else if r > 0 {
			score += 10
		}
	}

	if score > 100 {
		score = 100
	}

	return score, reasons
}

func loadAllStocksMeta(limit int, offset int, symbolPrefix string) ([]stockMeta, error) {
	lim := limit
	if lim <= 0 {
		lim = 5000
	}
	if lim > 5000 {
		lim = 5000
	}

	off := offset
	if off < 0 {
		off = 0
	}

	prefix := strings.TrimSpace(symbolPrefix)
	if prefix != "" {
		prefix = strings.ToUpper(prefix)
	}

	orderBy := "ORDER BY UPPER(symbol)"
	if prefix == "" {
		orderBy = "ORDER BY market_cap::double precision DESC NULLS LAST, UPPER(symbol)"
	}

	query := `
		SELECT UPPER(symbol) AS symbol, sector, industry, market_cap::double precision
		FROM stocks
		WHERE symbol IS NOT NULL
		  AND BTRIM(symbol) <> ''
		  AND BTRIM(symbol) ~ '^[A-Za-z]'
		  AND ($1 = '' OR UPPER(symbol) LIKE ($1 || '%'))
		` + orderBy + `
		LIMIT $2
		OFFSET $3
	`

	rows, err := database.DB.Query(query, prefix, lim, off)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := make([]stockMeta, 0, lim)
	for rows.Next() {
		var sym string
		var sector, industry sql.NullString
		var mc sql.NullFloat64
		if err := rows.Scan(&sym, &sector, &industry, &mc); err != nil {
			continue
		}
		sm := stockMeta{Symbol: sym}
		if sector.Valid {
			v := sector.String
			sm.Sector = &v
		}
		if industry.Valid {
			v := industry.String
			sm.Industry = &v
		}
		if mc.Valid {
			v := mc.Float64
			sm.MarketCap = &v
		}
		out = append(out, sm)
	}
	return out, nil
}

func payloadOrEmpty(m map[string]interface{}) map[string]interface{} {
	if m == nil {
		return map[string]interface{}{}
	}
	return m
}

func getFloat(m map[string]interface{}, keys []string) *float64 {
	for _, k := range keys {
		v, ok := m[k]
		if !ok {
			continue
		}
		switch t := v.(type) {
		case float64:
			vv := t
			return &vv
		case float32:
			vv := float64(t)
			return &vv
		case int:
			vv := float64(t)
			return &vv
		case int64:
			vv := float64(t)
			return &vv
		case json.Number:
			if f, err := t.Float64(); err == nil {
				vv := f
				return &vv
			}
		case string:
			if f, err := strconv.ParseFloat(strings.TrimSpace(t), 64); err == nil {
				vv := f
				return &vv
			}
		}
	}
	return nil
}

func normalizePct(v *float64) *float64 {
	if v == nil {
		return nil
	}
	vv := *v
	if vv > -1.0 && vv < 1.0 {
		vv = vv * 100.0
	}
	return &vv
}

func firstFloat(a *float64, b *float64) *float64 {
	if a != nil {
		return a
	}
	return b
}
