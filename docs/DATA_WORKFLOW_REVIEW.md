# Data Load & Computation Workflow Review

## Executive Summary

**Current Status**: ✅ Good foundation with validation and audit
**Industry Comparison**: ⚠️ Missing workflow orchestration, fail-fast gates, and recovery mechanisms
**Recommendation**: Implement robust workflow pipeline with state management

---

## 1. Current System Analysis

### ✅ What We Have (Good)

1. **Data Validation Layer**

   - `DataValidator` with comprehensive checks
   - Validation reports stored in `data_validation_reports`
   - Data cleaning with `validate_and_clean()`

2. **Audit Trail**

   - `data_fetch_audit` table tracks all fetch operations
   - `signal_readiness` table for pre-flight checks
   - Detailed error tracking

3. **Separation of Concerns**

   - `DataRefreshManager` orchestrates fetching
   - `IndicatorService` handles computation
   - `BatchWorker` runs scheduled jobs

4. **Auto-calculation Policy**
   - Indicators auto-calculated after price data fetch
   - Industry standard: Always calculate after data load

### ⚠️ What's Missing (Critical Gaps)

1. **No Workflow Orchestration**

   - Steps run sequentially without state management
   - No rollback on failure
   - No retry logic with backoff

2. **No Fail-Fast Gates**

   - Batch continues even if data validation fails
   - No pre-flight checks before next stage
   - No dependency validation

3. **No Recovery Mechanisms**

   - Failed symbols are logged but not retried
   - No automatic recovery from transient failures
   - No checkpoint/resume capability

4. **No Workflow State Management**

   - Can't track "in-progress" vs "completed"
   - Can't resume from last successful step
   - No visibility into workflow progress

5. **Mixed Responsibilities**
   - Raw data and computed data in same flow
   - No clear separation of raw/clean/computed layers
   - Signals computed inline, not in separate stage

---

## 2. Industry Standard Comparison

### Industry Standard Pipeline

```
Market Close
   ↓
[GATE 1: Data Ingestion] → Raw Data (immutable, append-only)
   ↓
[GATE 2: Validation] → Clean Data (validated, normalized)
   ↓
[GATE 3: Indicator Computation] → Indicators (pure math, no signals)
   ↓
[GATE 4: Signal Engine] → Signals (rules-based, explainable)
   ↓
[GATE 5: Scoring] → Scores (aggregated, user-facing)
   ↓
[GATE 6: Caching] → Redis (fast reads)
   ↓
[GATE 7: API Ready] → Read-only API
```

### Our Current Flow

```
Batch Worker
   ↓
[Step 1] Fetch Data → Raw Data (with validation inline)
   ↓
[Step 2] Calculate Indicators → Indicators (auto-calculated)
   ↓
[Step 3] Generate Signals → Signals (inline)
   ↓
[Step 4] Generate Reports → Reports
   ↓
[Step 5] Update Metrics → Metrics
```

**Key Differences:**

- ❌ No gates between stages
- ❌ No state management
- ❌ No recovery
- ❌ Mixed raw/computed in same step
- ✅ Has validation (but not as gate)
- ✅ Has audit (but not used for workflow control)

---

## 3. Proposed Robust Workflow Architecture

### 3.1 Workflow Orchestration Options

#### Option A: Simple State Machine (Recommended for MVP)

**Pros:**

- Lightweight, no external dependencies
- Easy to understand and debug
- Full control over workflow logic

**Cons:**

- Manual state management
- No built-in retry/backoff

**Implementation:**

```python
class WorkflowState(Enum):
    PENDING = "pending"
    INGESTING = "ingesting"
    VALIDATING = "validating"
    COMPUTING = "computing"
    SIGNAL_GENERATING = "signal_generating"
    SCORING = "scoring"
    CACHING = "caching"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

class WorkflowStage:
    name: str
    state: WorkflowState
    started_at: datetime
    completed_at: Optional[datetime]
    error: Optional[str]
    retry_count: int
```

#### Option B: Prefect (Recommended for Production)

