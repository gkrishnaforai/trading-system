# EMA Data Sufficiency - Analysis & Solutions

## 🔍 **Root Cause Analysis: EMA Data Insufficiency**

### **🐛 Current Issue:**
```
❌ Insufficient EMA data for SEA: need at least 2 points, got 1
```

### **🎯 Why This Happens:**

#### **1. EMA Calculation Requirements:**
- **EMA20 needs 20+ data points** to start calculating meaningful values
- **EMA slope needs 2+ valid EMA points** from different dates
- **Current query only gets 5 days** of data, which may not have valid EMA values

#### **2. Data Loading Issues:**
- **Insufficient historical data** - Not enough price history for EMA calculation
- **Missing indicator calculations** - EMA might not be calculated for all dates
- **Data gaps** - Missing dates in the indicators_daily table

#### **3. Query Limitations:**
```python
# Current query only gets 5 days
LIMIT 5  # May not contain enough valid EMA data points
```

## 🔧 **Comprehensive Solutions:**

### **✅ Solution 1: Enhanced EMA Slope Calculation**

**Current Implementation:**
```python
def calculate_ema_slope(symbol: str, target_date: str, db_url: str) -> float:
    # Only gets 5 days, may not have enough valid EMA points
    slope_query = """
        SELECT DISTINCT date, ema_20
        FROM indicators_daily 
        WHERE symbol = %s AND date <= %s::date
        ORDER BY date DESC
        LIMIT 5
    """
```

