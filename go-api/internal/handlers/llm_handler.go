package handlers

import (
	"database/sql"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/database"
)

type LLMHandler struct {
	db *sql.DB
}

func NewLLMHandler() *LLMHandler {
	return &LLMHandler{
		db: database.DB,
	}
}

// GetLLMBlog handles GET /api/v1/llm_blog/:symbol
func (h *LLMHandler) GetLLMBlog(c *gin.Context) {
	symbol := c.Param("symbol")

	query := `
		SELECT generated_content
		FROM llm_generated_reports
		WHERE stock_symbol = ? AND report_type = 'blog_post'
		ORDER BY timestamp DESC
		LIMIT 1
	`

	var content string
	err := h.db.QueryRow(query, symbol).Scan(&content)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Report not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"symbol": symbol,
		"content": content,
	})
}

