# Database Schema Reference

## 📊 Table and Column Names Reference

### **Core Tables**

#### **stocks**
```sql
Columns: id, symbol, company_name, exchange, sector, industry, market_cap, 
         country, currency, is_active, listing_date, delisting_date, 
         created_at, updated_at, has_fundamentals, has_earnings, 
         has_market_data, has_indicators, last_fundamentals_update, 
         last_earnings_update, last_market_data_update, last_indicators_update
```

#### **raw_market_data_daily**
```sql
Columns: id, symbol, date, open, high, low, close, volume, 
         adjusted_close, data_source, created_at
```

#### **raw_market_data_intraday**
```sql
Columns: id, symbol, ts, interval, open, high, low, close, 
         volume, data_source, created_at
```

#### **indicators_daily**
```sql
Columns: id, symbol, date, indicator_name, indicator_value, 
         time_period, data_source, created_at
```

#### **data_ingestion_runs**
```sql
Columns: run_id, started_at, finished_at, status, environment, 
         git_sha, metadata, created_at
```

#### **data_ingestion_events**
```sql
Columns: id, run_id, event_ts, level, provider, operation, symbol, 
         duration_ms, records_in, records_saved, message, error_type, 
         error_message, root_cause_type, root_cause_message, 
         context, created_at
```

#### **data_ingestion_state**
```sql
Columns: id, symbol, data_source, table_name, dataset, interval, 
         last_ingested_at, records_count, status, error_message, 
         created_at, updated_at
```

#### **macro_market_data**
```sql
Columns: id, data_date, vix_close, nasdaq_symbol, nasdaq_close, 
         nasdaq_sma50, nasdaq_sma200, tnx_yield, irx_yield, 
         yield_curve_spread, sp500_above_50d_pct, source, created_at
```

#### **fundamentals_summary**
```sql
Columns: id, symbol, name, sector, industry, market_cap, pe_ratio, 
         pb_ratio, eps, beta, dividend_yield, revenue_ttm, 
         gross_profit_ttm, operating_margin_ttm, profit_margin_ttm, 
         roe, debt_to_equity, price_to_sales, ev_to_revenue, 
         ev_to_ebitda, price_to_book, data_source, updated_at, 
         created_at
```

#### **fundamentals_snapshots**
```sql
Columns: id, symbol, as_of_date, payload, created_at, updated_at
```

#### **industry_peers**
```sql
Columns: id, symbol, peer_symbol, industry, sector, data_source, 
         created_at
```

#### **market_news**
```sql
Columns: id, symbol, title, url, source, summary, published_at, 
         created_at
```

#### **missing_symbols_queue**
```sql
Columns: id, symbol, source_table, source_record_id, discovered_at, 
         status, error_message, attempts, last_attempt_at, 
         completed_at
```

#### **signals**
```sql
Columns: id, symbol, signal_type, signal_value, confidence, 
         price_at_signal, timestamp, engine_name, reasoning, 
         metadata, created_at
```

#### **earnings_data** (NOT earnings_calendar)
```sql
Columns: [Check actual structure - table exists but needs column verification]
```

---

## 🔧 **Column Naming Standards**

### **✅ CORRECT Names to Use:**
- **Symbol**: `symbol` (NOT `stock_symbol`)
- **Date**: `date` for daily data, `ts` for intraday, `data_date` for macro data
- **Timestamp**: `created_at`, `updated_at`, `event_ts`
- **Trade Date**: `date` (NOT `trade_date`)

### **❌ OLD Names (Deprecated):**
- `stock_symbol` → Use `symbol`
- `trade_date` → Use `date`
- `as_of_date` → Use `date` (for fundamentals)

---

## 📋 **API Query Patterns**

### **Daily Market Data:**
```sql
SELECT * FROM raw_market_data_daily 
WHERE symbol = 'AAPL' AND date = '2026-01-06'
```

### **Intraday Data:**
```sql
SELECT * FROM raw_market_data_intraday 
WHERE symbol = 'AAPL' AND ts >= '2026-01-06 09:30:00'
```

### **Indicators:**
```sql
SELECT * FROM indicators_daily 
WHERE symbol = 'AAPL' AND date = '2026-01-06'
```

### **Macro Data:**
```sql
SELECT * FROM macro_market_data 
WHERE data_date = '2026-01-06'
```

---

## 🎯 **Key Points for Developers**

1. **Always use `symbol`** - never `stock_symbol`
2. **Use `date` for daily data** - never `trade_date`
3. **Use `ts` for intraday timestamps**
4. **Use `data_date` for macro data**
5. **Check table structure** before writing queries
6. **Test with actual column names** - don't assume!

---

## 🔄 **Migration Status**

✅ **Fixed Tables**: stocks, raw_market_data_daily, indicators_daily, data_ingestion_state, industry_peers  
✅ **VIX Data**: Working in macro_market_data  
❌ **Still Issues**: raw_market_data_intraday (API code needs fixing)  

---

## 📞 **Quick Reference Commands**

### **Check Table Structure:**
```sql
SELECT column_name, ordinal_position 
FROM information_schema.columns 
WHERE table_name = 'your_table_name' 
ORDER BY ordinal_position
```

### **Check All Tables:**
```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name
```
