# Indicator Calculation Policy

## Industry Standard: Automatic Indicator Calculation

**Best Practice (December 2025):** Technical indicators MUST be calculated automatically after every price data load. This ensures:

1. **Data Consistency**: Indicators are always in sync with price data
2. **Real-Time Readiness**: Signals can be generated immediately after data load
3. **No Manual Intervention**: Eliminates the need for separate indicator calculation steps
4. **Fail-Fast**: If indicators can't be calculated, the data load should fail (data is incomplete)

## Current Implementation

### ✅ Automatic Calculation (Implemented)

The system automatically calculates indicators after price data fetch in:

1. **`DataRefreshManager._refresh_data_type_with_result()`**:
   - When `DataType.PRICE_HISTORICAL` is refreshed successfully
   - Automatically calls `IndicatorService.calculate_indicators()`
   - **Fail-fast**: Raises exception if indicator calculation fails
   - This ensures indicators are ALWAYS calculated after price data load

2. **Batch Worker**:
   - Calculates indicators for all symbols after data refresh
   - Ensures consistency across all symbols

### ⚠️ Potential Issues

1. **API Endpoint Flag**: The `fetch-historical-data` endpoint has a `calculate_indicators` flag
   - **Issue**: If set to `False`, indicators won't be calculated
   - **Fix**: This flag should be deprecated or always set to `True`
   - **Current Behavior**: Auto-calculation happens regardless of flag (good!)

2. **Error Handling**: If indicator calculation fails, the entire data load fails
   - **This is correct**: Fail-fast ensures data integrity
   - **But**: Should provide clear error messages

## Policy Enforcement

### Rule 1: Always Calculate Indicators After Price Data Load
- ✅ Implemented in `_refresh_data_type_with_result()`
- ✅ Automatic, no manual step required
- ✅ Fail-fast if calculation fails

### Rule 2: Indicators Must Use Validated/Cleaned Data
- ✅ Price data is validated before saving
- ✅ Indicators are calculated from validated data in database
- ✅ This ensures data quality

### Rule 3: Indicator Calculation Should Be Atomic
- ✅ If indicator calculation fails, the data load is marked as failed
- ✅ This prevents partial data states

## Recommendations

1. **Remove `calculate_indicators` flag from API** (or make it always True)
   - Indicators should ALWAYS be calculated
   - No opt-out option

2. **Add indicator calculation to audit trail**
   - Track when indicators are calculated
   - Track calculation duration
   - Track success/failure

3. **Add retry logic for transient failures**
   - If indicator calculation fails due to transient issues, retry
   - But still fail-fast for persistent issues

4. **Add validation that indicators exist after data load**
   - Verify indicators were calculated successfully
   - Alert if indicators are missing

## Code Review Findings

### ✅ Good Practices Found:
1. Auto-calculation in `_refresh_data_type_with_result()` ✅
2. Fail-fast error handling ✅
3. Validation before indicator calculation ✅
4. Audit trail for data fetches ✅

### ⚠️ Areas for Improvement:
1. API endpoint still has `calculate_indicators` flag (should be deprecated)
2. No explicit validation that indicators exist after calculation
3. No retry logic for transient indicator calculation failures

