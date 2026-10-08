"""
Soak Testing & Reliability Automation Package
==============================================
P2-8: 7-Day Multi-Asset Continuous Soak Test, Failure Injection,
Recovery Verification & Operational Reliability Framework.
"""

from tools.soak.soak_controller import (
    SoakController,
    SoakConfig,
    SoakMode,
    SoakCheckpoint,
    SoakSummaryReport,
    ScheduledFault,
    FaultType,
    DEFAULT_168H_FAULT_SCHEDULE
)

__all__ = [
    "SoakController",
    "SoakConfig",
    "SoakMode",
    "SoakCheckpoint",
    "SoakSummaryReport",
    "ScheduledFault",
    "FaultType",
    "DEFAULT_168H_FAULT_SCHEDULE"
]
