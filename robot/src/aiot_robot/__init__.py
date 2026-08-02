"""Jetson-side runtime primitives for the Hanbakwi patrol robot."""

from .backend_client import BackendConfig, BackendError, RobotBackendClient
from .contracts import AiStatus, ContractError, DetectionEvent
from .gate import AiGate, GateDecision

__all__ = [
    "AiGate",
    "AiStatus",
    "BackendConfig",
    "BackendError",
    "ContractError",
    "DetectionEvent",
    "GateDecision",
    "RobotBackendClient",
]
