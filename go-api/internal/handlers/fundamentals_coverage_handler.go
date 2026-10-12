package handlers

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/database"
)

type FundamentalsCoverageHandler struct{}

func NewFundamentalsCoverageHandler() *FundamentalsCoverageHandler {
	return &FundamentalsCoverageHandler{}
}

func (h *FundamentalsCoverageHandler) Summary(c *gin.Context) {
	// Snapshot-level coverage summary (not symbol-level distinct)
	query := `
		SELECT
			COUNT(*) AS snapshots,
			COUNT(*) FILTER (WHERE payload IS NULL) AS payload_null,
			COUNT(*) FILTER (WHERE payload IS NOT NULL) AS payload_nonnull,
			COUNT(*) FILTER (WHERE jsonb_typeof(payload::jsonb->'income_statement') = 'array') AS income_statement_array,
			COUNT(*) FILTER (WHERE COALESCE(jsonb_array_length(payload::jsonb->'income_statement'), 0) = 0) AS income_statement_empty,
			COUNT(*) FILTER (WHERE COALESCE(jsonb_array_length(payload::jsonb->'income_statement'), 0) >= 1) AS income_statement_ge_1,
			COUNT(*) FILTER (WHERE COALESCE(jsonb_array_length(payload::jsonb->'income_statement'), 0) >= 3) AS income_statement_ge_3,
			COUNT(*) FILTER (WHERE COALESCE(jsonb_array_length(payload::jsonb->'income_statement'), 0) >= 5) AS income_statement_ge_5,
			COUNT(*) FILTER (
				WHERE COALESCE(jsonb_array_length(payload::jsonb->'income_statement'), 0) > 0
				  AND (payload::jsonb->'income_statement'->0 ? 'researchAndDevelopmentExpenses')
			) AS has_rnd_latest,
			COUNT(*) FILTER (
				WHERE COALESCE(jsonb_array_length(payload::jsonb->'income_statement'), 0) > 0
				  AND (payload::jsonb->'income_statement'->0 ? 'sellingGeneralAndAdministrativeExpenses')
			) AS has_sga_latest
		FROM fundamentals_snapshots;
	`

	var snapshots, payloadNull, payloadNonnull int64
	var incomeArray, incomeEmpty, incomeGe1, incomeGe3, incomeGe5 int64
	var hasRndLatest, hasSgaLatest int64

	row := database.DB.QueryRow(query)
	if err := row.Scan(
		&snapshots,
		&payloadNull,
		&payloadNonnull,
		&incomeArray,
		&incomeEmpty,
		&incomeGe1,
		&incomeGe3,
		&incomeGe5,
		&hasRndLatest,
		&hasSgaLatest,
	); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"snapshot_counts": gin.H{
			"total":               snapshots,
			"payload_null":        payloadNull,
			"payload_nonnull":     payloadNonnull,
			"income_statement_array": incomeArray,
			"income_statement_empty": incomeEmpty,
			"income_statement_ge_1":  incomeGe1,
			"income_statement_ge_3":  incomeGe3,
			"income_statement_ge_5":  incomeGe5,
			"has_rnd_latest":      hasRndLatest,
			"has_sga_latest":      hasSgaLatest,
		},
	})
}
