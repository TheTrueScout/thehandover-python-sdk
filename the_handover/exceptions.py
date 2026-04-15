"""Exceptions for The Handover SDK.

These exceptions enforce agent behaviour — a denied decision raises an
exception that the agent cannot silently ignore. This is the core mechanism
that makes The Handover's SDK-level enforcement work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .models import Decision


class HandoverError(Exception):
    """Base exception for all Handover errors."""

    pass


class DecisionDenied(HandoverError):
    """Raised when an approver denies an action.

    This exception STOPS the agent from proceeding. The agent must handle
    this explicitly — it cannot be silently ignored in normal control flow.
    """

    def __init__(self, decision: Decision, message: str = ""):
        self.decision = decision
        msg = message or f"Action denied by {decision.resolved_by}: {decision.action}"
        super().__init__(msg)


class DecisionExpired(HandoverError):
    """Raised when a decision times out without a response."""

    def __init__(self, decision: Decision, message: str = ""):
        self.decision = decision
        msg = message or f"Decision expired: {decision.action}"
        super().__init__(msg)


class DecisionTimeout(HandoverError):
    """Raised when polling exceeds the max wait time."""

    def __init__(self, decision_id: str, message: str = ""):
        self.decision_id = decision_id
        msg = message or f"Timed out waiting for decision {decision_id}"
        super().__init__(msg)


class ApprovalRequired(HandoverError):
    """Raised when a function decorated with @require_approval is called
    without approval. The agent should request approval and retry."""

    def __init__(self, action: str, message: str = ""):
        self.action = action
        msg = message or f"Approval required before executing: {action}"
        super().__init__(msg)