**Enhanced Implementation:**
```python
def calculate_ema_slope(symbol: str, target_date: str, db_url: str) -> float:
    """
    Calculate EMA20 slope with enhanced data sufficiency checks
    """
    try:
        engine = create_engine(db_url)
        
        # Get more historical data to ensure sufficient EMA points
        enhanced_query = """
            SELECT DISTINCT date, 
                   FIRST_VALUE(ema_20) OVER (PARTITION BY date ORDER BY created_at DESC) as ema_20
            FROM indicators_daily 
            WHERE symbol = %s 
            AND date <= %s::date
            AND ema_20 IS NOT NULL
            ORDER BY date DESC
            LIMIT 20  -- Get more days to find valid EMA data
        """
        
        df = pd.read_sql(enhanced_query, engine, params=(symbol.upper(), target_date))
        
        # Filter out invalid EMA values
        valid_ema_df = df[df['ema_20'].notna() & (df['ema_20'] > 0)]
        
        print(f"🔍 Enhanced EMA Analysis for {symbol}:")
        print(f"   Total records: {len(df)}")
        print(f"   Valid EMA records: {len(valid_ema_df)}")
        
        if len(valid_ema_df) < 2:
            print(f"❌ Insufficient valid EMA data: need at least 2 points, got {len(valid_ema_df)}")
            
            # Try to trigger EMA calculation if data is missing
            if len(df) >= 2:
                print(f"🔄 Attempting to calculate missing EMA values...")
                return _trigger_ema_calculation(symbol, target_date, db_url)
            else:
                print(f"❌ Insufficient price data for EMA calculation")
                return 0.0
        
        # Calculate slope using most recent 2 valid EMA points
        ema_recent = float(valid_ema_df.iloc[0]['ema_20'])
        ema_previous = float(valid_ema_df.iloc[1]['ema_20'])
        slope = ema_recent - ema_previous
        
        print(f"📈 EMA20 Slope for {symbol}: {slope:+.4f}")
        print(f"   Recent EMA: {ema_recent:.2f} ({valid_ema_df.iloc[0]['date']})")
        print(f"   Previous EMA: {ema_previous:.2f} ({valid_ema_df.iloc[1]['date']})")
        
        return slope
        
    except Exception as e:
        print(f"❌ Error calculating EMA slope for {symbol}: {e}")
        return 0.0

def _trigger_ema_calculation(symbol: str, target_date: str, db_url: str) -> float:
    """
    Trigger EMA calculation when insufficient data exists
    """
    try:
        print(f"🔄 Triggering EMA calculation for {symbol}...")
        
        # Get more price history to calculate EMA
        price_query = """
            SELECT date, close, high, low, open, volume
            FROM raw_market_data_daily 
            WHERE symbol = %s 
            AND date <= %s::date
            ORDER BY date DESC
            LIMIT 50  -- Get 50 days to ensure sufficient EMA calculation
        """
        
        engine = create_engine(db_url)
        price_df = pd.read_sql(price_query, engine, params=(symbol.upper(), target_date))
        
        if len(price_df) < 20:
            print(f"❌ Insufficient price data: {len(price_df)} < 20 days")
            return 0.0
        
        # Calculate EMA using the same logic as the indicator service
        from app.indicators.moving_averages import calculate_ema20
        
        price_df = price_df.sort_values('date')  # Sort ascending for EMA calculation
        price_df['ema_20'] = calculate_ema20(price_df['close'])
        
        # Get the most recent valid EMA values
        valid_ema = price_df[price_df['ema_20'].notna()].tail(2)
        
        if len(valid_ema) < 2:
            print(f"❌ Still insufficient EMA after calculation: {len(valid_ema)} < 2")
            return 0.0
        
        # Store calculated EMA values
        _store_ema_values(symbol, valid_ema, db_url)
        
        # Calculate slope
        ema_recent = float(valid_ema.iloc[-1]['ema_20'])
        ema_previous = float(valid_ema.iloc[-2]['ema_20'])
        slope = ema_recent - ema_previous
        
        print(f"✅ Calculated EMA slope: {slope:+.4f}")
        return slope
        
    except Exception as e:
        print(f"❌ Error in EMA calculation trigger: {e}")
        return 0.0

def _store_ema_values(symbol: str, ema_data: pd.DataFrame, db_url: str) -> None:
    """
    Store calculated EMA values in indicators_daily table
    """
    try:
        from sqlalchemy import create_engine, text
        from datetime import datetime
        
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            for _, row in ema_data.iterrows():
                # Upsert EMA values
                upsert_query = text("""
                    INSERT INTO indicators_daily (
                        symbol, date, ema_20, data_source, 
                        created_at, updated_at
                    ) VALUES (
                        :symbol, :date, :ema_20, 'calculated',
                        NOW(), NOW()
                    )
                    ON CONFLICT (symbol, date) 
                    DO UPDATE SET 
                        ema_20 = EXCLUDED.ema_20,
                        updated_at = NOW()
                """)
                
                conn.execute(upsert_query, {
                    'symbol': symbol.upper(),
                    'date': row['date'],
                    'ema_20': float(row['ema_20'])
                })
            
            conn.commit()
            print(f"✅ Stored {len(ema_data)} EMA values for {symbol}")
            
    except Exception as e:
        print(f"❌ Error storing EMA values: {e}")
```

### **✅ Solution 2: Proactive EMA Data Loading**

