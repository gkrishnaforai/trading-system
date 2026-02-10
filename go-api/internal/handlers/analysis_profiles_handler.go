package handlers

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/services"
)

type AnalysisProfilesHandler struct{}

func NewAnalysisProfilesHandler() *AnalysisProfilesHandler {
	return &AnalysisProfilesHandler{}
}

// GET /api/v1/admin/analysis-profiles
func (h *AnalysisProfilesHandler) GetProfiles(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"profiles": services.AnalysisProfilesAsMap()})
}
