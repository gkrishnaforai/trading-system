package models

type DataPreviewResponse struct {
	Symbol   string           `json:"symbol"`
	DataType string           `json:"data_type"`
	Limit    int              `json:"limit"`
	Offset   int              `json:"offset"`
	Count    int              `json:"count"`
	Rows     []map[string]any `json:"rows"`
}
