"""Data models for The Handover SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DecisionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    MODIFIED = "modified"
    EXPIRED = "expired"
    ESCALATED = "escalated"
    SCHEDULED = "scheduled"


class ResponseType(str, Enum):
    APPROVE_DENY = "approve_deny"
    CHOOSE = "choose"
    TEXT_INPUT = "text_input"
    NUMBER_INPUT = "number_input"
    CONFIRM = "confirm"


@dataclass
class ChooseResponse:
    """Ask the approver to pick from a list of choices."""

    choices: list[str]
    label: str = "Select an option"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "choose", "choices": self.choices, "label": self.label}


@dataclass
class TextInputResponse:
    """Ask the approver to fill in named text fields."""

    fields: list[dict[str, Any]]
    """Each field: {"name": str, "label": str, "required": bool, "placeholder": str}"""

    def to_dict(self) -> dict[str, Any]:
        return {"type": "text_input", "fields": self.fields}

    @staticmethod
    def field(
        name: str,
        label: str,
        required: bool = False,
        placeholder: str = "",
    ) -> dict[str, Any]:
        """Helper to build a field definition."""
        return {
            "name": name,
            "label": label,
            "required": required,
            "placeholder": placeholder,
        }


@dataclass
class NumberInputResponse:
    """Ask the approver for a number."""

    label: str = "Enter a value"
    min: Optional[float] = None
    max: Optional[float] = None
    placeholder: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": "number_input", "label": self.label}
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        if self.placeholder:
            d["placeholder"] = self.placeholder
        return d


@dataclass
class ConfirmResponse:
    """Simple confirm/decline — no extra input."""

    def to_dict(self) -> dict[str, Any]:
        return {"type": "confirm"}


@dataclass
class ScheduleResponse:
    """Let the approver pick *when* the action should run.

    The approver sees a date/time picker alongside the standard Approve/Deny
    buttons.  When they pick a future time the decision status becomes
    ``scheduled`` and ``Decision.execute_at`` holds the chosen ISO-8601
    timestamp.  :meth:`~the_handover.HandoverClient.approve` will sleep until
    that moment before returning, so the calling agent proceeds at exactly the
    right time with no extra work.

    Example::

        from the_handover import ScheduleResponse

        decision = client.approve(
            action="Run nightly database vacuum",
            approver="ops@company.com",
            response_type=ScheduleResponse(label="When should the vacuum run?"),
        )
        # Execution resumes at the time the approver chose.
    """

    label: str = "When should this run?"
    allow_immediate: bool = True
    """Whether the approver may also click 'Run now' instead of picking a time."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "schedule",
            "label": self.label,
            "allow_immediate": self.allow_immediate,
        }


@dataclass
class Decision:
    """Represents a resolved or pending decision."""

    id: str
    status: DecisionStatus
    action: str = ""
    context: Optional[str] = None
    urgency: str = "medium"
    response_notes: Optional[str] = None
    response_data: Optional[dict[str, Any]] = None
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    execute_at: Optional[str] = None
    """ISO-8601 timestamp set when the approver schedules the action for a
    future time.  Only present when ``status == DecisionStatus.SCHEDULED``."""

    @property
    def approved(self) -> bool:
        return self.status == DecisionStatus.APPROVED

    @property
    def denied(self) -> bool:
        return self.status == DecisionStatus.DENIED

    @property
    def modified(self) -> bool:
        return self.status == DecisionStatus.MODIFIED

    @property
    def scheduled(self) -> bool:
        return self.status == DecisionStatus.SCHEDULED

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Decision:
        return cls(
            id=data.get("id", ""),
            status=DecisionStatus(data.get("status", "pending")),
            action=data.get("action", ""),
            context=data.get("context"),
            urgency=data.get("urgency", "medium"),
            response_notes=data.get("response_notes"),
            response_data=data.get("response_data"),
            resolved_at=data.get("resolved_at"),
            resolved_by=data.get("resolved_by"),
            expires_at=data.get("expires_at"),
            created_at=data.get("created_at"),
            execute_at=data.get("execute_at"),
        )
