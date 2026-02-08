# Stock Grades System - Complete Implementation

## 🏗️ Architecture Overview

This system provides a **data-source independent** stock grades and consensus management system following **DRY** and **SOLID** principles.

### **Key Features:**
- ✅ **Data Source Agnostic**: Easy to switch between FMP, Bloomberg, Reuters, etc.
- ✅ **Real-time Alerts**: Individual grade changes + high-priority consensus changes
- ✅ **Industry Standard**: Yahoo Finance-style consensus display
- ✅ **Performance Optimized**: Materialized views, proper indexing
- ✅ **Extensible**: Plugin-based alert system
- ✅ **Audit Trail**: Complete event sourcing and history

---

## 📁 File Structure

```
migrations/
├── 007_stock_grades_system.sql          # Main schema (data source independent)
├── 008_consensus_system.sql             # Consensus tracking
├── 009_alerts_integration.sql           # Alert system integration
└── 010_stock_grades_indexes.sql        # Performance optimization

app/services/
├── data_sources/
│   ├── base.py                         # Abstract base (Dependency Inversion)
│   ├── fmp.py                          # FMP implementation
│   └── registry.py                     # Data source registry
├── stock_grades/
│   ├── service.py                      # Main service (Facade Pattern)
│   ├── consensus_service.py            # Consensus change detection
│   └── repository.py                   # Data access (Repository Pattern)
└── alerts/
    ├── plugins/
    │   ├── stock_grade_plugin.py        # Individual grade alerts
    │   └── consensus_plugin.py           # Consensus change alerts
    └── base.py                         # Alert interfaces

app/api/
└── stock_grades_api.py                 # RESTful API endpoints
```

---

## 🗄️ Database Schema

### **Core Tables:**

#### **1. stock_grades** (Data Source Independent)
```sql
-- Main grades table - no vendor coupling
CREATE TABLE stock_grades (
    id UUID PRIMARY KEY,
    symbol VARCHAR(10) REFERENCES stocks(symbol),  -- Foreign key!
    grade_date DATE NOT NULL,
    grading_company VARCHAR(100),
    previous_grade VARCHAR(20),
    new_grade VARCHAR(20),
    action VARCHAR(20),  -- upgrade, downgrade, maintain, initiate, suspend
    
    -- Data source tracking (for analytics, not business logic)
    data_source VARCHAR(50) DEFAULT 'unknown',
    source_id VARCHAR(100),
    
    -- Market context
    price_at_grade DECIMAL(10,2),
    volume_at_grade BIGINT,
    
    UNIQUE(symbol, grading_company, grade_date, data_source, source_id)
);
```

#### **2. stock_grade_consensus** (Market Consensus)
```sql
-- Cached consensus with calculated fields
CREATE TABLE stock_grade_consensus (
    symbol VARCHAR(10) PRIMARY KEY REFERENCES stocks(symbol),
    strong_buy INTEGER DEFAULT 0,
    buy INTEGER DEFAULT 0,
    hold INTEGER DEFAULT 0,
    sell INTEGER DEFAULT 0,
    strong_sell INTEGER DEFAULT 0,
    consensus_rating VARCHAR(20),
    
    -- Calculated fields
    total_analysts INTEGER GENERATED ALWAYS AS (...) STORED,
    consensus_score DECIMAL(3,1) GENERATED ALWAYS AS (...) STORED,
    
    last_updated TIMESTAMPTZ DEFAULT NOW()
);
```

#### **3. stock_consensus_history** (Event Sourcing)
```sql
-- Complete audit trail of consensus changes
CREATE TABLE stock_consensus_history (
    id UUID PRIMARY KEY,
    symbol VARCHAR(10) REFERENCES stocks(symbol),
    previous_consensus VARCHAR(20),
    new_consensus VARCHAR(20),
    consensus_change VARCHAR(20),  -- upgrade, downgrade, maintain
    significance_level INTEGER,     -- 1-5 significance
    market_impact VARCHAR(20),       -- LOW, MEDIUM, HIGH, VERY_HIGH
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 🔌 Data Source Architecture

### **Abstract Base Class:**
```python
class BaseDataSource(ABC):
    """Dependency Inversion Principle"""
    
    @abstractmethod
    async def get_stock_grades(self, symbol: str) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def get_consensus_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        pass
    
    def to_stock_grade(self, external_data: Dict) -> StockGrade:
        """Factory Method Pattern"""
        pass
```

### **FMP Implementation:**
```python
class FMPDataSource(BaseDataSource):
    """Single Responsibility: FMP API only"""
    
    async def get_stock_grades(self, symbol: str) -> List[Dict[str, Any]]:
        return self.client.get_stock_grades(symbol)
    
    def normalize_grade(self, grade: str) -> str:
        """Template Method Pattern"""
        return self._grade_mappings.get(grade, grade)
