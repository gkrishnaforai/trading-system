# Database Schema Standards

## STRICT NAMING CONVENTIONS

### Primary Key Fields
- **NEVER** change existing primary key field names
- **ALWAYS** use `symbol` for stock ticker symbols (NOT `stock_symbol`)
- **ALWAYS** use `date` for trading dates (NOT `trade_date`)

### Table-Specific Standards

#### Stock Data Tables
- `symbol` VARCHAR(10) - Stock ticker symbol
- `date` DATE - Trading date
- `data_source` VARCHAR(50) - Data provider name

#### Technical Indicators Tables  
- `symbol` VARCHAR(10) - Stock ticker symbol
- `date` DATE - Trading date
- `indicator_name` VARCHAR(50) - Indicator type
- `indicator_value` NUMERIC - Indicator value

#### Market Data Tables
- `symbol` VARCHAR(10) - Stock ticker symbol  
- `date` DATE - Trading date
- `open/high/low/close` NUMERIC - OHLC values
- `volume` BIGINT - Trading volume

#### Industry Peers Tables
- `symbol` VARCHAR(10) - Primary stock symbol
- `peer_symbol` VARCHAR(10) - Peer stock symbol

#### Fundamentals Tables
- `symbol` VARCHAR(10) - Stock ticker symbol
- `fiscal_date_ending` DATE - Fiscal period end

### Migration Rules
1. **NEVER** rename existing columns
2. **ADD** new columns with deprecation warnings if needed
3. **USE** views for abstraction instead of schema changes
4. **MAINTAIN** backward compatibility at all costs

### Code Review Checklist
- [ ] No primary key field name changes
- [ ] Consistent use of `symbol` and `date`
- [ ] All INSERT statements use correct column names
- [ ] All SELECT queries use correct column names
- [ ] No breaking changes to existing schemas

### Enforcement
- All schema changes require architectural review
- Database migrations must preserve existing column names
- Use feature flags for new schema patterns
- Maintain comprehensive test coverage for all database operations

---

**RULE: If you must change a field name, create a new table instead.**