**Pros:**

- Built-in retry, backoff, scheduling
- Workflow visualization
- State management
- Task dependencies

**Cons:**

- External dependency
- Learning curve

**Example:**

```python
from prefect import flow, task
from prefect.tasks import task_inputs

@task(retries=3, retry_delay_seconds=60)
def ingest_data(symbol: str):
    # Data ingestion
    pass

@task
def validate_data(symbol: str):
    # Validation gate
    pass

@flow
def daily_pipeline(symbols: List[str]):
    for symbol in symbols:
        ingest_data(symbol)
        validate_data(symbol)
        # ... other stages
```

#### Option C: Celery (For Distributed Systems)

**Pros:**

- Distributed task queue
- Scalable
- Built-in retry

**Cons:**

- Requires Redis/RabbitMQ
- More complex setup

### 3.2 Recommended: Hybrid Approach

**Phase 1 (Now)**: Simple state machine with workflow table
**Phase 2 (Later)**: Migrate to Prefect if needed

---

## 4. Fail-Fast Gates Implementation

### Gate 1: Data Ingestion Gate

```python
class DataIngestionGate:
    """Validates data ingestion is complete and valid"""

    def check(self, symbol: str, date: date) -> GateResult:
        """
        Checks:
        1. Raw data exists for date
        2. Data source is valid
        3. Row count is reasonable
        4. No critical validation errors
        """
        # Check raw_market_data table
        raw_data = db.execute_query(
            "SELECT COUNT(*) as count FROM raw_market_data WHERE stock_symbol = :symbol AND date = :date",
            {"symbol": symbol, "date": date}
        )

        if not raw_data or raw_data[0]['count'] == 0:
            return GateResult(
                passed=False,
                reason="No raw data found",
                action="RETRY_INGESTION"
            )

        # Check validation report
        validation = db.execute_query(
            "SELECT overall_status, critical_issues FROM data_validation_reports WHERE symbol = :symbol AND data_type = 'price_historical' ORDER BY validation_timestamp DESC LIMIT 1",
            {"symbol": symbol}
        )

        if validation and validation[0]['overall_status'] == 'fail':
            return GateResult(
                passed=False,
                reason=f"Data validation failed: {validation[0]['critical_issues']} critical issues",
                action="FIX_DATA_QUALITY"
            )

        return GateResult(passed=True)
```

### Gate 2: Indicator Computation Gate

```python
class IndicatorComputationGate:
    """Validates indicators are computed and valid"""

    def check(self, symbol: str, date: date) -> GateResult:
        """
        Checks:
        1. Required indicators exist
        2. Indicators are not stale
        3. No NaN values in critical indicators
        """
        indicators = db.execute_query(
            """
            SELECT ema9, ema21, sma50, sma200, rsi, macd
            FROM aggregated_indicators
            WHERE stock_symbol = :symbol AND date = :date
            """,
            {"symbol": symbol, "date": date}
        )

        if not indicators:
            return GateResult(
                passed=False,
                reason="No indicators found",
                action="COMPUTE_INDICATORS"
            )

        ind = indicators[0]
        missing = []
        if ind['ema9'] is None: missing.append('ema9')
        if ind['sma200'] is None: missing.append('sma200')
        if ind['rsi'] is None: missing.append('rsi')

        if missing:
            return GateResult(
                passed=False,
                reason=f"Missing indicators: {', '.join(missing)}",
                action="RECOMPUTE_INDICATORS"
            )

        return GateResult(passed=True)
```

### Gate 3: Signal Generation Gate

```python
class SignalGenerationGate:
    """Validates signals can be generated"""

    def check(self, symbol: str) -> GateResult:
        """
        Uses SignalReadinessValidator
        """
        from app.data_validation.signal_readiness import SignalReadinessValidator

        validator = SignalReadinessValidator()
        readiness = validator.check_readiness(symbol, "swing_trend")

        if readiness.readiness_status == "not_ready":
            return GateResult(
                passed=False,
                reason=readiness.readiness_reason,
                action="FIX_DATA_QUALITY"
            )

        return GateResult(passed=True)
```