```

### **Registry Pattern:**
```python
class DataSourceRegistry:
    """Manages data source registration"""
    
    def get_source(self, source_type: DataSourceType) -> BaseDataSource:
        """Lazy Loading Pattern"""
        pass
    
    def register_source_class(self, source_type, source_class):
        """Factory Method Pattern"""
        pass
```

---

## 🚨 Alert System Integration

### **Two Alert Types:**

#### **1. Individual Grade Changes** (Standard Priority)
```python
class StockGradePlugin(BaseAlertPlugin):
    """Individual analyst grade changes"""
    
    def evaluate(self, context: AlertContext, config: Dict) -> AlertResult:
        # Check firm tier, portfolio, price impact
        # Return AlertResult with severity
        pass
```

#### **2. Consensus Changes** (HIGH PRIORITY)
```python
class ConsensusPlugin(BaseAlertPlugin):
    """Market consensus changes - HIGH PRIORITY"""
    
    def evaluate(self, context: AlertContext, config: Dict) -> AlertResult:
        # Check significance level, analyst count, market impact
        # Always higher priority than individual grades
        pass
```

### **Alert Templates:**
- **Individual**: "📈 AAPL upgraded by Goldman Sachs from Hold to Buy"
- **Consensus**: "🚀 MARKET CONSENSUS UPGRADE: AAPL upgraded to Buy"

---

## 📊 API Endpoints

### **RESTful API:**
```
GET  /api/v2/stock-grades/{symbol}/grades
GET  /api/v2/stock-grades/{symbol}/consensus
GET  /api/v2/stock-grades/{symbol}/recent-changes
POST /api/v2/stock-grades/refresh/{symbol}
POST /api/v2/stock-grades/update-consensus/{symbol}
GET  /api/v2/stock-grades/coverage-stats
```

### **Example Responses:**
```json
// Consensus Data
{
  "symbol": "AAPL",
  "strong_buy": 1,
  "buy": 67,
  "hold": 34,
  "sell": 7,
  "strong_sell": 0,
  "consensus_rating": "Buy",
  "consensus_score": 0.8,
  "total_analysts": 109,
  "last_updated": "2026-01-16T18:30:00Z"
}

// Grade Change
{
  "id": "uuid",
  "symbol": "AAPL",
  "grading_company": "Goldman Sachs",
  "previous_grade": "Hold",
  "new_grade": "Buy",
  "action": "upgrade",
  "grade_date": "2026-01-15",
  "data_source": "fmp"
}
```

---

## 🔄 Database Migration

### **Run Migrations:**
```bash
# Run in order
psql -d trading_db -f migrations/007_stock_grades_system.sql
psql -d trading_db -f migrations/008_consensus_system.sql
psql -d trading_db -f migrations/009_alerts_integration.sql
psql -d trading_db -f migrations/010_stock_grades_indexes.sql
```

### **Key Features:**
- ✅ **Foreign Keys**: `stock_grades.symbol → stocks.symbol`
- ✅ **Generated Columns**: Automatic consensus calculations
- ✅ **Triggers**: Automatic event creation and alert queuing
- ✅ **Indexes**: Optimized for performance
- ✅ **Constraints**: Data integrity and validation

---

## 🎯 Usage Examples

### **Load Grades for Symbol:**
```python
from app.services.stock_grades.service import get_stock_grades_service
from app.services.data_sources.base import DataSourceType

service = get_stock_grades_service()

# Load grades from FMP
grades = await service.load_grades_for_symbol('AAPL', DataSourceType.FMP)

# Get consensus
consensus = await service.load_consensus_for_symbol('AAPL', DataSourceType.FMP)
```

### **Detect Consensus Changes:**
```python
from app.services.stock_grades.consensus_service import get_consensus_service

consensus_service = get_consensus_service()

# Update consensus and detect changes
result = await consensus_service.update_consensus_for_symbol('AAPL')

if result['change_detected']:
    print(f"Consensus changed: {result['change_analysis']}")
```

### **API Usage:**
```bash
# Get grades for AAPL
curl "http://localhost:8001/api/v2/stock-grades/AAPL/grades"

# Get consensus for AAPL
curl "http://localhost:8001/api/v2/stock-grades/AAPL/consensus"

# Refresh data
curl -X POST "http://localhost:8001/api/v2/stock-grades/refresh/AAPL"

