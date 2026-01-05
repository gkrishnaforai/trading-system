FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY python-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    python3 -c "from massive import RESTClient; print('✅ massive library installed successfully')" || \
    (echo "❌ CRITICAL: massive library failed to install from requirements.txt" && exit 1)

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code and tests
COPY python-worker/app ./app
COPY python-worker/tests ./tests

# Copy Supabase migrations so python-worker can run them on startup
COPY supabase/migrations/ ./supabase/migrations/

# Copy python-worker migrations for admin API
COPY python-worker/migrations/ ./migrations/

# Copy Streamlit apps (UI entrypoints)
COPY python-worker/streamlit_*.py ./

# Copy configuration files for enhanced features
COPY python-worker/default_symbols.py ./

# Check Python syntax before finalizing image
RUN python3 -c "import ast, os; [ast.parse(open(os.path.join(root, f)).read()) for root, dirs, files in os.walk('/app') for f in files if f.endswith('.py')]" || (echo "❌ Python syntax errors found! Fix before building." && exit 1)

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose FastAPI port
EXPOSE 8001

# Start both batch worker (background) and API server (foreground)
CMD ["sh", "-c", "python -m app.main & python app/api_app.py"]