---

## 5. Recovery Mechanisms

### 5.1 Automatic Retry with Exponential Backoff

```python
class RetryPolicy:
    max_retries: int = 3
    initial_delay: int = 60  # seconds
    max_delay: int = 3600  # 1 hour
    backoff_multiplier: float = 2.0

    def should_retry(self, error: Exception, retry_count: int) -> bool:
        """Determine if error is retryable"""
        # Don't retry validation failures (data quality issues)
        if isinstance(error, ValidationError):
            return False

        # Retry transient errors
        if isinstance(error, (ConnectionError, TimeoutError, RateLimitError)):
            return retry_count < self.max_retries

        return False

    def get_delay(self, retry_count: int) -> int:
        """Calculate delay for retry"""
        delay = self.initial_delay * (self.backoff_multiplier ** retry_count)
        return min(delay, self.max_delay)
```

### 5.2 Checkpoint/Resume

```python
class WorkflowCheckpoint:
    """Save workflow state for recovery"""

    def save_checkpoint(self, workflow_id: str, stage: str, state: dict):
        """Save checkpoint"""
        db.execute_update(
            """
            INSERT OR REPLACE INTO workflow_checkpoints
            (workflow_id, stage, state_json, timestamp)
            VALUES (:workflow_id, :stage, :state_json, CURRENT_TIMESTAMP)
            """,
            {
                "workflow_id": workflow_id,
                "stage": stage,
                "state_json": json.dumps(state)
            }
        )

    def load_checkpoint(self, workflow_id: str) -> Optional[dict]:
        """Load last checkpoint"""
        result = db.execute_query(
            "SELECT stage, state_json FROM workflow_checkpoints WHERE workflow_id = :workflow_id ORDER BY timestamp DESC LIMIT 1",
            {"workflow_id": workflow_id}
        )
        if result:
            return {
                "stage": result[0]['stage'],
                "state": json.loads(result[0]['state_json'])
            }
        return None
```

### 5.3 Dead Letter Queue

```python
class DeadLetterQueue:
    """Store failed items for manual review"""

    def add_failed_item(self, symbol: str, stage: str, error: str, context: dict):
        """Add failed item to DLQ"""
        db.execute_update(
            """
            INSERT INTO workflow_dlq
            (symbol, stage, error_message, context_json, created_at)
            VALUES (:symbol, :stage, :error, :context, CURRENT_TIMESTAMP)
            """,
            {
                "symbol": symbol,
                "stage": stage,
                "error": error,
                "context": json.dumps(context)
            }
        )
```

---

## 6. Workflow State Management

### 6.1 Workflow Table Schema

```sql
CREATE TABLE IF NOT EXISTS workflow_executions (
    workflow_id TEXT PRIMARY KEY,
    workflow_type TEXT NOT NULL,  -- 'daily_batch', 'on_demand', 'recovery'
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'paused')),
    current_stage TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    metadata_json TEXT,  -- JSON with progress, counts, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workflow_stage_executions (
    stage_execution_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    FOREIGN KEY (workflow_id) REFERENCES workflow_executions(workflow_id)
);

CREATE TABLE IF NOT EXISTS workflow_symbol_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_id) REFERENCES workflow_executions(workflow_id),
    UNIQUE(workflow_id, symbol, stage)
);

CREATE INDEX IF NOT EXISTS idx_workflow_status ON workflow_executions(status);
CREATE INDEX IF NOT EXISTS idx_workflow_type ON workflow_executions(workflow_type);
CREATE INDEX IF NOT EXISTS idx_stage_workflow ON workflow_stage_executions(workflow_id, stage_name);
CREATE INDEX IF NOT EXISTS idx_symbol_workflow ON workflow_symbol_states(workflow_id, symbol);
```

### 6.2 Workflow Orchestrator

