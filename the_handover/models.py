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
    SCHEDULE = "schedule"
    FILE_UPLOAD = "file_upload"


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
    buttons.  Picking a future time sets the decision status to
    :attr:`DecisionStatus.SCHEDULED` and populates :attr:`Decision.execute_at`
    with the chosen ISO-8601 timestamp.

    :meth:`HandoverClient.approve` automatically sleeps until that moment
    before returning, so the calling agent proceeds at exactly the right time.
    """

    label: str = "When should this run?"
    allow_immediate: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "schedule",
            "label": self.label,
            "allow_immediate": self.allow_immediate,
        }


@dataclass
class FileUploadResponse:
    """Ask the approver to upload one or more files as their response.

    The uploaded files appear in :attr:`Decision.response_data` under the
    ``uploaded_files`` key, each as ``{"name", "url", "type", "size"}``.
    """

    label: str = "Upload files"
    max_files: int = 5
    accept: Optional[list[str]] = None
    """MIME types or extensions accepted, e.g. ``["image/*", ".pdf"]``."""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": "file_upload",
            "label": self.label,
            "max_files": self.max_files,
        }
        if self.accept:
            d["accept"] = self.accept
        return d


@dataclass
class Attachment:
    """A file attached to a decision (either by the agent as context for the
    approver, or uploaded by the approver as part of their response)."""

    name: str
    url: str
    type: str
    size: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Attachment:
        return cls(
            name=data.get("name", ""),
            url=data.get("url", ""),
            type=data.get("type", ""),
            size=int(data.get("size", 0)),
        )


# ── Approval policy ───────────────────────────────────────────────────────────

_URGENCY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass
class AmountRule:
    """Require approval when a numeric amount meets or exceeds a threshold.

    Pass ``amount=`` to :meth:`~the_handover.HandoverClient.approve` and the
    SDK will compare it against every ``AmountRule`` in the active policy.

    Args:
        threshold: The minimum value (inclusive) that triggers approval.
        keywords: If provided, the rule only fires when the action text also
            contains at least one of these strings (case-insensitive).  Leave
            empty to apply the threshold to *any* action that carries an amount.
        currency: Informational label shown in log/debug output (e.g. ``"USD"``).
            The SDK does not convert currencies — pass amounts in a consistent
            unit.

    Example::

        from the_handover import ApprovalPolicy, AmountRule

        policy = ApprovalPolicy(
            amount_rules=[
                # Flag any payment over $100
                AmountRule(
                    threshold=100.0,
                    keywords=["payment", "charge", "transfer", "refund"],
                    currency="USD",
                ),
                # Flag any crypto transfer over 0.1 BTC regardless of keyword
                AmountRule(threshold=0.1, currency="BTC"),
            ]
        )
    """

    threshold: float
    keywords: list[str] = field(default_factory=list)
    currency: str = ""

    def matches(self, action: str, amount: float) -> bool:
        """Return ``True`` if this rule should trigger for the given action/amount."""
        if amount < self.threshold:
            return False
        if not self.keywords:
            return True
        action_lower = action.lower()
        return any(kw.lower() in action_lower for kw in self.keywords)


#: Keywords that commonly indicate a write, destructive, or high-risk action.
#: Used by :data:`DEFAULT_POLICY`.  Override by passing your own list to
#: :class:`ApprovalPolicy`.
DEFAULT_KEYWORDS: list[str] = [
    # Destructive / write operations
    "delete", "remove", "drop", "truncate", "purge", "wipe", "erase",
    "update", "modify", "edit", "patch", "overwrite", "replace",
    "create", "insert", "add", "write", "upload", "import",
    # Outbound communications
    "send", "email", "notify", "message", "post", "publish", "broadcast",
    "announce", "alert", "sms", "call", "webhook",
    # Financial
    "payment", "charge", "transfer", "refund", "invoice", "billing",
    "purchase", "buy", "subscribe", "withdraw", "deposit",
    # Infrastructure / deployments
    "deploy", "release", "migrate", "rollback", "restart", "reboot",
    "shutdown", "terminate", "provision", "scale",
    # Access / permissions
    "grant", "revoke", "invite", "ban", "block", "reset password",
]


@dataclass
class ApprovalPolicy:
    """Defines which agent actions require human approval.

    Attach a policy to :class:`~the_handover.HandoverClient` so you don't have
    to scatter approval logic through your agent code.  The agent always calls
    ``client.approve()``; the policy decides whether that becomes a real
    approval request or an instant auto-approval.

    Rules are **OR-combined**: if *any* rule matches, approval is required.
    With no rules set and ``always_require=False`` every action is auto-approved
    — start there in development, then tighten for production.

    Args:
        require_for_keywords: Approval required when the action text contains
            any of these strings (case-insensitive).
        require_for_urgency: Approval required when ``urgency`` is at or above
            this level.  ``"high"`` means both ``"high"`` and ``"critical"``
            trigger approval.
        amount_rules: Approval required when the caller passes ``amount=`` to
            :meth:`~the_handover.HandoverClient.approve` and the amount meets or
            exceeds the rule's threshold.  See :class:`AmountRule`.
        always_require: Require approval for every action regardless of rules.
        never_require: Skip approval for every action (auto-approve all).
            Useful in local dev / CI.

    Example::

        from the_handover import HandoverClient, ApprovalPolicy, AmountRule

        client = HandoverClient(
            api_key="ho_live_...",
            policy=ApprovalPolicy(
                require_for_keywords=["delete", "send", "deploy"],
                require_for_urgency="high",
                amount_rules=[
                    AmountRule(threshold=100.0,
                               keywords=["payment", "charge", "transfer"]),
                ],
            ),
        )

        # Triggers approval — "delete" keyword matched.
        client.approve(action="Delete 500 user records", approver="admin@co.com")

        # Triggers approval — amount $250 exceeds the $100 threshold.
        client.approve(action="Process payment", approver="finance@co.com", amount=250.0)

        # Auto-approves — no keyword match, low urgency, no amount.
        client.approve(action="Fetch user profile", approver="admin@co.com")
    """

    require_for_keywords: list[str] = field(default_factory=list)
    require_for_urgency: Optional[str] = None
    amount_rules: list[AmountRule] = field(default_factory=list)
    always_require: bool = False
    never_require: bool = False

    def should_require(
        self,
        action: str,
        urgency: str = "medium",
        amount: Optional[float] = None,
    ) -> bool:
        """Return ``True`` if this action needs human approval."""
        if self.never_require:
            return False
        if self.always_require:
            return True
        action_lower = action.lower()
        for kw in self.require_for_keywords:
            if kw.lower() in action_lower:
                return True
        if self.require_for_urgency:
            threshold = _URGENCY_RANK.get(self.require_for_urgency, 0)
            if _URGENCY_RANK.get(urgency, 1) >= threshold:
                return True
        if amount is not None:
            for rule in self.amount_rules:
                if rule.matches(action, amount):
                    return True
        return False


#: A ready-to-use policy that covers common risky action categories.
#: Pass it directly to :class:`~the_handover.HandoverClient` as a starting
#: point, then customise as needed.
#:
#: - Keywords: destructive writes, outbound comms, financial ops, infra changes,
#:   access/permission changes.
#: - Urgency: ``"high"`` and ``"critical"`` always require approval.
#: - Amount: financial actions over $100 require approval.
#:
#: Example::
#:
#:     from the_handover import HandoverClient, DEFAULT_POLICY
#:     client = HandoverClient(api_key="ho_live_...", policy=DEFAULT_POLICY)
DEFAULT_POLICY: ApprovalPolicy = ApprovalPolicy(
    require_for_keywords=DEFAULT_KEYWORDS,
    require_for_urgency="high",
    amount_rules=[
        AmountRule(
            threshold=100.0,
            keywords=["payment", "charge", "transfer", "refund", "invoice",
                      "purchase", "buy", "withdraw", "deposit", "billing"],
            currency="USD",
        ),
    ],
)


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
    context_images: Optional[list[str]] = None
    """HTTP(S) URLs of images the agent attached as context for the approver."""
    attachments: Optional[list[Attachment]] = None
    """Files the agent uploaded for the approver to review."""
    enforce: bool = False
    """When ``True``, the server computed :attr:`action_permitted`."""
    action_permitted: Optional[bool] = None
    """Present only when ``enforce=True``.  ``True`` means the action is
    approved and may proceed; ``False`` means it must not."""

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
        raw_attachments = data.get("attachments")
        attachments: Optional[list[Attachment]] = None
        if raw_attachments:
            attachments = [Attachment.from_dict(a) for a in raw_attachments]

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
            context_images=data.get("context_images"),
            attachments=attachments,
            enforce=bool(data.get("enforce", False)),
            action_permitted=data.get("action_permitted"),
        )
