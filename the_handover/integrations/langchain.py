"""LangChain integration for The Handover.

Provides a LangChain-compatible tool that gates agent actions behind
human approval. When the agent calls this tool, it blocks until the
approver responds. Denial raises an exception that stops the agent.

Usage::

    pip install the-handover[langchain]

    from the_handover import HandoverClient
    from the_handover.integrations.langchain import HandoverApprovalTool

    client = HandoverClient(api_key="ho_live_...")
    tool = HandoverApprovalTool(
        client=client,
        approver="admin@company.com",
    )

    # Use with any LangChain agent
    from langchain.agents import create_react_agent
    agent = create_react_agent(llm, [tool, ...other_tools], prompt)
"""

from __future__ import annotations

from typing import Any, Optional, Type, Union

from pydantic import BaseModel, Field

try:
    from langchain_core.tools import BaseTool
    from langchain_core.callbacks import CallbackManagerForToolRun
except ImportError:
    raise ImportError(
        "LangChain integration requires langchain-core. "
        "Install with: pip install the-handover[langchain]"
    )

from ..client import HandoverClient, ResponseTypeConfig
from ..exceptions import DecisionDenied, DecisionExpired


class ApprovalInput(BaseModel):
    """Input schema for the approval tool."""

    action: str = Field(description="What the agent wants to do — shown to the human approver")
    context: str = Field(default="", description="Additional context to help the approver decide")
    urgency: str = Field(default="medium", description="Urgency level: low, medium, high, critical")


class HandoverApprovalTool(BaseTool):
    """LangChain tool that requests human approval before proceeding.

    When called by an agent, this tool:
    1. Sends an approval request to the configured approver
    2. Blocks until the human responds
    3. Returns the approval result (approved/modified with notes)
    4. **Raises ToolException on denial** — LangChain handles this as a
       tool error, preventing the agent from proceeding with the action.

    The agent must call this tool BEFORE taking any sensitive action.
    The tool's response tells the agent whether it may proceed.
    """

    name: str = "request_human_approval"
    description: str = (
        "Request human approval before taking a sensitive action. "
        "Call this BEFORE executing any action that could be destructive, "
        "costly, or irreversible. Returns 'approved' or 'modified' with "
        "the approver's notes. Raises an error if denied."
    )
    args_schema: Type[BaseModel] = ApprovalInput

    # These are set in __init__ but declared for Pydantic
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

    def _run(
        self,
        action: str,
        context: str = "",
        urgency: str = "",
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
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
        except DecisionDenied as e:
            # Raising ToolException tells LangChain the tool failed —
            # the agent must respect the denial.
            from langchain_core.tools import ToolException

            raise ToolException(
                f"DENIED: The human approver denied this action: {action}. "
                f"You must NOT proceed with this action."
            ) from e
        except DecisionExpired as e:
            from langchain_core.tools import ToolException

            raise ToolException(
                f"EXPIRED: The approval request timed out for: {action}. "
                f"You must NOT proceed without approval."
            ) from e

        if decision.modified:
            notes = decision.response_notes or ""
            data = decision.response_data or {}
            return (
                f"MODIFIED: The approver wants changes before proceeding. "
                f"Notes: {notes}. Data: {data}. "
                f"Adjust your action accordingly."
            )

        if decision.response_data:
            return (
                f"APPROVED by {decision.resolved_by}. "
                f"Response data: {decision.response_data}"
            )

        return f"APPROVED by {decision.resolved_by}. You may proceed with: {action}"