```python
class WorkflowOrchestrator:
    """Orchestrates multi-stage workflow with gates and recovery"""

    def __init__(self):
        self.gates = {
            'ingestion': DataIngestionGate(),
            'indicators': IndicatorComputationGate(),
            'signals': SignalGenerationGate(),
        }
        self.retry_policy = RetryPolicy()
        self.checkpoint = WorkflowCheckpoint()
        self.dlq = DeadLetterQueue()

    def execute_workflow(self, workflow_type: str, symbols: List[str]) -> WorkflowResult:
        """Execute workflow with fail-fast gates"""
        workflow_id = str(uuid.uuid4())

        # Create workflow execution record
        self._create_workflow_execution(workflow_id, workflow_type, symbols)

        try:
            # Stage 1: Data Ingestion
            self._execute_stage(
                workflow_id, 'ingestion', symbols,
                self._ingest_data,
                gate=self.gates['ingestion']
            )

            # Stage 2: Indicator Computation
            self._execute_stage(
                workflow_id, 'indicators', symbols,
                self._compute_indicators,
                gate=self.gates['indicators'],
                depends_on='ingestion'
            )

            # Stage 3: Signal Generation
            self._execute_stage(
                workflow_id, 'signals', symbols,
                self._generate_signals,
                gate=self.gates['signals'],
                depends_on='indicators'
            )

            # Mark workflow as completed
            self._update_workflow_status(workflow_id, 'completed')

            return WorkflowResult(success=True, workflow_id=workflow_id)

        except WorkflowGateFailed as e:
            # Gate failed - fail fast
            self._update_workflow_status(workflow_id, 'failed', str(e))
            return WorkflowResult(success=False, workflow_id=workflow_id, error=str(e))

        except Exception as e:
            # Unexpected error - save checkpoint and add to DLQ
            self._update_workflow_status(workflow_id, 'failed', str(e))
            self.checkpoint.save_checkpoint(workflow_id, self.current_stage, {'symbols': symbols})
            return WorkflowResult(success=False, workflow_id=workflow_id, error=str(e))

    def _execute_stage(
        self,
        workflow_id: str,
        stage_name: str,
        symbols: List[str],
        stage_func: Callable,
        gate: Optional[Gate] = None,
        depends_on: Optional[str] = None
    ):
        """Execute a workflow stage with gate check"""
        # Check dependencies
        if depends_on:
            self._check_dependency(workflow_id, depends_on)

        # Create stage execution record
        stage_id = self._create_stage_execution(workflow_id, stage_name)

        try:
            # Execute stage for each symbol
            for symbol in symbols:
                try:
                    # Run stage function
                    stage_func(symbol)

                    # Check gate (fail-fast)
                    if gate:
                        gate_result = gate.check(symbol, date.today())
                        if not gate_result.passed:
                            raise WorkflowGateFailed(
                                f"Gate failed for {symbol} at stage {stage_name}: {gate_result.reason}",
                                action=gate_result.action
                            )

                    # Update symbol state
                    self._update_symbol_state(workflow_id, symbol, stage_name, 'completed')

                except Exception as e:
                    # Handle symbol-level failure
                    retry_count = self._get_retry_count(workflow_id, symbol, stage_name)

                    if self.retry_policy.should_retry(e, retry_count):
                        # Retry with backoff
                        delay = self.retry_policy.get_delay(retry_count)
                        time.sleep(delay)
                        self._increment_retry_count(workflow_id, symbol, stage_name)
                        # Retry the symbol
                        continue
                    else:
                        # Add to DLQ
                        self.dlq.add_failed_item(symbol, stage_name, str(e), {'workflow_id': workflow_id})
                        self._update_symbol_state(workflow_id, symbol, stage_name, 'failed', str(e))

            # Mark stage as completed
            self._update_stage_status(stage_id, 'completed')

        except WorkflowGateFailed:
            # Gate failed - fail entire stage
            self._update_stage_status(stage_id, 'failed')
            raise
        except Exception as e:
            # Stage failed
            self._update_stage_status(stage_id, 'failed', str(e))
            raise
```

