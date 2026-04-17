"""The Handover — Human-in-the-loop approval SDK for AI agents."""

from .client import HandoverClient
from .models import (
    Decision,
    DecisionStatus,
    ResponseType,
    ChooseResponse,
    TextInputResponse,
    NumberInputResponse,
    ConfirmResponse,
    ScheduleResponse,
)
from .exceptions import (
    HandoverError,
    DecisionDenied,
    DecisionExpired,
    DecisionTimeout,
    ApprovalRequired,
)
from .enforcement import require_approval

__all__ = [
    "HandoverClient",
    "Decision",
    "DecisionStatus",
    "ResponseType",
    "ChooseResponse",
    "TextInputResponse",
    "NumberInputResponse",
    "ConfirmResponse",
    "ScheduleResponse",
    "HandoverError",
    "DecisionDenied",
    "DecisionExpired",
    "DecisionTimeout",
    "ApprovalRequired",
    "require_approval",
]

__version__ = "0.1.0"
