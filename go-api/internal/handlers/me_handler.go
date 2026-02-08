package handlers

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/trading-system/go-api/internal/repositories"
)

type MeHandler struct {
	userRepo *repositories.UserRepository
}

func NewMeHandler(userRepo *repositories.UserRepository) *MeHandler {
	return &MeHandler{userRepo: userRepo}
}

func getUserIDFromRequest(c *gin.Context) (string, bool) {
	userID := strings.TrimSpace(c.GetHeader("X-User-Id"))
	if userID == "" {
		return "", false
	}
	if _, err := uuid.Parse(userID); err != nil {
		return "", false
	}
	return userID, true
}

// GetMe handles GET /api/v1/me
func (h *MeHandler) GetMe(c *gin.Context) {
	userID, ok := getUserIDFromRequest(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "missing or invalid X-User-Id header"})
		return
	}

	user, err := h.userRepo.GetByID(userID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, user)
}

type UpdateMeRequest struct {
	Email *string `json:"email"`
}

// UpdateMe handles PATCH /api/v1/me
func (h *MeHandler) UpdateMe(c *gin.Context) {
	userID, ok := getUserIDFromRequest(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "missing or invalid X-User-Id header"})
		return
	}

	var req UpdateMeRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if req.Email == nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "email is required"})
		return
	}
	email := strings.TrimSpace(*req.Email)
	if email == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "email must not be empty"})
		return
	}

	updated, err := h.userRepo.UpdateEmail(userID, email)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, updated)
}
