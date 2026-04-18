"""Dev mode: prompt the developer directly on stdin when no API key is set.

Lets devs try the SDK without signing up.  The decision shows in the terminal
with approve/deny/modify prompts and a nudge to sign up for real notifications.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .models import (
    ChooseResponse,
    ConfirmResponse,
    FileUploadResponse,
    NumberInputResponse,
    ScheduleResponse,
    TextInputResponse,
)

BAR = "=" * 62
SIGNUP_NUDGE = (
    "  Sign up at https://thehandover.xyz for real approvers:\n"
    "  email, Slack, and mobile push notifications."
)


def prompt_decision(
    action: str,
    approver: str,
    urgency: str,
    context: Optional[str],
    response_type: Optional[Any],
) -> tuple[str, Optional[str], Optional[dict[str, Any]], Optional[str]]:
    """Show the decision in the terminal and read the dev's response.

    Returns ``(status, notes, response_data, execute_at)``.
    """
    print(f"\n{BAR}")
    print("  The Handover  [dev mode — no API key set]")
    print(BAR)
    print(f"  Action:    {action}")
    print(f"  Approver:  {approver}")
    print(f"  Urgency:   {urgency}")
    if context:
        print(f"  Context:   {context}")
    print()

    while True:
        choice = input("  [a]pprove  [d]eny  [m]odify > ").strip().lower()
        if choice in ("a", "approve"):
            status, notes, response_data, execute_at = "approved", None, None, None
            break
        if choice in ("d", "deny"):
            reason = input("  Reason (optional): ").strip()
            status, notes, response_data, execute_at = (
                "denied",
                reason or None,
                None,
                None,
            )
            break
        if choice in ("m", "modify"):
            result = _prompt_modify(response_type)
            if result is None:
                continue
            status, notes, response_data, execute_at = result
            break
        print("  Please answer a, d, or m.")

    print(f"\n  -> resolved: {status}")
    print(SIGNUP_NUDGE)
    print(f"{BAR}\n")

    return status, notes, response_data, execute_at


def _prompt_modify(
    response_type: Optional[Any],
) -> Optional[tuple[str, Optional[str], Optional[dict[str, Any]], Optional[str]]]:
    if response_type is None or isinstance(response_type, ConfirmResponse):
        notes = input("  Modified action / notes: ").strip()
        return "modified", notes or None, None, None

    if isinstance(response_type, TextInputResponse):
        data: dict[str, Any] = {}
        for field in response_type.fields:
            name = field.get("name", "")
            label = field.get("label") or name
            data[name] = input(f"  {label}: ").strip()
        return "modified", None, data, None

    if isinstance(response_type, NumberInputResponse):
        raw = input(f"  {response_type.label or 'Value'}: ").strip()
        try:
            value: Any = float(raw) if "." in raw else int(raw)
        except ValueError:
            print("  Not a valid number.")
            return None
        return "modified", None, {"value": value}, None

    if isinstance(response_type, ChooseResponse):
        for idx, choice in enumerate(response_type.choices, 1):
            print(f"    {idx}. {choice}")
        raw = input("  Pick number: ").strip()
        try:
            chosen = response_type.choices[int(raw) - 1]
        except (ValueError, IndexError):
            print("  Not a valid choice.")
            return None
        return "modified", None, {"chosen": chosen}, None

    if isinstance(response_type, ScheduleResponse):
        when = input("  Execute at (ISO 8601, or blank for now): ").strip()
        if not when or when.lower() == "now":
            return "approved", None, None, None
        try:
            datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            print("  Not a valid ISO 8601 timestamp.")
            return None
        return "scheduled", None, None, when

    if isinstance(response_type, FileUploadResponse):
        print("  File upload not supported in dev mode — treating as approved.")
        return "approved", None, None, None

    notes = input("  Notes: ").strip()
    return "modified", notes or None, None, None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
