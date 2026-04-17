"""The Handover API client with enforcement."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional, Union

import httpx

from .exceptions import (
    DecisionDenied,
    DecisionExpired,
    DecisionTimeout,
    HandoverError,
)
from .models import (
    ChooseResponse,
    ConfirmResponse,
    Decision,
    DecisionStatus,
    NumberInputResponse,
    ScheduleResponse,
    TextInputResponse,
)

ResponseTypeConfig = Union[
    ChooseResponse, TextInputResponse, NumberInputResponse, ConfirmResponse, ScheduleResponse
]

DEFAULT_BASE_URL = "https://thehandover.xyz"


class HandoverClient:
    """Client for The Handover API.

    Usage::

        from the_handover import HandoverClient

        client = HandoverClient(api_key="ho_live_...")

        # Simple approval gate — blocks until resolved, raises on denial
        decision = client.approve(
            action="Delete 500 user records",
            approver="admin@company.com",
            urgency="critical",
        )
        # If we get here, it was approved
        print(f"Approved by {decision.resolved_by}")

        # Rich response — ask for a choice
        from the_handover import ChooseResponse
        decision = client.approve(
            action="Select deployment target",
            approver="ops@company.com",
            response_type=ChooseResponse(
                choices=["staging", "production", "canary"],
                label="Which environment?",
            ),
        )
        print(f"Chosen: {decision.response_data['chosen']}")
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "the-handover-python/0.1.0",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> HandoverClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ── Core API methods ─────────────────────────────────────────────

    def create(
        self,
        action: str,
        approver: str,
        *,
        context: Optional[str] = None,
        urgency: str = "medium",
        timeout_minutes: int = 60,
        channel: str = "email",
        options: Optional[list[str]] = None,
        callback_url: Optional[str] = None,
        response_type: Optional[ResponseTypeConfig] = None,
    ) -> dict[str, Any]:
        """Create a decision request (non-blocking).

        Returns the raw API response with ``id``, ``status``, ``expires_at``.
        For most use cases, prefer :meth:`approve` which blocks until resolved.
        """
        body: dict[str, Any] = {
            "action": action,
            "approver": approver,
            "urgency": urgency,
            "timeout_minutes": timeout_minutes,
            "channel": channel,
        }
        if context:
            body["context"] = context
        if options:
            body["options"] = options
        if callback_url:
            body["callback_url"] = callback_url
        if response_type:
            body["response_type"] = response_type.to_dict()

        res = self._http.post("/decisions", json=body)
        if res.status_code >= 400:
            data = res.json()
            raise HandoverError(
                f"API error {res.status_code}: {data.get('error', res.text)}"
            )
        return res.json()

    def get(self, decision_id: str) -> Decision:
        """Get the current state of a decision."""
        res = self._http.get(f"/decisions/{decision_id}")
        if res.status_code >= 400:
            data = res.json()
            raise HandoverError(
                f"API error {res.status_code}: {data.get('error', res.text)}"
            )
        return Decision.from_dict(res.json())

    def resolve(
        self,
        decision_id: str,
        action: str,
        *,
        notes: Optional[str] = None,
        response_data: Optional[dict[str, Any]] = None,
        resolved_by: Optional[str] = None,
    ) -> Decision:
        """Programmatically resolve a decision."""
        body: dict[str, Any] = {"action": action}
        if notes:
            body["notes"] = notes
        if response_data:
            body["response_data"] = response_data
        if resolved_by:
            body["resolved_by"] = resolved_by

        res = self._http.post(f"/decisions/{decision_id}/resolve", json=body)
        if res.status_code >= 400:
            data = res.json()
            raise HandoverError(
                f"API error {res.status_code}: {data.get('error', res.text)}"
            )
        return Decision.from_dict(res.json())

    # ── Polling ──────────────────────────────────────────────────────

    def poll(
        self,
        decision_id: str,
        *,
        interval: float = 2.0,
        max_wait: float = 3600.0,
    ) -> Decision:
        """Poll a decision until it's resolved or expired.

        Raises :class:`DecisionTimeout` if ``max_wait`` is exceeded.
        """
        start = time.monotonic()
        while True:
            decision = self.get(decision_id)
            if decision.status != DecisionStatus.PENDING:
                return decision
            elapsed = time.monotonic() - start
            if elapsed >= max_wait:
                raise DecisionTimeout(decision_id)
            time.sleep(min(interval, max_wait - elapsed))

    # ── High-level enforcement ───────────────────────────────────────

    def approve(
        self,
        action: str,
        approver: str,
        *,
        context: Optional[str] = None,
        urgency: str = "medium",
        timeout_minutes: int = 60,
        channel: str = "email",
        options: Optional[list[str]] = None,
        callback_url: Optional[str] = None,
        response_type: Optional[ResponseTypeConfig] = None,
        poll_interval: float = 2.0,
        max_wait: float = 3600.0,
    ) -> Decision:
        """Request approval and block until resolved.

        **This is the primary enforcement mechanism.** It:

        1. Creates a decision request
        2. Polls until the approver responds
        3. Returns the Decision if approved/modified
        4. **Raises DecisionDenied if denied** — the agent cannot proceed
        5. **Raises DecisionExpired if it times out** — the agent cannot proceed

        Usage::

            decision = client.approve(
                action="Send 10,000 marketing emails",
                approver="marketing-lead@company.com",
                urgency="high",
            )
            # If we reach this line, it was approved.
            # A denial raises DecisionDenied — the agent is STOPPED.

        """
        result = self.create(
            action=action,
            approver=approver,
            context=context,
            urgency=urgency,
            timeout_minutes=timeout_minutes,
            channel=channel,
            options=options,
            callback_url=callback_url,
            response_type=response_type,
        )

        # Auto-resolved decisions (e.g. by urgency rules) return immediately
        if result.get("auto_resolved"):
            return self.get(result["id"])

        decision = self.poll(
            result["id"],
            interval=poll_interval,
            max_wait=max_wait,
        )

        if decision.status == DecisionStatus.DENIED:
            raise DecisionDenied(decision)

        if decision.status == DecisionStatus.EXPIRED:
            raise DecisionExpired(decision)

        if decision.status == DecisionStatus.ESCALATED:
            raise DecisionExpired(
                decision, f"Decision escalated after timeout: {action}"
            )

        if decision.status == DecisionStatus.SCHEDULED and decision.execute_at:
            execute_time = datetime.fromisoformat(
                decision.execute_at.replace("Z", "+00:00")
            )
            wait_seconds = (execute_time - datetime.now(timezone.utc)).total_seconds()
            if wait_seconds > 0:
                time.sleep(wait_seconds)

        return decision
