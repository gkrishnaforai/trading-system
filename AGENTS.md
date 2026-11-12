
## External calls
- LLM: always `from app.llm.client import llm_completion` — never raw `litellm.completion` (timeout + breaker live in the door).
- Provider fetches: terminal failures call `fail(provider, endpoint, e)` (ledgers to fetch_failures + trips the breaker), never bare `br.failure()`.
- `yf.download(...)` must pass `timeout=`.
