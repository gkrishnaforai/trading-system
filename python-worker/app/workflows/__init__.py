"""
Workflow Orchestration Module
Industry Standard: Robust pipeline with gates, recovery, and state management
"""

from app.workflows.gates import (
    GateResult,
    DataIngestionGate,
    IndicatorComputationGate,
    SignalGenerationGate
)
from app.workflows.recovery import RetryPolicy, WorkflowCheckpoint, DeadLetterQueue
from app.workflows.data_frequency import (
    DataFrequency,
    DuplicatePreventionStrategy,
    IdempotentDataSaver
)
from app.workflows.exceptions import (
    WorkflowException,
    WorkflowGateFailed,
    WorkflowStageFailed,
    DuplicateDataError
)

__all__ = [
    'GateResult',
    'DataIngestionGate',
    'IndicatorComputationGate',
    'SignalGenerationGate',
    'RetryPolicy',
    'WorkflowCheckpoint',
    'DeadLetterQueue',
    'DataFrequency',
    'DuplicatePreventionStrategy',
    'IdempotentDataSaver',
    'WorkflowException',
    'WorkflowGateFailed',
    'WorkflowStageFailed',
    'DuplicateDataError'
]

# WorkflowOrchestrator will be imported when created
try:
    from app.workflows.orchestrator import WorkflowOrchestrator
    __all__.append('WorkflowOrchestrator')
except ImportError:
    pass

