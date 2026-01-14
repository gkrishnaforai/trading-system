# 🚨 CRITICAL: Router Configuration Guidelines

## ⚠️ IMMEDIATE RULES - READ BEFORE ANY ROUTER CHANGES

### 1. 📋 Router Setup Pattern
```python
# ✅ CORRECT PATTERN - USE THIS EXACTLY
from fastapi import APIRouter

# ========================================
# IMPORTANT: Router Configuration Rules
# ========================================
# DO NOT ADD PREFIX HERE! Prefixes are managed in api_server.py
# ❌ WRONG: router = APIRouter(prefix="/api/v1/feature", tags=["feature"])
# ✅ CORRECT: router = APIRouter(tags=["feature"])
# ========================================
router = APIRouter(tags=["feature"])

# Your endpoints here...
@router.get("/endpoint")
async def endpoint():
    return {"message": "works"}
```

### 2. 🎯 Prefix Management
- **NEVER** add `prefix=` to individual router files
- **ONLY** add prefixes in `/app/api_server.py`
- **EXACTLY ONE** prefix per router in the main server

### 3. 📁 File Structure Pattern
```
/app/api/
├── api_server.py          # ✅ ONLY place for prefixes
├── feature_router.py      # ✅ No prefix here
├── another_router.py      # ✅ No prefix here
└── README_ROUTERS.md       # ✅ This file
```

### 4. 🔍 Validation Checklist
Before committing any router changes:
- [ ] Router has NO prefix in individual file
- [ ] Router is imported in api_server.py
- [ ] Router has EXACTLY ONE prefix in api_server.py
- [ ] Test: `curl http://localhost:8001/docs` shows all endpoints
- [ ] Test: Key endpoints return 200, not 404

## 🚨 COMMON MISTAKES - AVOID THESE

### ❌ WRONG - Double Prefix
```python
# In router file:
router = APIRouter(prefix="/api/v1/feature", tags=["feature"])

# In api_server.py:
app.include_router(feature_router, prefix="/api/v1/feature")
# Result: /api/v1/feature/api/v1/feature/endpoint ❌
```

### ❌ WRONG - Missing Prefix
```python
# In router file:
router = APIRouter(tags=["feature"])  # ✅ Correct

# In api_server.py:
app.include_router(feature_router)  # ❌ Missing prefix
# Result: /endpoint instead of /api/v1/feature/endpoint ❌
```

### ✅ CORRECT - Single Prefix
```python
# In router file:
router = APIRouter(tags=["feature"])  # ✅ Correct

# In api_server.py:
app.include_router(feature_router, prefix="/api/v1/feature")  # ✅ Correct
# Result: /api/v1/feature/endpoint ✅
```

## 🧪 TESTING AFTER CHANGES

### 1. Quick Endpoint Test
```bash
# Test API docs are accessible
curl http://localhost:8001/docs

# Test specific endpoint
curl http://localhost:8001/api/v1/feature/endpoint
```

### 2. Expected Results
- ✅ 200: Endpoint works
- ❌ 404: Double prefix or missing prefix
- ❌ 500: Router import error

## 📝 Current Router Registry

### Main Routers (api_server.py)
```python
# These prefixes are FINAL - DO NOT change without full review
app.include_router(main_router, prefix="/api/v1")
app.include_router(portfolio_router, prefix="/api/v1/portfolio")
app.include_router(portfolio_v2_router, prefix="/api/v2/portfolio")
app.include_router(universal_router, prefix="/api/v1/universal")
app.include_router(growth_quality_router, prefix="/api/v1/growth-quality")
app.include_router(stocks_router, prefix="/api/v1/stocks")
app.include_router(stock_symbols_router, prefix="/api/v1/symbols")
app.include_router(admin_router, prefix="/admin")
app.include_router(bulk_operations_router, prefix="/api/v1/bulk")
app.include_router(generic_engine_router, prefix="/api/v1/generic")
app.include_router(swing_engine_router, prefix="/api/v1/swing")
app.include_router(tqqq_engine_router, prefix="/api/v1/tqqq")
app.include_router(unified_tqqq_router, prefix="/api/v1/unified-tqqq")
app.include_router(symbol_enrichment_router, prefix="/api/v1/enrichment")
app.include_router(market_router, prefix="/api/v1")
```

## 🔄 LLM INSTRUCTIONS

### For Future Development:
1. **ALWAYS** read this file first before any router changes
2. **NEVER** add prefixes to individual router files
3. **ALWAYS** validate endpoints after changes
4. **UPDATE** this file when adding new routers

### Code Review Checklist:
- [ ] Router file has no prefix
- [ ] Router is imported in api_server.py
- [ ] Router has correct prefix in api_server.py
- [ ] Endpoints are accessible
- [ ] No duplicate prefixes

## 🚀 EMERGENCY FIXES

If you see 404 errors:
1. Check if router has prefix in individual file - remove it
2. Check if router is missing prefix in api_server.py - add it
3. Check for double prefixes - remove from individual file
4. Test endpoints again

---

**⚠️ THIS FILE IS AUTHORITATIVE - Changes here affect all router development!**
