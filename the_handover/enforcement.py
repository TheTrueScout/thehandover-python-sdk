"""Decorator-based enforcement for agent actions.

The @require_approval decorator wraps any function so that it cannot
execute without human approval. If the approver denies, the function
NEVER runs — the agent is stopped with a DecisionDenied exception.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Optional

from .client import HandoverClient, ResponseTypeConfig
from .exceptions import DecisionDenied, DecisionExpired


def require_approval(
    client: HandoverClient,
    approver: str,
    *,
    action: Optional[str] = None,
    context: Optional[str] = None,
    urgency: str = "medium",
    timeout_minutes: int = 60,
    channel: str = "email",
    response_type: Optional[ResponseTypeConfig] = None,
) -> Callable:
    """Decorator that gates a function behind human approval.

    The decorated function will NOT execute unless an approver explicitly
    approves it. If denied, ``DecisionDenied`` is raised. If expired,
    ``DecisionExpired`` is raised. The agent cannot bypass this.

    Usage::

        from the_handover import HandoverClient, require_approval

        client = HandoverClient(api_key="ho_live_...")

        @require_approval(
            client,
            approver="admin@company.com",
            urgency="critical",
        )
        def delete_all_users():
            db.execute("DELETE FROM users")

        # Calling delete_all_users() now requires human approval.
        # If denied, DecisionDenied is raised and the function never runs.
        delete_all_users()

    The decorator also injects the Decision object as a keyword argument
    ``_decision`` if the wrapped function accepts it::

        @require_approval(client, approver="ops@company.com")
        def deploy(env: str, _decision=None):
            print(f"Approved by {_decision.resolved_by}")
            do_deploy(env)

    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            action_name = action or f"{func.__module__}.{func.__qualname__}()"

            # Build context from function args if not provided
            ctx = context
            if not ctx and (args or kwargs):
                parts = []
                if args:
                    parts.append(f"args: {args}")
                if kwargs:
                    parts.append(f"kwargs: {kwargs}")
                ctx = ", ".join(parts)

            decision = client.approve(
                action=action_name,
                approver=approver,
                context=ctx,
                urgency=urgency,
                timeout_minutes=timeout_minutes,
                channel=channel,
                response_type=response_type,
            )

            # Inject decision if the function accepts it
            import inspect

            sig = inspect.signature(func)
            if "_decision" in sig.parameters:
                kwargs["_decision"] = decision

            return func(*args, **kwargs)

        return wrapper

    return decorator
