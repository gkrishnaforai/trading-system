# Massive.com Data Provider Integration

## Overview

Massive.com (formerly Polygon.io) has been integrated as a configurable data provider alongside Yahoo Finance. This provides access to real-time and historical market data from all major U.S. stock exchanges.

## Features

- **Historical Price Data**: Daily OHLCV bars with high-quality data
- **Real-time Prices**: Last trade prices for live market data
- **Company Fundamentals**: Basic company information and metrics
- **News Articles**: Company-specific news from various publishers
- **Earnings Data**: Earnings calendar and history (partial implementation)
- **Industry Peers**: Sector and industry classification (partial implementation)

## Configuration

### Environment Variables

Add the following to your `.env` file:

```bash
# Massive.com API Key (required for Massive.com provider)
MASSIVE_API_KEY=zaWw3IMSljtZ9HNqjQrg0WR_XlMdvFQF

# Enable Massive.com provider (optional, default: false)
MASSIVE_ENABLED=true

# Default data provider (options: yahoo_finance, massive, fallback)
DEFAULT_DATA_PROVIDER=massive

# Rate limiting (optional, defaults shown)
MASSIVE_RATE_LIMIT_CALLS=4  # Calls per minute (default: 4)
MASSIVE_RATE_LIMIT_WINDOW=60.0  # Time window in seconds (default: 60)
```

### Getting an API Key

1. Sign up for an account at [Massive.com](https://massive.com)
2. Navigate to your API keys section
3. Copy your API key
4. Set it as the `MASSIVE_API_KEY` environment variable

## Usage

### Programmatic Selection

```python
from app.data_sources import get_data_source

# Use configured default provider
data_source = get_data_source()

# Or explicitly select Massive.com
data_source = get_data_source("massive")

# Fetch data
price_data = data_source.fetch_price_data("AAPL", period="1y")
current_price = data_source.fetch_current_price("AAPL")
fundamentals = data_source.fetch_fundamentals("AAPL")
news = data_source.fetch_news("AAPL", limit=10)
```

### Configuration-Based Selection

The system will automatically use the provider specified in `DEFAULT_DATA_PROVIDER`:

- `yahoo_finance`: Yahoo Finance (default, no API key required)
- `massive`: Massive.com (requires API key)
- `fallback`: Automatic failover between Yahoo Finance and Finnhub

## API Coverage

### Fully Implemented

✅ **Price Data** (`fetch_price_data`)

- Historical daily bars
- Supports multiple periods (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y)
- High-quality data from all major U.S. exchanges

✅ **Current Price** (`fetch_current_price`)

- Real-time last trade price
- Fallback to latest daily bar if real-time unavailable

✅ **News** (`fetch_news`)

- Company-specific news articles
- Multiple publishers
- Related symbols tracking

### Partially Implemented

⚠️ **Fundamentals** (`fetch_fundamentals`)

- Basic company information available
- Some financial metrics may require additional API endpoints
- May need enhancement based on your Massive.com subscription tier

⚠️ **Earnings** (`fetch_earnings`)

- Placeholder implementation
- May require additional API endpoints or subscription tier
- Consider using Yahoo Finance for comprehensive earnings data

⚠️ **Industry Peers** (`fetch_industry_peers`)

- Sector/industry classification available
- Peer company matching may need additional API calls
- Consider using Yahoo Finance for comprehensive peer data

## Comparison with Yahoo Finance

| Feature          | Yahoo Finance     | Massive.com                             |
| ---------------- | ----------------- | --------------------------------------- |
| Price Data       | ✅ Free, reliable | ✅ Professional-grade, requires API key |
| Real-time Data   | ⚠️ Delayed        | ✅ Real-time (with subscription)        |
| Fundamentals     | ✅ Comprehensive  | ⚠️ Basic (may need subscription)        |
| News             | ✅ Good coverage  | ✅ Professional sources                 |
| Earnings         | ✅ Comprehensive  | ⚠️ Limited (may need subscription)      |
| Industry Peers   | ✅ Good coverage  | ⚠️ Limited                              |
| API Key Required | ❌ No             | ✅ Yes                                  |
| Rate Limits      | ⚠️ Informal       | ✅ Documented                           |

## Rate Limiting

The Massive.com data provider includes **automatic rate limiting** to prevent API rate limit violations:

- **Default**: 4 calls per minute (configurable)
- **Automatic**: All API calls are automatically rate-limited
- **Thread-Safe**: Handles concurrent API calls safely
- **Configurable**: Adjust via `MASSIVE_RATE_LIMIT_CALLS` and `MASSIVE_RATE_LIMIT_WINDOW`

See [MASSIVE_RATE_LIMITING.md](./MASSIVE_RATE_LIMITING.md) for detailed documentation.

## Best Practices

1. **Use Fallback Strategy**: Consider using `fallback` as default provider for automatic failover
2. **API Key Security**: Never commit API keys to version control
3. **Rate Limiting**: Configure rate limits to match your subscription tier (see Rate Limiting section above)
4. **Error Handling**: Implement proper error handling for API failures
5. **Testing**: Test with your API key before deploying to production

## Troubleshooting

### "Massive.com API key not found"

**Solution**: Set `MASSIVE_API_KEY` environment variable

```bash
export MASSIVE_API_KEY=your_api_key_here
```

### "massive library not installed"

**Solution**: Install the required library

```bash
pip install -U massive
```

Or ensure it's in your `requirements.txt`:

```
massive>=2.0.0
```

### "Unknown data source: massive"

**Solution**: Ensure Massive.com is enabled

```bash
export MASSIVE_ENABLED=true
export MASSIVE_API_KEY=your_api_key_here
```

### Limited Data Available

**Solution**: Some features may require higher subscription tiers. Check your Massive.com subscription level and API documentation for available endpoints.

## References

- [Massive.com Documentation](https://massive.com/docs/stocks/)
- [Polygon.io Python Client](https://github.com/polygon-io/client-python)
- [Massive.com API Status](https://massive.com/system)

## Migration Notes

Massive.com was formerly known as Polygon.io. The API endpoints and client libraries remain compatible, but the branding has changed. The Python client library (`polygon`) still works with Massive.com APIs.
