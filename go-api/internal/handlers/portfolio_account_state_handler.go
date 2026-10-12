package handlers

import (
	"net/http"
	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/repositories"
)

type PortfolioAccountStateHandler struct{ repo *repositories.PortfolioAccountStateRepository }
func NewPortfolioAccountStateHandler(repo *repositories.PortfolioAccountStateRepository) *PortfolioAccountStateHandler { return &PortfolioAccountStateHandler{repo: repo} }

func (h *PortfolioAccountStateHandler) Latest(c *gin.Context) {
	state, err := h.repo.Latest(c.Param("portfolio_id"))
	if err != nil { c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()}); return }
	c.JSON(http.StatusOK, state)
}

func (h *PortfolioAccountStateHandler) Save(c *gin.Context) {
	var values map[string]any
	if err := c.ShouldBindJSON(&values); err != nil { c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()}); return }
	state, err := h.repo.Save(c.Param("portfolio_id"), values)
	if err != nil { c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()}); return }
	c.JSON(http.StatusCreated, state)
}
