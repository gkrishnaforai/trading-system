package handlers

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

type LLMHandler struct {
}

func NewLLMHandler() *LLMHandler {
	return &LLMHandler{}
}

// GetLLMBlog handles GET /api/v1/llm_blog/:symbol
func (h *LLMHandler) GetLLMBlog(c *gin.Context) {
	symbol := c.Param("symbol")
	c.JSON(http.StatusOK, gin.H{
		"symbol":  symbol,
		"content": "",
		"message": "LLM blog content is not available yet under the normalized schema.",
	})
}
