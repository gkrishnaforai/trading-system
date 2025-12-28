# Massive.com Rate Limiting

## Overview

The Massive.com data provider includes built-in rate limiting to prevent API rate limit violations. The rate limiter uses a token bucket algorithm to ensure API calls stay within configured limits.

## Configuration

### Environment Variables

Add the following to your `.env` file:

```bash
# Massive.com API rate limit (calls per minute)
MASSIVE_RATE_LIMIT_CALLS=4

# Rate limit time window in seconds (default: 60 for per-minute)
MASSIVE_RATE_LIMIT_WINDOW=60.0
```

### Default Settings

- **Default Rate Limit**: 4 calls per minute
- **Time Window**: 60 seconds (1 minute)
- **Configurable**: Both values can be adjusted via environment variables

## How It Works

### Token Bucket Algorithm

The rate limiter uses a token bucket algorithm:

1. **Bucket Capacity**: Maximum number of calls allowed (`MASSIVE_RATE_LIMIT_CALLS`)
2. **Refill Rate**: Tokens refill at a rate of `max_calls / time_window`
3. **Burst Handling**: Allows bursts up to the maximum capacity
4. **Thread-Safe**: Multiple concurrent API calls are safely rate-limited

### Example

With `MASSIVE_RATE_LIMIT_CALLS=4` and `MASSIVE_RATE_LIMIT_WINDOW=60`:

- **4 calls** can be made immediately
- After 1 call, **1 token** is consumed
- After 15 seconds, **1 token** is available again (4 tokens / 60 seconds = 1 token per 15 seconds)
- After 60 seconds, all **4 tokens** are available again

## Usage

The rate limiter is automatically applied to all Massive.com API calls. No code changes are required:

```python
from app.data_sources import get_data_source

# Get Massive.com data source (rate limiting is automatic)
data_source = get_data_source("massive")

# All API calls are automatically rate-limited
price_data = data_source.fetch_price_data("AAPL", period="1y")
current_price = data_source.fetch_current_price("AAPL")
fundamentals = data_source.fetch_fundamentals("AAPL")
```

## Rate Limiter Behavior

### Automatic Throttling

When the rate limit is reached:
- The rate limiter **automatically waits** until a token is available
- API calls are **blocked** until capacity is available
- **No errors** are thrown - calls are simply delayed

### Logging

The rate limiter logs its activity:

```
INFO: Initialized Massive.com API: 4 calls per 60.0s (4.00 calls/minute)
DEBUG: Massive.com API: Call allowed. Used: 1/4 calls
DEBUG: Massive.com API: Rate limit reached. Waiting 15.23s for next available slot
```

### Statistics

You can check rate limiter statistics:

```python
from app.data_sources import get_data_source

data_source = get_data_source("massive")
stats = data_source.rate_limiter.get_stats()

print(f"Current calls: {stats['current_calls']}/{stats['max_calls']}")
print(f"Available calls: {stats['available_calls']}")
print(f"Calls per minute: {stats['calls_per_minute']}")
```

## Adjusting Rate Limits

### For Different Subscription Tiers

Different Massive.com subscription tiers have different rate limits:

| Tier | Rate Limit | Configuration |
|------|------------|---------------|
| Free/Starter | 5 calls/minute | `MASSIVE_RATE_LIMIT_CALLS=5` |
| Developer | 10 calls/minute | `MASSIVE_RATE_LIMIT_CALLS=10` |
| Advanced | 20 calls/minute | `MASSIVE_RATE_LIMIT_CALLS=20` |
| Professional | 100 calls/minute | `MASSIVE_RATE_LIMIT_CALLS=100` |

### Custom Time Windows

You can also adjust the time window:

```bash
# 10 calls per 30 seconds (20 calls/minute)
MASSIVE_RATE_LIMIT_CALLS=10
MASSIVE_RATE_LIMIT_WINDOW=30.0

# 1 call per 10 seconds (6 calls/minute)
MASSIVE_RATE_LIMIT_CALLS=1
MASSIVE_RATE_LIMIT_WINDOW=10.0
```

## Best Practices

1. **Match Your Subscription**: Set rate limits to match your Massive.com subscription tier
2. **Monitor Usage**: Check rate limiter statistics to understand API usage patterns
3. **Handle Delays**: Be aware that rate-limited calls may take longer to complete
4. **Test Limits**: Test with your actual API key to ensure limits are appropriate

## Troubleshooting

### Calls Are Too Slow

**Problem**: API calls are taking too long due to rate limiting

**Solution**: 
- Increase `MASSIVE_RATE_LIMIT_CALLS` if your subscription allows
- Check if you're making too many concurrent calls
- Consider using batch endpoints if available

### Rate Limit Errors from API

**Problem**: Still getting rate limit errors (429) from Massive.com API

**Solution**:
- Verify your rate limit configuration matches your subscription
- Check if other applications are using the same API key
- Reduce `MASSIVE_RATE_LIMIT_CALLS` to be more conservative

### Rate Limiter Not Working

**Problem**: Rate limiter doesn't seem to be active

**Solution**:
- Verify `MASSIVE_ENABLED=true` is set
- Check that `MASSIVE_API_KEY` is configured
- Ensure you're using `get_data_source("massive")` or have `DEFAULT_DATA_PROVIDER=massive`

## Implementation Details

### Thread Safety

The rate limiter is **thread-safe** and can handle concurrent API calls from multiple threads:

- Uses `threading.Lock()` for synchronization
- Multiple threads can safely call the same rate limiter
- Calls are serialized through the rate limiter

### Performance

- **Low Overhead**: Minimal performance impact
- **Non-Blocking**: Uses efficient time-based tracking
- **Memory Efficient**: Only stores recent call timestamps

## References

- [Massive.com API Documentation](https://massive.com/docs/stocks/)
- [Rate Limiting Best Practices](https://massive.com/docs/rate-limits/)

