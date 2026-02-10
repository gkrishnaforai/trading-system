package handlers

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/services"
)

type SchedulerTickHandler struct {
	svc *services.SchedulerService
}

func NewSchedulerTickHandler(svc *services.SchedulerService) *SchedulerTickHandler {
	return &SchedulerTickHandler{svc: svc}
}

func (h *SchedulerTickHandler) Tick(c *gin.Context) {
	limit := 25
	if v := c.Query("limit"); v != "" {
		if parsed, err := parseInt(v); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	resp, err := h.svc.Tick(c.Request.Context(), time.Now().UTC(), limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, resp)
}
