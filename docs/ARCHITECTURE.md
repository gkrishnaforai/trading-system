# Architecture Overview

## System Architecture

Trading System follows a microservices architecture with clear separation of concerns:

### Components

1. **Go API** - Core trading engine and API gateway
2. **Python Worker** - AI/ML processing and analysis
3. **Frontend** - Next.js web application
4. **Database** - SQLite (dev) or PostgreSQL/Supabase (prod)
5. **Redis** - Queue and cache layer

### Communication Flow

```
Frontend (Next.js)
    ↓ HTTP/REST
Go API (Port 8000)
    ↓ gRPC
Python Worker (Port 50051)
    ↓
Redis Queue
    ↓
Database
```

### Data Flow

1. User interacts with Frontend
2. Frontend calls Go API REST endpoints
3. Go API processes trading logic, calculates signals
4. For AI/ML tasks, Go API calls Python Worker via gRPC
5. Python Worker processes indicators, generates narratives
6. Results stored in database
7. Frontend displays results

## Design Principles

- **DRY**: Shared logic in packages/modules
- **SOLID**: Single responsibility per service
- **Modular**: Easy to add new indicators, signals, or LLM models
- **Scalable**: Horizontal scaling via additional workers
- **Type-safe**: Protocol Buffers for gRPC communication
