"""CrewAI integration for The Handover.

Provides a CrewAI-compatible tool that gates agent actions behind
human approval.

Usage::

    pip install the-handover[crewai]

    from the_handover import HandoverClient
    from the_handover.integrations.crewai import HandoverApprovalTool

    client = HandoverClient(api_key="ho_live_...")
    tool = HandoverApprovalTool(
        client=client,
        approver="admin@company.com",
    )

    # Use in a CrewAI agent
    from crewai import Agent
    agent = Agent(
        role="Operations Manager",
        tools=[tool],
        ...
    )
"""

from __future__ import annotations

from typing import Any, Optional

try:
    from crewai.tools import BaseTool as CrewAIBaseTool
except ImportError:
    raise ImportError(
        "CrewAI integration requires crewai. "
        "Install with: pip install the-handover[crewai]"
    )

from ..client import HandoverClient, ResponseTypeConfig
from ..exceptions import DecisionDenied, DecisionExpired


class HandoverApprovalTool(CrewAIBaseTool):
    """CrewAI tool that enforces human approval before sensitive actions.

    When an agent calls this tool, it blocks until the approver responds.
    Denial raises an exception that stops the agent.
    """

    name: str = "request_human_approval"
    description: str = (
        "Request human approval before taking a sensitive, destructive, or "
        "costly action. Provide a clear description of what you want to do "
        "and why. Returns the approval status and any instructions from the "
        "approver. If denied, you MUST stop and NOT proceed."
    )

    client: Any = None
    approver: str = ""
    default_urgency: str = "medium"
    channel: str = "email"
    timeout_minutes: int = 60
    response_type: Any = None

    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        client: HandoverClient,
        approver: str,
        *,
        default_urgency: str = "medium",
        channel: str = "email",
        timeout_minutes: int = 60,
        response_type: Optional[ResponseTypeConfig] = None,
        **kwargs: Any,
    ):
        super().__init__(
            client=client,
            approver=approver,
            default_urgency=default_urgency,
            channel=channel,
            timeout_minutes=timeout_minutes,
            response_type=response_type,
            **kwargs,
        )

    def _run(self, action: str, context: str = "", urgency: str = "") -> str:
        try:
            decision = self.client.approve(
                action=action,
                approver=self.approver,
                context=context or None,
                urgency=urgency or self.default_urgency,
                timeout_minutes=self.timeout_minutes,
                channel=self.channel,
                response_type=self.response_type,
            )
        except DecisionDenied:
            return (
                "DENIED: The human approver has denied this action. "
                "You MUST NOT proceed. Find an alternative approach or stop."
            )
        except DecisionExpired:
            return (
                "EXPIRED: The approval request timed out. "
                "You MUST NOT proceed without approval."
            )

        if decision.modified:
            return (
                f"MODIFIED: Approval granted with changes requested. "
                f"Notes: {decision.response_notes}. "
                f"Data: {decision.response_data}. "
                f"Adjust your approach accordingly."
            )

        if decision.response_data:
            return (
                f"APPROVED by {decision.resolved_by}. "
                f"Response: {decision.response_data}. "
                f"You may proceed."
            )

        return f"APPROVED by {decision.resolved_by}. You may proceed with: {action}"
