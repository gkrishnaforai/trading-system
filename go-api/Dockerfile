# Multi-stage build for Go API
FROM golang:1.22-alpine AS builder

# Install build dependencies for CGO (SQLite support)
RUN apk add --no-cache gcc musl-dev

WORKDIR /build

# Copy go mod files first
COPY go-api/go.mod ./

# Download dependencies
ENV GOPROXY=https://proxy.golang.org,direct
RUN for i in 1 2 3 4 5; do \
        go mod download && break; \
        echo "go mod download failed (attempt $i), retrying..."; \
        sleep $((i * 2)); \
    done

# Copy source code
COPY go-api/ ./

# Copy Supabase migrations (normalized baseline schema)
COPY supabase/migrations/ /app/supabase/migrations/

# Generate go.sum and verify dependencies
RUN go mod tidy

# Build (CGO enabled for SQLite support)
RUN CGO_ENABLED=1 GOOS=linux go build -o /build/api ./cmd/api

# Runtime stage
FROM alpine:latest

RUN apk --no-cache add ca-certificates wget sqlite

WORKDIR /app

COPY --from=builder /build/api .

# Copy Supabase migrations (normalized baseline schema)
COPY supabase/migrations/ /app/supabase/migrations/

EXPOSE 8000 50051

CMD ["./api"]
