# Blog Publishing Integration

## Overview

Stock reports are stored in the database and can be automatically published to blog sites using LLM or n8n workflows.

## Database Schema

Reports are stored in the `llm_generated_reports` table:

```sql
CREATE TABLE llm_generated_reports (
    report_id TEXT PRIMARY KEY,
    portfolio_id TEXT,
    stock_symbol TEXT,
    generated_content TEXT,  -- JSON format
    report_type TEXT,
    timestamp TIMESTAMP
);
```

## Report Format

Each report is stored as JSON with the following structure:

```json
{
  "symbol": "AAPL",
  "generated_at": "2025-12-21T21:00:00",
  "summary": "Simple layman-friendly summary",
  "trend_status": {
    "short_term": "✅ Bullish - EMA20 vs EMA50",
    "medium_term": "✅ Bullish - Medium-term trend",
    "long_term": "✅ Bullish - Long-term trend (Price vs SMA200)"
  },
  "signal_clarity": {
    "signal": "BUY",
    "confidence": "75%",
    "why": "Technical explanation...",
    "action": "Consider buying on pullback",
    "key_factors": ["✅ Long-term trend is bullish", ...]
  },
  "technical_analysis": {...},
  "risk_assessment": {...},
  "recommendation": {...},
  "llm_narrative": "AI-generated narrative (if available)"
}
```

## API Endpoints

### Get Report for Symbol
```bash
GET /api/v1/report/:symbol
```

Returns the latest report for a symbol.

### List All Reports
```bash
GET /api/v1/reports?limit=50
```

Returns list of all available reports.

## Using with n8n Workflow

### Step 1: Query Reports

Create an HTTP Request node in n8n:
- Method: GET
- URL: `http://your-api:8000/api/v1/reports?limit=10`
- Authentication: If needed

### Step 2: Filter New Reports

Use a Function node to filter reports by timestamp:
```javascript
// Filter reports from last 24 hours
const oneDayAgo = new Date();
oneDayAgo.setDate(oneDayAgo.getDate() - 1);

return items.filter(item => {
  const reportTime = new Date(item.json.timestamp);
  return reportTime > oneDayAgo;
});
```

### Step 3: Format for Blog

Use a Function node to format the report:
```javascript
const report = JSON.parse(item.json.generated_content);

return [{
  json: {
    title: `${report.symbol} Stock Analysis - ${report.recommendation.action} Signal`,
    content: `
# ${report.symbol} Stock Analysis

## Summary
${report.summary}

## Trend Status
- **Short-term:** ${report.trend_status.short_term}
- **Medium-term:** ${report.trend_status.medium_term}
- **Long-term:** ${report.trend_status.long_term}

## Signal: ${report.signal_clarity.signal}
**Confidence:** ${report.signal_clarity.confidence}
**Why:** ${report.signal_clarity.why}
**Action:** ${report.signal_clarity.action}

## Recommendation
${report.recommendation.action} - ${report.recommendation.reasoning}

${report.llm_narrative || ''}
    `,
    tags: ['stock-analysis', report.symbol.toLowerCase(), 'trading'],
    category: 'Stock Analysis',
    published: true
  }
}];
```

### Step 4: Publish to Blog Platform

Use appropriate node for your blog platform:
- WordPress: Use WordPress node
- Medium: Use HTTP Request with Medium API
- Ghost: Use Ghost node
- Custom: Use HTTP Request with your API

## Using with LLM for Blog Post Generation

### Example: Generate Blog Post from Report

```python
from app.database import db
from app.llm.agent import LLMAgent
import json

# Get report from database
query = """
    SELECT generated_content
    FROM llm_generated_reports
    WHERE stock_symbol = ? AND report_type = 'stock_analysis'
    ORDER BY timestamp DESC
    LIMIT 1
"""

result = db.execute_query(query, {"symbol": "AAPL"})
if result:
    report = json.loads(result[0]['generated_content'])
    
    # Generate blog post using LLM
    llm_agent = LLMAgent()
    
    prompt = f"""
    Convert this stock analysis report into a professional blog post:
    
    {json.dumps(report, indent=2)}
    
    Requirements:
    - Engaging title
    - SEO-friendly content
    - Clear sections with headers
    - Include key metrics and recommendations
    - Professional tone
    - 800-1200 words
    """
    
    blog_post = llm_agent.generate_stock_analysis(
        report['symbol'],
        report,
        market_data=None
    )
    
    # Save blog post
    # ... publish to your blog platform
```

## Scheduled Publishing

### Option 1: n8n Cron Trigger

Set up a cron trigger in n8n to run daily:
- Schedule: `0 2 * * *` (2 AM daily)
- Query new reports
- Format and publish

### Option 2: Python Script

Create a scheduled script:

```python
# scripts/publish_reports.py
from app.services.report_generator import ReportGenerator
from app.database import db
import json
from datetime import datetime, timedelta

def publish_new_reports():
    """Publish reports from last 24 hours"""
    one_day_ago = datetime.now() - timedelta(days=1)
    
    query = """
        SELECT report_id, stock_symbol, generated_content, timestamp
        FROM llm_generated_reports
        WHERE report_type = 'stock_analysis'
        AND timestamp > ?
        ORDER BY timestamp DESC
    """
    
    reports = db.execute_query(query, {"timestamp": one_day_ago})
    
    for report_data in reports:
        report = json.loads(report_data['generated_content'])
        # Format and publish
        publish_to_blog(report)

if __name__ == "__main__":
    publish_new_reports()
```

## Report Types

- `stock_analysis`: Individual stock analysis report
- `portfolio_analysis`: Portfolio-level report
- `signal_explanation`: Signal explanation report
- `blog_post`: Formatted blog post ready for publishing

## Best Practices

1. **Filter by Timestamp**: Only publish new reports
2. **Format Consistently**: Use templates for consistent blog format
3. **Add Metadata**: Include tags, categories, SEO keywords
4. **Error Handling**: Handle API failures gracefully
5. **Rate Limiting**: Respect blog platform rate limits
6. **Content Review**: Optionally review before publishing

## Example n8n Workflow

```
1. Cron Trigger (Daily 2 AM)
   ↓
2. HTTP Request (GET /api/v1/reports)
   ↓
3. Filter (Last 24 hours)
   ↓
4. Function (Format report)
   ↓
5. HTTP Request (POST to blog API)
   ↓
6. Notification (Success/Failure)
```

## Integration Examples

### WordPress
```javascript
// n8n Function node
return [{
  json: {
    title: report.title,
    content: report.content,
    status: 'publish',
    categories: [5], // Stock Analysis category ID
    tags: report.tags
  }
}];
```

### Medium
```javascript
// n8n HTTP Request
{
  method: 'POST',
  url: 'https://api.medium.com/v1/posts',
  headers: {
    'Authorization': 'Bearer YOUR_TOKEN',
    'Content-Type': 'application/json'
  },
  body: {
    title: report.title,
    contentFormat: 'html',
    content: report.content,
    publishStatus: 'public'
  }
}
```

## Monitoring

Track published reports:
- Add `published` flag to reports table
- Log publishing attempts
- Monitor success/failure rates
- Track blog engagement metrics

