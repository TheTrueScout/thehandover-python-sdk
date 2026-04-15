"""OpenAI integration for The Handover.

Provides helpers to use The Handover as an OpenAI function/tool that
enforces human approval in Assistants API or chat completions with
function calling.

Usage::

    pip install the-handover[openai]

    from the_handover import HandoverClient
    from the_handover.integrations.openai import (
        handover_tool_definition,
        handle_handover_call,
    )

    client = HandoverClient(api_key="ho_live_...")

    # Add to your OpenAI tools list
    tools = [handover_tool_definition(), ...your_other_tools]

    # In your tool call handler
    if tool_call.function.name == "request_human_approval":
        result = handle_handover_call(
            client,
            tool_call.function.arguments,
            approver="admin@company.com",
        )
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..client import HandoverClient, ResponseTypeConfig
from ..exceptions import DecisionDenied, DecisionExpired


def handover_tool_definition() -> dict[str, Any]:
    """Returns an OpenAI-compatible tool definition for human approval.

    Add this to your ``tools`` list when calling chat completions or
    creating an Assistant.
    """
    return {
        "type": "function",
        "function": {
            "name": "request_human_approval",
            "description": (
                "Request human approval before taking a sensitive, destructive, "
                "or costly action. Call this BEFORE executing the action. "
                "If the response says DENIED, you must NOT proceed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Clear description of what you want to do",
                    },
                    "context": {
                        "type": "string",
                        "description": "Why you want to do this and any relevant details",
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "How urgent is this action",
                    },
                },
                "required": ["action"],
            },
        },
    }


def handle_handover_call(
    client: HandoverClient,
    arguments: str | dict[str, Any],
    approver: str,
    *,
    channel: str = "email",
    timeout_minutes: int = 60,
    response_type: Optional[ResponseTypeConfig] = None,
) -> str:
    """Handle an OpenAI tool call for human approval.

    Returns a string result that should be sent back as the tool response.
    The model will read this to determine whether to proceed.

    Args:
        client: HandoverClient instance
        arguments: The function arguments from OpenAI (JSON string or dict)
        approver: Email of the approver
        channel: Notification channel
        timeout_minutes: How long to wait
        response_type: Rich response type config

    Returns:
        String result to return as the tool call output
    """
    if isinstance(arguments, str):
        args = json.loads(arguments)
    else:
        args = arguments

    action = args.get("action", "Unknown action")
    context = args.get("context")
    urgency = args.get("urgency", "medium")

    try:
        decision = client.approve(
            action=action,
            approver=approver,
            context=context,
            urgency=urgency,
            timeout_minutes=timeout_minutes,
            channel=channel,
            response_type=response_type,
        )
    except DecisionDenied:
        return (
            "DENIED: The human approver has denied this action. "
            "You MUST NOT proceed with this action under any circumstances. "
            "Inform the user that the action was denied."
        )
    except DecisionExpired:
        return (
            "EXPIRED: The approval request timed out without a response. "
            "You MUST NOT proceed without explicit approval. "
            "Inform the user that the approval request expired."
        )

    if decision.modified:
        return (
            f"MODIFIED: The approver has requested changes. "
            f"Notes: {decision.response_notes}. "
            f"Data: {decision.response_data}. "
            f"Adjust your approach according to these instructions."
        )

    if decision.response_data:
        return (
            f"APPROVED by {decision.resolved_by}. "
            f"Response data: {json.dumps(decision.response_data)}. "
            f"You may proceed with the action."
        )

    return f"APPROVED by {decision.resolved_by}. You may proceed with: {action}"
