"""
Workflow Orchestrator
Industry Standard: Robust pipeline with gates, recovery, state management, and duplicate prevention
"""
import logging
import uuid
import json
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, date
from dataclasses import dataclass

from app.database import db
from app.workflows.gates import (
    DataIngestionGate,
    IndicatorComputationGate,
    SignalGenerationGate,
    GateResult
)
from app.workflows.recovery import RetryPolicy, WorkflowCheckpoint, DeadLetterQueue
from app.workflows.data_frequency import DataFrequency, IdempotentDataSaver
from app.workflows.exceptions import WorkflowGateFailed, WorkflowStageFailed

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """Result of workflow execution"""
    success: bool
    workflow_id: str
    error: Optional[str] = None
    symbols_processed: int = 0
    symbols_succeeded: int = 0
    symbols_failed: int = 0
    stages_completed: List[str] = None
    
    def __post_init__(self):
        if self.stages_completed is None:
            self.stages_completed = []


class WorkflowOrchestrator:
    """
    Orchestrates multi-stage workflow with gates, recovery, and duplicate prevention
    Industry Standard: Fail-fast gates, retry with backoff, checkpoint/resume, DLQ
    """
    
    def __init__(
        self,
        retry_policy: Optional[RetryPolicy] = None,
        checkpoint: Optional[WorkflowCheckpoint] = None,
        dlq: Optional[DeadLetterQueue] = None
    ):
        self.gates = {
            'ingestion': DataIngestionGate(),
            'indicators': IndicatorComputationGate(),
            'signals': SignalGenerationGate(),
        }
        self.retry_policy = retry_policy or RetryPolicy()
        self.checkpoint = checkpoint or WorkflowCheckpoint()
        self.dlq = dlq or DeadLetterQueue()
        self.current_stage = None
    
    def execute_workflow(
        self,
        workflow_type: str,
        symbols: List[str],
        data_frequency: DataFrequency = DataFrequency.DAILY,
        force: bool = False
    ) -> WorkflowResult:
        """
        Execute workflow with fail-fast gates and duplicate prevention
        
        Args:
            workflow_type: Type of workflow ('daily_batch', 'on_demand', 'recovery')
            symbols: List of symbols to process
            data_frequency: Data frequency (daily, quarterly, etc.)
            force: Force processing even if data exists
        
        Returns:
            WorkflowResult with execution status
        """
        workflow_id = str(uuid.uuid4())
        check_date = date.today()
        
        # Create workflow execution record
        self._create_workflow_execution(workflow_id, workflow_type, symbols, data_frequency)
        
        symbols_succeeded = 0
        symbols_failed = 0
        
        try:
            # Stage 1: Data Ingestion (with duplicate prevention)
            stage_result = self._execute_stage(
                workflow_id=workflow_id,
                stage_name='ingestion',
                symbols=symbols,
                stage_func=lambda s: self._ingest_data(s, data_frequency, force),
                gate=self.gates['ingestion'],
                check_date=check_date
            )
            symbols_succeeded += stage_result['succeeded']
            symbols_failed += stage_result['failed']
            
            if stage_result['failed'] > 0 and not force:
                logger.warning(f"⚠️ {stage_result['failed']} symbols failed ingestion stage")
            
            # Stage 2: Indicator Computation
            stage_result = self._execute_stage(
                workflow_id=workflow_id,
                stage_name='indicators',
                symbols=[s for s in symbols if self._symbol_passed_stage(workflow_id, s, 'ingestion')],
                stage_func=lambda s: self._compute_indicators(s),
                gate=self.gates['indicators'],
                depends_on='ingestion',
                check_date=check_date
            )
            symbols_succeeded += stage_result['succeeded']
            symbols_failed += stage_result['failed']
            
            # Stage 2.5: Financial Data Ingestion (Income Statements, Balance Sheets, Cash Flow)
            stage_result = self._execute_stage(
                workflow_id=workflow_id,
                stage_name='financial_data',
                symbols=[s for s in symbols if self._symbol_passed_stage(workflow_id, s, 'ingestion')],
                stage_func=lambda s: self._ingest_financial_data(s, force),
                gate=None,  # No gate for financial data (optional)
                depends_on='ingestion',
                check_date=check_date
            )
            symbols_succeeded += stage_result['succeeded']
            symbols_failed += stage_result['failed']
            
            # Stage 2.6: Weekly Data Aggregation (for swing trading)
            stage_result = self._execute_stage(
                workflow_id=workflow_id,
                stage_name='weekly_aggregation',
                symbols=[s for s in symbols if self._symbol_passed_stage(workflow_id, s, 'indicators')],
                stage_func=lambda s: self._aggregate_weekly_data(s, force),
                gate=None,  # No gate for aggregation (optional)
                depends_on='indicators',
                check_date=check_date
            )
            symbols_succeeded += stage_result['succeeded']
            symbols_failed += stage_result['failed']
            
            # Stage 2.7: Growth Calculations (from financial statements)
            stage_result = self._execute_stage(
                workflow_id=workflow_id,
                stage_name='growth_calculations',
                symbols=[s for s in symbols if self._symbol_passed_stage(workflow_id, s, 'financial_data')],
                stage_func=lambda s: self._calculate_growth_metrics(s, force),
                gate=None,  # No gate for calculations (optional)
                depends_on='financial_data',
                check_date=check_date
            )
            symbols_succeeded += stage_result['succeeded']
            symbols_failed += stage_result['failed']
            
            # Stage 3: Signal Generation
            stage_result = self._execute_stage(
                workflow_id=workflow_id,
                stage_name='signals',
                symbols=[s for s in symbols if self._symbol_passed_stage(workflow_id, s, 'indicators')],
                stage_func=lambda s: self._generate_signals(s),
                gate=self.gates['signals'],
                depends_on='indicators',
                check_date=check_date
            )
            symbols_succeeded += stage_result['succeeded']
            symbols_failed += stage_result['failed']
            
            # Mark workflow as completed
            self._update_workflow_status(workflow_id, 'completed', {
                'symbols_succeeded': symbols_succeeded,
                'symbols_failed': symbols_failed,
                'total_symbols': len(symbols)
            })
            
            return WorkflowResult(
                success=True,
                workflow_id=workflow_id,
                symbols_processed=len(symbols),
                symbols_succeeded=symbols_succeeded,
                symbols_failed=symbols_failed,
                stages_completed=['ingestion', 'indicators', 'signals']
            )
            
        except WorkflowGateFailed as e:
            # Gate failed - fail fast
            self._update_workflow_status(workflow_id, 'failed', {'error': str(e), 'gate': e.gate_name})
            return WorkflowResult(
                success=False,
                workflow_id=workflow_id,
                error=f"Gate failed: {str(e)}",
                symbols_processed=len(symbols),
                symbols_succeeded=symbols_succeeded,
                symbols_failed=symbols_failed
            )
        
        except Exception as e:
            # Unexpected error - save checkpoint and add to DLQ
            self._update_workflow_status(workflow_id, 'failed', {'error': str(e)})
            self.checkpoint.save_checkpoint(workflow_id, self.current_stage or 'unknown', {
                'symbols': symbols,
                'data_frequency': data_frequency.value
            })
            logger.error(f"❌ Workflow {workflow_id} failed: {e}", exc_info=True)
            return WorkflowResult(
                success=False,
                workflow_id=workflow_id,
                error=str(e),
                symbols_processed=len(symbols),
                symbols_succeeded=symbols_succeeded,
                symbols_failed=symbols_failed
            )
    
    def _execute_stage(
        self,
        workflow_id: str,
        stage_name: str,
        symbols: List[str],
        stage_func: Callable,
        gate: Optional[Any] = None,
        depends_on: Optional[str] = None,
        check_date: Optional[date] = None
    ) -> Dict[str, int]:
        """Execute a workflow stage with gate check and duplicate prevention"""
        self.current_stage = stage_name
        
        # Check dependencies
        if depends_on:
            self._check_dependency(workflow_id, depends_on)
        
        # Create stage execution record
        stage_id = self._create_stage_execution(workflow_id, stage_name)
        
        succeeded = 0
        failed = 0
        
        try:
            # Execute stage for each symbol
            for symbol in symbols:
                symbol_state_id = None
                try:
                    # Create symbol state record
                    symbol_state_id = self._create_symbol_state(workflow_id, symbol, stage_name, 'running')
                    
                    # Run stage function
                    stage_func(symbol)
                    
                    # Check gate (fail-fast)
                    if gate and check_date:
                        gate_result = gate.check(symbol, check_date, workflow_id)
                        if not gate_result.passed:
                            raise WorkflowGateFailed(
                                f"Gate failed for {symbol} at stage {stage_name}: {gate_result.reason}",
                                action=gate_result.action,
                                gate_name=gate.__class__.__name__
                            )
                    
                    # Update symbol state
                    self._update_symbol_state(workflow_id, symbol, stage_name, 'completed')
                    succeeded += 1
                    
                except WorkflowGateFailed as e:
                    # Gate failed - fail this symbol
                    self._update_symbol_state(workflow_id, symbol, stage_name, 'failed', str(e))
                    self.dlq.add_failed_item(workflow_id, symbol, stage_name, e, {
                        'gate_name': e.gate_name,
                        'action': e.action
                    })
                    failed += 1
                    logger.error(f"❌ Gate failed for {symbol} at {stage_name}: {e}")
                    
                except Exception as e:
                    # Handle symbol-level failure
                    retry_count = self._get_retry_count(workflow_id, symbol, stage_name)
                    
                    if self.retry_policy.should_retry(e, retry_count):
                        # Retry with backoff
                        self._update_symbol_state(workflow_id, symbol, stage_name, 'retrying', str(e))
                        self._increment_retry_count(workflow_id, symbol, stage_name)
                        self.retry_policy.wait_for_retry(retry_count)
                        
                        # Retry the symbol
                        try:
                            stage_func(symbol)
                            if gate and check_date:
                                gate_result = gate.check(symbol, check_date, workflow_id)
                                if not gate_result.passed:
                                    raise WorkflowGateFailed(
                                        f"Gate failed on retry: {gate_result.reason}",
                                        action=gate_result.action
                                    )
                            self._update_symbol_state(workflow_id, symbol, stage_name, 'completed')
                            succeeded += 1
                        except Exception as retry_error:
                            # Retry failed - add to DLQ
                            self._update_symbol_state(workflow_id, symbol, stage_name, 'failed', str(retry_error))
                            self.dlq.add_failed_item(workflow_id, symbol, stage_name, retry_error, {
                                'retry_count': retry_count + 1
                            })
                            failed += 1
                    else:
                        # Not retryable - add to DLQ
                        self._update_symbol_state(workflow_id, symbol, stage_name, 'failed', str(e))
                        self.dlq.add_failed_item(workflow_id, symbol, stage_name, e, {
                            'retry_count': retry_count
                        })
                        failed += 1
                        logger.error(f"❌ Failed {symbol} at {stage_name}: {e}")
            
            # Mark stage as completed
            self._update_stage_status(stage_id, 'completed', {
                'symbols_succeeded': succeeded,
                'symbols_failed': failed
            })
            
            return {'succeeded': succeeded, 'failed': failed}
            
        except WorkflowGateFailed:
            # Gate failed - fail entire stage
            self._update_stage_status(stage_id, 'failed')
            raise
        except Exception as e:
            # Stage failed
            self._update_stage_status(stage_id, 'failed', {'error': str(e)})
            raise WorkflowStageFailed(f"Stage {stage_name} failed: {str(e)}", stage=stage_name)
    
    def _ingest_data(self, symbol: str, data_frequency: DataFrequency, force: bool):
        """
        Ingest data with duplicate prevention
        
        Industry Standard: Use idempotent operations - safe to retry/re-run
        """
        from app.data_management.refresh_manager import DataRefreshManager
        from app.services.data_fetcher import DataFetcher
        from app.data_validation import DataValidator
        
        refresh_manager = DataRefreshManager()
        fetcher = DataFetcher()
        validator = DataValidator()
        
        # Fetch data
        data = refresh_manager.data_source.fetch_price_data(symbol, period="1y")
        
        if data is None or data.empty:
            raise ValueError(f"No data returned for {symbol}")
        
        # Validate data
        validation_report = validator.validate(data, symbol, "price_historical")
        if validation_report.overall_status == "fail":
            raise ValueError(f"Data validation failed for {symbol}: {validation_report.critical_issues} critical issues")
        
        # Clean data
        cleaned_data, cleaned_report = validator.validate_and_clean(data, symbol, "price_historical")
        
        # Save validation report to database (required for gate checks)
        # Fail-fast: Gate depends on this, so we raise on error
        validation_report_id = refresh_manager._save_validation_report(cleaned_report)
        if not validation_report_id:
            raise ValueError(f"Failed to save validation report for {symbol} - gate check will fail")
        
        # Use idempotent data saver for duplicate prevention
        saver = IdempotentDataSaver(data_frequency)
        result = saver.save_market_data(symbol, cleaned_data, data_source='yahoo_finance', force=force)
        
        logger.info(f"✅ Ingested {symbol}: {result['rows_inserted']} inserted, {result['rows_updated']} updated, {result['duplicates_prevented']} duplicates prevented")
    
    def _compute_indicators(self, symbol: str):
        """Compute indicators"""
        from app.services.indicator_service import IndicatorService
        
        service = IndicatorService()
        success = service.calculate_indicators(symbol)
        if not success:
            raise ValueError(f"Failed to calculate indicators for {symbol}")
    
    def _generate_signals(self, symbol: str):
        """Generate signals"""
        from app.services.strategy_service import StrategyService
        from app.strategies import DEFAULT_STRATEGY
        
        # Signals are generated on-demand or during batch
        # This is a placeholder - actual signal generation happens elsewhere
        logger.debug(f"Signal generation for {symbol} (handled by strategy service)")
    
    def _ingest_financial_data(self, symbol: str, force: bool):
        """Ingest financial data (income statements, balance sheets, cash flow)"""
        from app.data_management.refresh_manager import DataRefreshManager
        from app.data_management.refresh_strategy import DataType, RefreshMode
        
        refresh_manager = DataRefreshManager()
        
        # Refresh financial statements using refresh_data which supports force parameter
        financial_data_types = [
            DataType.INCOME_STATEMENTS,
            DataType.BALANCE_SHEETS,
            DataType.CASH_FLOW_STATEMENTS,
            DataType.FINANCIAL_RATIOS
        ]
        
        for data_type in financial_data_types:
            try:
                result = refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[data_type],
                    mode=RefreshMode.ON_DEMAND,
                    force=force
                )
                if result.total_failed > 0:
                    logger.warning(f"⚠️ Failed to refresh {data_type.value} for {symbol}")
            except Exception as e:
                logger.warning(f"⚠️ Error refreshing {data_type.value} for {symbol}: {e}")
                # Continue with other data types - financial data is optional
        
        logger.info(f"✅ Financial data ingestion completed for {symbol}")
    
    def _aggregate_weekly_data(self, symbol: str, force: bool):
        """Aggregate daily data to weekly timeframe for swing trading"""
        from app.services.data_aggregation_service import DataAggregationService
        
        service = DataAggregationService()
        result = service.aggregate_to_weekly(symbol, force=force)
        
        if not result.get('success'):
            raise ValueError(f"Weekly aggregation failed for {symbol}: {result.get('error', 'Unknown error')}")
        
        logger.info(f"✅ Weekly aggregation completed for {symbol}: {result.get('rows_created', 0)} bars")
    
    def _calculate_growth_metrics(self, symbol: str, force: bool):
        """Calculate growth metrics from financial statements"""
        from app.services.growth_calculation_service import GrowthCalculationService
        
        service = GrowthCalculationService()
        result = service.calculate_growth_metrics(symbol, force=force)
        
        if not result.get('success'):
            # Growth calculation is optional - log warning but don't fail
            logger.warning(f"⚠️ Growth calculation failed for {symbol}: {result.get('error', 'Unknown error')}")
            return
        
        metrics = result.get('metrics', {})
        logger.info(f"✅ Growth metrics calculated for {symbol}: {metrics}")
    
    # Database helper methods
    def _create_workflow_execution(
        self,
        workflow_id: str,
        workflow_type: str,
        symbols: List[str],
        data_frequency: DataFrequency
    ):
        """Create workflow execution record"""
        db.execute_update(
            """
            INSERT INTO workflow_executions
            (workflow_id, workflow_type, status, current_stage, started_at, metadata_json)
            VALUES (:workflow_id, :workflow_type, 'running', 'ingestion', CURRENT_TIMESTAMP, :metadata)
            """,
            {
                "workflow_id": workflow_id,
                "workflow_type": workflow_type,
                "metadata": json.dumps({
                    "symbols": symbols,
                    "symbol_count": len(symbols),
                    "data_frequency": data_frequency.value
                })
            }
        )
    
    def _update_workflow_status(self, workflow_id: str, status: str, metadata: Optional[Dict] = None):
        """Update workflow status"""
        db.execute_update(
            """
            UPDATE workflow_executions
            SET status = :status,
                current_stage = NULL,
                completed_at = CASE WHEN :status IN ('completed', 'failed') THEN CURRENT_TIMESTAMP ELSE completed_at END,
                metadata_json = :metadata,
                updated_at = CURRENT_TIMESTAMP
            WHERE workflow_id = :workflow_id
            """,
            {
                "workflow_id": workflow_id,
                "status": status,
                "metadata": json.dumps(metadata or {})
            }
        )
    
    def _create_stage_execution(self, workflow_id: str, stage_name: str) -> str:
        """Create stage execution record"""
        stage_id = str(uuid.uuid4())
        db.execute_update(
            """
            INSERT INTO workflow_stage_executions
            (stage_execution_id, workflow_id, stage_name, status, started_at)
            VALUES (:stage_id, :workflow_id, :stage_name, 'running', CURRENT_TIMESTAMP)
            """,
            {
                "stage_id": stage_id,
                "workflow_id": workflow_id,
                "stage_name": stage_name
            }
        )
        return stage_id
    
    def _update_stage_status(self, stage_id: str, status: str, metadata: Optional[Dict] = None):
        """Update stage status"""
        db.execute_update(
            """
            UPDATE workflow_stage_executions
            SET status = :status,
                completed_at = CASE WHEN :status IN ('completed', 'failed') THEN CURRENT_TIMESTAMP ELSE completed_at END,
                symbols_succeeded = :succeeded,
                symbols_failed = :failed,
                updated_at = CURRENT_TIMESTAMP
            WHERE stage_execution_id = :stage_id
            """,
            {
                "stage_id": stage_id,
                "status": status,
                "succeeded": metadata.get('symbols_succeeded', 0) if metadata else 0,
                "failed": metadata.get('symbols_failed', 0) if metadata else 0
            }
        )
    
    def _create_symbol_state(self, workflow_id: str, symbol: str, stage: str, status: str) -> str:
        """Create symbol state record"""
        db.execute_update(
            """
            INSERT OR REPLACE INTO workflow_symbol_states
            (workflow_id, symbol, stage, status, started_at, updated_at)
            VALUES (:workflow_id, :symbol, :stage, :status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            {
                "workflow_id": workflow_id,
                "symbol": symbol,
                "stage": stage,
                "status": status
            }
        )
        return f"{workflow_id}_{symbol}_{stage}"
    
    def _update_symbol_state(self, workflow_id: str, symbol: str, stage: str, status: str, error: Optional[str] = None):
        """Update symbol state"""
        db.execute_update(
            """
            UPDATE workflow_symbol_states
            SET status = :status,
                error_message = :error,
                completed_at = CASE WHEN :status IN ('completed', 'failed') THEN CURRENT_TIMESTAMP ELSE completed_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE workflow_id = :workflow_id AND symbol = :symbol AND stage = :stage
            """,
            {
                "workflow_id": workflow_id,
                "symbol": symbol,
                "stage": stage,
                "status": status,
                "error": error
            }
        )
    
    def _symbol_passed_stage(self, workflow_id: str, symbol: str, stage: str) -> bool:
        """Check if symbol passed a stage"""
        result = db.execute_query(
            """
            SELECT status FROM workflow_symbol_states
            WHERE workflow_id = :workflow_id AND symbol = :symbol AND stage = :stage
            """,
            {"workflow_id": workflow_id, "symbol": symbol, "stage": stage}
        )
        return result and result[0]['status'] == 'completed'
    
    def _check_dependency(self, workflow_id: str, depends_on: str):
        """Check if dependency stage completed"""
        result = db.execute_query(
            """
            SELECT status FROM workflow_stage_executions
            WHERE workflow_id = :workflow_id AND stage_name = :stage
            ORDER BY started_at DESC LIMIT 1
            """,
            {"workflow_id": workflow_id, "stage": depends_on}
        )
        if not result or result[0]['status'] != 'completed':
            raise WorkflowStageFailed(f"Dependency {depends_on} not completed", stage=depends_on)
    
    def _get_retry_count(self, workflow_id: str, symbol: str, stage: str) -> int:
        """Get retry count for symbol at stage"""
        result = db.execute_query(
            """
            SELECT retry_count FROM workflow_symbol_states
            WHERE workflow_id = :workflow_id AND symbol = :symbol AND stage = :stage
            """,
            {"workflow_id": workflow_id, "symbol": symbol, "stage": stage}
        )
        return result[0]['retry_count'] if result else 0
    
    def _increment_retry_count(self, workflow_id: str, symbol: str, stage: str):
        """Increment retry count"""
        db.execute_update(
            """
            UPDATE workflow_symbol_states
            SET retry_count = retry_count + 1
            WHERE workflow_id = :workflow_id AND symbol = :symbol AND stage = :stage
            """,
            {"workflow_id": workflow_id, "symbol": symbol, "stage": stage}
        )