---

## 7. Implementation Plan

### Phase 1: Foundation (Week 1)

1. ✅ Create workflow tables (migration)
2. ✅ Implement `WorkflowOrchestrator` base class
3. ✅ Implement fail-fast gates
4. ✅ Add workflow state tracking

### Phase 2: Integration (Week 2)

1. ✅ Refactor `BatchWorker` to use `WorkflowOrchestrator`
2. ✅ Add retry logic with exponential backoff
3. ✅ Implement checkpoint/resume
4. ✅ Add Dead Letter Queue

### Phase 3: Monitoring (Week 3)

1. ✅ Add workflow progress dashboard
2. ✅ Add alerts for failed workflows
3. ✅ Add metrics for workflow performance
4. ✅ Add recovery scripts

### Phase 4: Optimization (Week 4)

1. ✅ Parallelize symbol processing
2. ✅ Optimize gate checks
3. ✅ Add caching for gate results
4. ✅ Performance tuning

---

## 8. Comparison: Current vs Proposed

| Aspect                     | Current               | Proposed                    | Industry Standard     |
| -------------------------- | --------------------- | --------------------------- | --------------------- |
| **Workflow Orchestration** | ❌ Sequential steps   | ✅ State machine with gates | ✅ Prefect/Celery     |
| **Fail-Fast**              | ❌ Continues on error | ✅ Gates between stages     | ✅ Pre-flight checks  |
| **Recovery**               | ❌ Logs only          | ✅ Retry + Checkpoint + DLQ | ✅ Automatic retry    |
| **State Management**       | ❌ No state           | ✅ Workflow tables          | ✅ State persistence  |
| **Audit**                  | ✅ Good               | ✅ Enhanced with workflow   | ✅ Full audit trail   |
| **Separation**             | ⚠️ Mixed              | ✅ Clear stages             | ✅ Raw/Clean/Computed |
| **Monitoring**             | ⚠️ Logs only          | ✅ Progress tracking        | ✅ Dashboards         |

---

## 9. Recommendations

### Immediate Actions (Critical)

1. **Implement Workflow Tables**

   - Create migration for workflow state management
   - Track workflow execution and stage progress

2. **Add Fail-Fast Gates**

   - Data ingestion gate
   - Indicator computation gate
   - Signal generation gate

3. **Implement Retry Logic**
   - Exponential backoff
   - Retry policy for transient errors
   - Skip retry for data quality issues

### Short-Term (Next Sprint)

4. **Refactor BatchWorker**

   - Use `WorkflowOrchestrator`
   - Add stage-by-stage execution
   - Add gate checks

5. **Add Recovery Mechanisms**
   - Checkpoint/resume
   - Dead Letter Queue
   - Manual recovery scripts

### Long-Term (Future)

6. **Consider Prefect**

   - If workflow complexity grows
   - For better visualization
   - For distributed execution

7. **Add Workflow Dashboard**
   - Real-time progress
   - Failed items view
   - Recovery actions

---

## 10. Conclusion

**Current System**: ✅ Good foundation, ⚠️ Missing workflow orchestration

**Industry Standard**: ✅ Robust pipeline with gates, recovery, and state management

**Gap**: Workflow orchestration, fail-fast gates, recovery mechanisms

**Recommendation**: Implement Phase 1-2 immediately for production readiness

**Risk**: Without these improvements, system is vulnerable to:

- Silent failures
- Data inconsistency
- No recovery from transient errors
- Poor visibility into workflow progress

**Benefit**: With improvements:

- ✅ Fail-fast prevents bad data propagation
- ✅ Recovery ensures data completeness
- ✅ State management enables monitoring
- ✅ Audit trail for compliance

---

## Appendix: Code Examples

See implementation files:

- `python-worker/app/workflows/orchestrator.py` (to be created)
- `python-worker/app/workflows/gates.py` (to be created)
- `python-worker/app/workflows/recovery.py` (to be created)
- `db/migrations/016_add_workflow_tables.sql` (to be created)
