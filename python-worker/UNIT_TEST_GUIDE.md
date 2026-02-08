# Unit Test Suite for Fix Verification

## 🎯 **Purpose**
Test all fixes against the running PostgreSQL container without needing to deploy to the Python worker container.

## 🚀 **How to Run**

### **1. Prerequisites**
```bash
# Ensure PostgreSQL container is running
docker-compose ps postgres

# Ensure DATABASE_URL is set in python-worker/.env
cat .env | grep DATABASE_URL
```

### **2. Run Tests**
```bash
cd /Users/krishnag/tools/trading-system/python-worker

# Quick test runner
./run_unit_tests.sh

# Or run directly
python test_fixes_unit.py
```

## 📋 **Test Coverage**

### **1. Database Connection Tests**
- ✅ Basic PostgreSQL connectivity
- ✅ Database query execution

### **2. Table Existence Tests**
- ✅ `financial_statements` table exists
- ✅ `corporate_actions` table exists
- ✅ `earnings_data` table exists
- ✅ All newly created tables (`earnings_transcripts`, `short_interest`, etc.)

### **3. Column Name Tests**
- ✅ `financial_statements.stock_symbol` exists
- ✅ `financial_statements.symbol` does NOT exist
- ✅ Date column mappings for all tables

### **4. NaT Handling Tests**
- ✅ `None` values filtered correctly
- ✅ `pd.NaT` values filtered correctly
- ✅ Invalid dates become `NaT` and are filtered
- ✅ Valid dates pass through

### **5. Method Signature Tests**
- ✅ `fetch_financial_statements` accepts `quarterly` as positional
- ✅ `fetch_corporate_actions` alias exists
- ✅ All required data source methods exist

### **6. Constraint Tests**
- ✅ Unique constraints on `financial_statements`
- ✅ Conflict resolution works with correct column names

### **7. Data Summary API Tests**
- ✅ Table validation logic
- ✅ Date column mappings for summary queries

## 🔍 **Test Details**

### **Financial Statements Fix Verification**
```python
def test_financial_statements_column_names(self):
    # Verifies stock_symbol column exists
    # Verifies symbol column does NOT exist
    # Tests insert query structure
```

### **NaT Handling Verification**
```python
def test_nat_handling(self):
    test_cases = [
        (None, True),      # Should be filtered
        (pd.NaT, True),    # Should be filtered
        ("invalid_date", True),  # Should become NaT and be filtered
        ("2023-01-01", False),   # Should pass through
    ]
```

### **Method Signature Verification**
```python
def test_financial_statements_method_signatures(self):
    # Checks quarterly is not keyword-only
    # Verifies method accepts positional arguments
```

## 📊 **Expected Output**

```
🚀 Starting unit tests against PostgreSQL container...
============================================================
test_database_connection ... ok
test_table_existence ... ok
test_financial_statements_column_names ... ok
test_nat_handling ... ok
test_financial_statements_insert_structure ... ok
test_data_source_methods ... ok
test_financial_statements_method_signatures ... ok
test_corporate_actions_alias ... ok
test_date_column_mappings ... ok
test_constraint_handling ... ok

============================================================
📊 TEST SUMMARY
============================================================
Tests run: 10
Failures: 0
Errors: 0

🎉 ALL TESTS PASSED! Ready for container deployment.
```

## 🚨 **Troubleshooting**

### **Database Connection Issues**
```bash
# Check PostgreSQL container
docker-compose logs postgres

# Check DATABASE_URL
echo $DATABASE_URL

# Test connection manually
python -c "from app.database import db; print(db.execute_query('SELECT 1'))"
```

### **Missing Tables**
```bash
# Run migrations
python -c "
from app.database import db
with open('migrations/031_create_missing_tables.sql', 'r') as f:
    db.execute_update(f.read())
print('Migration completed')
"
```

### **Import Errors**
```bash
# Check Python path
export PYTHONPATH=/Users/krishnag/tools/trading-system/python-worker:$PYTHONPATH

# Check app structure
ls -la app/
```

## 🎯 **Next Steps After Tests Pass**

### **1. Deploy to Container**
```bash
cd /Users/krishnag/tools/trading-system
docker-compose build python-worker
docker-compose up -d python-worker
```

### **2. Verify Container Deployment**
```bash
# Check container logs
docker-compose logs python-worker

# Test health endpoint
curl http://localhost:8001/health

# Test data summary API
curl http://localhost:8001/admin/data-summary/financial_statements
```

### **3. Integration Testing**
```bash
# Test actual data refresh
curl -X POST http://localhost:8001/refresh/financial-statements \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'
```

## 🎉 **Success Criteria**

- ✅ All unit tests pass
- ✅ Container starts without errors
- ✅ Health endpoint responds
- ✅ Data summary API works
- ✅ Financial statements refresh works
- ✅ No NaT or column name errors in logs

Once all tests pass, you can confidently deploy to the Python worker container!