**Enhanced Data Loading Strategy:**
```python
def ensure_sufficient_ema_data(symbol: str, target_date: str, db_url: str) -> bool:
    """
    Ensure sufficient EMA data exists for reliable calculations
    """
    try:
        engine = create_engine(db_url)
        
        # Check current EMA data coverage
        coverage_query = """
            SELECT 
                COUNT(*) as total_records,
                COUNT(ema_20) as ema_records,
                COUNT(ema_20) FILTER (WHERE ema_20 IS NOT NULL) as valid_ema,
                MIN(date) as earliest_date,
                MAX(date) as latest_date
            FROM indicators_daily 
            WHERE symbol = %s 
            AND date >= %s::date - INTERVAL '30 days'
            AND date <= %s::date
        """
        
        coverage_df = pd.read_sql(
            coverage_query, 
            engine, 
            params=(symbol.upper(), target_date, target_date)
        )
        
        if coverage_df.empty:
            print(f"❌ No indicator data found for {symbol}")
            return False
        
        coverage = coverage_df.iloc[0]
        valid_ema_count = coverage['valid_ema']
        
        print(f"📊 EMA Data Coverage for {symbol}:")
        print(f"   Total records: {coverage['total_records']}")
        print(f"   EMA records: {coverage['ema_records']}")
        print(f"   Valid EMA: {valid_ema_count}")
        print(f"   Date range: {coverage['earliest_date']} to {coverage['latest_date']}")
        
        # Determine if we need to calculate more EMA data
        if valid_ema_count < 10:  # Need at least 10 valid EMA points
            print(f"⚠️ Insufficient EMA data ({valid_ema_count} < 10), triggering calculation...")
            return _trigger_comprehensive_ema_calculation(symbol, target_date, db_url)
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking EMA coverage: {e}")
        return False

def _trigger_comprehensive_ema_calculation(symbol: str, target_date: str, db_url: str) -> bool:
    """
    Comprehensive EMA calculation for extended historical period
    """
    try:
        print(f"🔄 Running comprehensive EMA calculation for {symbol}...")
        
        # Get extended price history
        price_query = """
            SELECT date, close, high, low, open, volume
            FROM raw_market_data_daily 
            WHERE symbol = %s 
            AND date >= %s::date - INTERVAL '60 days'
            AND date <= %s::date
            ORDER BY date ASC
        """
        
        engine = create_engine(db_url)
        price_df = pd.read_sql(price_query, engine, params=(symbol.upper(), target_date, target_date))
        
        if len(price_df) < 50:
            print(f"❌ Insufficient price history: {len(price_df)} < 50 days")
            return False
        
        # Calculate all technical indicators
        from app.utils.technical_indicators import TechnicalIndicators
        
        indicators = TechnicalIndicators()
        price_df_with_indicators = indicators.add_all_indicators(price_df)
        
        # Store indicators in database
        _store_comprehensive_indicators(symbol, price_df_with_indicators, db_url)
        
        print(f"✅ Calculated and stored indicators for {len(price_df)} days")
        return True
        
    except Exception as e:
        print(f"❌ Error in comprehensive EMA calculation: {e}")
        return False
```

### **✅ Solution 3: Data Quality Monitoring**

**EMA Data Health Check:**
```python
def check_ema_data_health(symbol: str, db_url: str) -> Dict[str, Any]:
    """
    Comprehensive EMA data health assessment
    """
    try:
        engine = create_engine(db_url)
        
        # Recent data quality
        recent_query = """
            SELECT 
                date,
                ema_20,
                CASE 
                    WHEN ema_20 IS NULL THEN 'missing'
                    WHEN ema_20 <= 0 THEN 'invalid'
                    ELSE 'valid'
                END as ema_status
            FROM indicators_daily 
            WHERE symbol = %s 
            AND date >= CURRENT_DATE - INTERVAL '14 days'
            ORDER BY date DESC
        """
        
        recent_df = pd.read_sql(recent_query, engine, params=(symbol.upper()))
        
        # Historical coverage
        history_query = """
            SELECT 
                COUNT(*) as total_days,
                COUNT(ema_20) as ema_calculated,
                COUNT(ema_20) FILTER (WHERE ema_20 IS NOT NULL AND ema_20 > 0) as ema_valid,
                DATE_TRUNC('week', date) as week
            FROM indicators_daily 
            WHERE symbol = %s 
            AND date >= CURRENT_DATE - INTERVAL '8 weeks'
            GROUP BY DATE_TRUNC('week', date)
            ORDER BY week DESC
        """
        
        history_df = pd.read_sql(history_query, engine, params=(symbol.upper()))
        
        # Calculate health metrics
        total_recent = len(recent_df)
        valid_recent = len(recent_df[recent_df['ema_status'] == 'valid'])
        recent_validity_rate = (valid_recent / total_recent * 100) if total_recent > 0 else 0
        
        total_historical = history_df['total_days'].sum()
        valid_historical = history_df['ema_valid'].sum()
        historical_validity_rate = (valid_historical / total_historical * 100) if total_historical > 0 else 0
        
        health_status = {
            'symbol': symbol,
            'recent_data': {
                'total_days': total_recent,
                'valid_days': valid_recent,
                'validity_rate': recent_validity_rate,
                'status': 'good' if recent_validity_rate >= 80 else 'poor'
            },
            'historical_data': {
                'total_days': total_historical,
                'valid_days': valid_historical,
                'validity_rate': historical_validity_rate,
                'status': 'good' if historical_validity_rate >= 80 else 'poor'
            },
            'overall_health': 'good' if recent_validity_rate >= 80 and historical_validity_rate >= 80 else 'needs_attention'
        }
        
        print(f"🏥 EMA Data Health for {symbol}:")
        print(f"   Recent validity: {recent_validity_rate:.1f}% ({valid_recent}/{total_recent})")
        print(f"   Historical validity: {historical_validity_rate:.1f}% ({valid_historical}/{total_historical})")
        print(f"   Overall status: {health_status['overall_health']}")
        
        return health_status
        
    except Exception as e:
        print(f"❌ Error checking EMA health: {e}")
        return {'error': str(e)}
```

