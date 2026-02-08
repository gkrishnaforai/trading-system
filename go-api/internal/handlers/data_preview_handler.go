package handlers

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/services"
)

type DataPreviewHandler struct {
	svc *services.DataPreviewService
}

func NewDataPreviewHandler(svc *services.DataPreviewService) *DataPreviewHandler {
	return &DataPreviewHandler{svc: svc}
}

func (h *DataPreviewHandler) GetPreview(c *gin.Context) {
	symbol := c.Query("symbol")
	dataType := c.Query("data_type")

	limit := 50
	if v := c.Query("limit"); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil {
			limit = parsed
		}
	}

	offset := 0
	if v := c.Query("offset"); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil {
			offset = parsed
		}
	}

	allColumns := false
	if v := strings.ToLower(strings.TrimSpace(c.Query("all_columns"))); v != "" {
		if v == "true" || v == "1" || v == "yes" {
			allColumns = true
		}
	}

	resp, err := h.svc.GetPreview(c.Request.Context(), symbol, dataType, limit, offset, allColumns)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, resp)
}
