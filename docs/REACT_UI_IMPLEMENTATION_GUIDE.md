# React UI Implementation Guide (Go API as Single Backend)

## Purpose

This guide describes how to build the product React UI so it talks **only** to the Go API. The goal is zero duplication of business logic between Streamlit/admin and React/product; both are clients of the same Go API contract.

Use this document as an input to LLM-assisted React/UI work.

## Non-goals

- React must not call python-worker directly.
- React must not call external market-data providers.

## Recommended frontend stack

- **React + TypeScript**
- **React Query (TanStack Query)** for request caching, retries, and background refetch
- **Zod** for runtime validation of API payloads (optional but recommended)
- **Component library**: shadcn/ui or MUI (choose one)

## Environment configuration

- **Single source of truth**: `NEXT_PUBLIC_API_URL` (Next.js) or `VITE_GO_API_URL` (Vite)
  - local dev (host): `http://localhost:8000`
  - docker (internal network): `http://go-api:8000`

Hard rule:
- React must not hardcode `localhost` or `go-api` in code. Always read from env.

## API client pattern

Create a single API client:
- `src/lib/apiClient.ts`

Responsibilities:
- base URL
- request/response typing
- auth header (future)
- consistent error mapping

### Hardened client defaults (match Streamlit hardening)

- **Connect timeout**: 5s
- **Read timeout**: 30s
- **Retries**: 2 (only for safe idempotent requests; React Query can handle this)
- **Retry on**: 429, 500, 502, 503, 504

Example `fetch` wrapper:

```ts
// src/lib/apiClient.ts
const BASE_URL = process.env.NEXT_PUBLIC_API_URL;
if (!BASE_URL) throw new Error("NEXT_PUBLIC_API_URL is not set");

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit & { timeoutMs?: number } = {}
): Promise<T> {
  const timeoutMs = init.timeoutMs ?? 30_000;
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers || {}),
      },
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new ApiError(text || `HTTP ${res.status}`, res.status);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(id);
  }
}
```

## React Query caching guidance (industry standard)

- Use React Query for **client-side caching**; Redis handles **server-side caching**.
- Prefer short stale times for dynamic data and longer for fundamentals.

Suggested defaults:
- symbol scope resolve: `staleTime: 30s`
- earnings calendar: `staleTime: 30s2m`
- fundamentals snapshots: `staleTime: 6h`

Retries (recommended):
- `retry: (failureCount, err) => failureCount < 2 && isRetryable(err)`
- `retryDelay: attemptIndex => Math.min(1000 * 2 ** attemptIndex, 5000)`

Where `isRetryable(err)` returns true for:
- network errors
- `429`, `500`, `502`, `503`, `504`

## Core screens (MVP)

### 1) Watchlist screen
- List watchlists: `GET /api/v1/watchlists/user/:user_id?subscription_level=...`
- Get watchlist: `GET /api/v1/watchlists/:watchlist_id?subscription_level=...`
- Add symbol: `POST /api/v1/watchlists/:watchlist_id/items`

### 2) Portfolio screen
- Get portfolio: `GET /api/v1/portfolio/:user_id/:portfolio_id?subscription_level=...`
- Add holding: `POST /api/v1/portfolio/:user_id/:portfolio_id/holdings`

### 3) Earnings calendar screen
- Resolve symbols for scope:
  - `GET /api/v1/symbol-scope/resolve?user_id=...&watchlist_id=...&portfolio_id=...&subscription_level=...`
- Read earnings calendar window (admin endpoint currently; can be promoted later):
  - `GET /api/v1/admin/earnings-calendar?start_date=...&end_date=...`

UI views:
- Month / Week / Day are **date-range projections**. Same endpoint, different parameters.

## Subscription gating UX

Backend is authoritative. UI behavior:
- Always render the section
- If field is missing/`null`, show:
  - lock icon
  - tooltip: "Upgrade to Pro" / "Upgrade to Elite"

## Error handling

- Display network errors in a non-blocking toast/banner.
- For 4xx validation errors, show field-level messages.
- For 5xx, show a generic "Try again" and log the request id (if present).

## Future enhancements

- Auth: JWT stored in HttpOnly cookies; Go API validates and injects subscription tier.
- Move earnings calendar endpoints out of `/admin` into public namespace once finalized.
- Add `/symbols/search` and `/symbols/{symbol}/overview` endpoints for iPhone-Stocks-like discovery.