### **✅ Solution 4: Automated Data Enrichment**

**Background Data Enrichment:**
```python
def enrich_ema_data_for_symbol(symbol: str, db_url: str) -> bool:
    """
    Background process to enrich EMA data for a symbol
    """
    try:
        print(f"🔄 Starting EMA data enrichment for {symbol}...")
        
        # Step 1: Check current coverage
        if not ensure_sufficient_ema_data(symbol, datetime.now().date(), db_url):
            print(f"❌ Failed to ensure sufficient EMA data for {symbol}")
            return False
        
        # Step 2: Validate data quality
        health = check_ema_data_health(symbol, db_url)
        
        if health.get('overall_health') != 'good':
            print(f"⚠️ EMA data health is {health.get('overall_health')}, running enrichment...")
            
            # Step 3: Calculate missing indicators
            success = _trigger_comprehensive_ema_calculation(
                symbol, 
                datetime.now().date(), 
                db_url
            )
            
            if success:
                print(f"✅ EMA data enrichment completed for {symbol}")
                return True
            else:
                print(f"❌ EMA data enrichment failed for {symbol}")
                return False
        else:
            print(f"✅ EMA data is already healthy for {symbol}")
            return True
            
    except Exception as e:
        print(f"❌ Error in EMA data enrichment: {e}")
        return False
```

## 🚀 **Implementation Strategy:**

### **Phase 1: Immediate Fixes**
1. **Enhance EMA slope calculation** with better data querying
2. **Add EMA calculation triggers** when insufficient data is detected
3. **Improve error messages** with actionable information

### **Phase 2: Proactive Measures**
1. **Implement data health monitoring** for all symbols
2. **Add automated data enrichment** processes
3. **Create EMA data validation** checks

### **Phase 3: System Integration**
1. **Integrate with data loading pipeline** to ensure EMA calculation
2. **Add scheduled data quality checks**
3. **Implement alerting** for EMA data issues

## 📊 **Expected Results:**

### **✅ Immediate Benefits:**
- **No more "Insufficient EMA data" errors**
- **Reliable EMA slope calculations**
- **Automatic EMA calculation** when data is missing

### **✅ Long-term Benefits:**
- **Consistent EMA data quality** across all symbols
- **Proactive data issue detection**
- **Automated data maintenance**

### **✅ Monitoring Capabilities:**
- **EMA data health dashboard**
- **Data quality metrics**
- **Automated enrichment reports**

**This comprehensive approach ensures we always have sufficient EMA data for reliable calculations!** 🎯
