"""The Handover — Human-in-the-loop approval SDK for AI agents."""

from .client import HandoverClient
from .models import (
    Decision,
    DecisionStatus,
    ResponseType,
    ApprovalPolicy,
    AmountRule,
    DEFAULT_POLICY,
    DEFAULT_KEYWORDS,
    ChooseResponse,
    TextInputResponse,
    NumberInputResponse,
    ConfirmResponse,
    ScheduleResponse,
    FileUploadResponse,
    Attachment,
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
    "ApprovalPolicy",
    "AmountRule",
    "DEFAULT_POLICY",
    "DEFAULT_KEYWORDS",
    "ChooseResponse",
    "TextInputResponse",
    "NumberInputResponse",
    "ConfirmResponse",
    "ScheduleResponse",
    "FileUploadResponse",
    "Attachment",
    "HandoverError",
    "DecisionDenied",
    "DecisionExpired",
    "DecisionTimeout",
    "ApprovalRequired",
    "require_approval",
]

__version__ = "0.2.0"