# Update consensus
curl -X POST "http://localhost:8001/api/v2/stock-grades/update-consensus/AAPL"
```

---

## 🏃‍♂️ Performance Features

### **Materialized Views:**
```sql
-- Refreshed hourly for performance
CREATE MATERIALIZED VIEW mv_consensus_summary AS
SELECT symbol, consensus_rating, consensus_score, total_analysts
FROM stock_grade_consensus c
JOIN stocks s ON c.symbol = s.symbol
WHERE c.total_analysts >= 3;
```

### **Indexes:**
```sql
-- Optimized for common queries
CREATE INDEX idx_stock_grades_symbol_date ON stock_grades(symbol, grade_date DESC);
CREATE INDEX idx_consensus_high_coverage ON stock_grade_consensus(total_analysts DESC);
CREATE INDEX idx_consensus_history_significant ON stock_consensus_history(significance_level DESC);
```

### **Batch Processing:**
```python
# Efficient batch updates
await service.batch_refresh_symbols(['AAPL', 'MSFT', 'GOOGL'], max_concurrent=5)
await consensus_service.batch_update_consensus(symbols, max_concurrent=3)
```

---

## 🔧 Configuration

### **Environment Variables:**
```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/trading_db

# FMP API
FMP_API_KEY=your_api_key_here

# Alert Settings
STOCK_GRADES_ALERT_ENABLED=true
CONSENSUS_ALERT_ENABLED=true
ALERT_BATCH_SIZE=50
```

### **Data Source Registry:**
```python
# Register new data sources
from app.services.data_sources.registry import get_data_source_registry

registry = get_data_source_registry()
registry.register_source_class(DataSourceType.BLOOMBERG, BloombergDataSource)
registry.register_source_class(DataSourceType.REUTERS, ReutersDataSource)
```

---

## 📈 Analytics & Monitoring

### **Coverage Statistics:**
```sql
SELECT 
    COUNT(DISTINCT symbol) as total_symbols,
    COUNT(DISTINCT grading_company) as total_firms,
    COUNT(*) as total_ratings,
    COUNT(CASE WHEN action = 'upgrade' THEN 1 END) as upgrades
FROM stock_grades;
```

### **Consensus Change Analytics:**
```sql
-- Recent consensus changes by significance
SELECT 
    symbol, consensus_change, significance_level, market_impact
FROM stock_consensus_history
WHERE recorded_at >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY significance_level DESC;
```

### **Performance Monitoring:**
```sql
-- Index usage
SELECT * FROM index_usage_stats WHERE tablename LIKE '%consensus%';

-- Slow queries
SELECT * FROM slow_query_candidates WHERE query LIKE '%stock_grade%';
```

---

## 🚀 Future Enhancements

### **Easy to Add:**
1. **New Data Sources**: Implement `BaseDataSource`
2. **New Alert Types**: Implement `BaseAlertPlugin`
3. **New Consensus Metrics**: Add to consensus service
4. **New Analytics Views**: Add materialized views

### **Planned Features:**
- 📱 **Mobile Push Notifications**
- 📊 **Advanced Analytics Dashboard**
- 🤖 **Machine Learning Predictions**
- 🌐 **WebSocket Real-time Updates**
- 📈 **Price Impact Analysis**

---

## 🛠️ Troubleshooting

### **Common Issues:**

#### **1. Database Connection:**
```bash
# Check connection
psql $DATABASE_URL -c "SELECT 1;"

# Check tables
\dt stock_grades*
```

#### **2. Data Source Issues:**
```python
# Test data sources
await service.validate_data_sources()
```

#### **3. Performance Issues:**
```sql
-- Check slow queries
SELECT * FROM slow_query_candidates;

-- Refresh materialized views
SELECT refresh_consensus_views();
```

---

## 📞 Support

### **Logs:**
```bash
# Application logs
tail -f logs/stock_grades.log

# Database logs
tail -f logs/database.log
```

### **Health Checks:**
```bash
# API health
curl "http://localhost:8001/api/v2/stock-grades/coverage-stats"

# Data source health
curl "http://localhost:8001/api/v2/stock-grades/data-sources"
```

---

## 🎯 Summary

This implementation provides a **production-ready**, **data-source independent** stock grades system that:

- ✅ **Follows SOLID Principles**: Single responsibility, dependency inversion, etc.
- ✅ **DRY Code**: No duplication, reusable components
- ✅ **Extensible**: Easy to add new data sources and alert types
- ✅ **Performance Optimized**: Proper indexing, materialized views
- ✅ **Complete**: Database schema, services, APIs, alerts
- ✅ **Future-Proof**: Clean architecture for enhancements

The system is ready for production use and can easily scale to handle multiple data sources, thousands of symbols, and real-time alert processing! 🚀
