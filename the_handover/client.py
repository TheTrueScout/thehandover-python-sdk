"""The Handover API client with enforcement."""

from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

import httpx

from . import dev as _dev
from .exceptions import (
    DecisionDenied,
    DecisionExpired,
    DecisionTimeout,
    HandoverError,
)
from .models import (
    ApprovalPolicy,
    Attachment,
    ChooseResponse,
    ConfirmResponse,
    Decision,
    DecisionStatus,
    FileUploadResponse,
    NumberInputResponse,
    ScheduleResponse,
    TextInputResponse,
)

ResponseTypeConfig = Union[
    ChooseResponse,
    TextInputResponse,
    NumberInputResponse,
    ConfirmResponse,
    ScheduleResponse,
    FileUploadResponse,
]

DEFAULT_BASE_URL = "https://thehandover.xyz"


class HandoverClient:
    """Client for The Handover API.

    Usage::

        from the_handover import HandoverClient, ApprovalPolicy, AmountRule, DEFAULT_POLICY

        # Use the built-in default policy
        client = HandoverClient(api_key="ho_live_...", policy=DEFAULT_POLICY)

        # Or define your own
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

        # Triggers approval — "delete" matched
        decision = client.approve(
            action="Delete 500 user records",
            approver="admin@company.com",
            urgency="critical",
        )

        # Triggers approval — amount exceeds $100 threshold
        decision = client.approve(
            action="Process payment for order #1234",
            approver="finance@company.com",
            amount=250.0,
        )

        # Auto-approved by policy — no match
        decision = client.approve(
            action="Fetch user profile",
            approver="admin@company.com",
        )
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        policy: Optional[ApprovalPolicy] = None,
        dev_mode: Optional[bool] = None,
    ):
        """Initialise the client.

        Args:
            dev_mode: When ``True`` every decision auto-approves locally with
                no network call and no prompt — perfect for CI, unit tests, and
                local agent runs. When ``False`` (default behaviour with a real
                key) the client always hits the API. When ``None`` (the
                default), the SDK auto-detects: if no API key and stdin is a
                TTY it falls back to the interactive ``dev`` prompt.
        """
        api_key = api_key or os.environ.get("HANDOVER_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.policy = policy
        self._dev_decisions: dict[str, Decision] = {}
        # Explicit dev_mode=True auto-approves without prompting; combined
        # with no api key it also avoids the "missing key" error so tests work
        # in non-interactive environments (CI, Docker).
        self._dev_auto_approve = dev_mode is True

        if dev_mode is True:
            # Force dev mode regardless of whether a key is set — useful in
            # CI where HANDOVER_API_KEY may be present but you don't want to
            # actually hit the network.
            self.api_key = api_key or ""
            self._dev_mode = True
            self._http = None
            return

        if not api_key:
            if dev_mode is False:
                raise HandoverError(
                    "No HANDOVER_API_KEY set and dev_mode=False. Set "
                    "HANDOVER_API_KEY or pass dev_mode=True to test locally."
                )
            if not sys.stdin.isatty():
                raise HandoverError(
                    "No HANDOVER_API_KEY set and no interactive terminal "
                    "available for dev mode. Set HANDOVER_API_KEY or pass "
                    "dev_mode=True. Get a free key at https://thehandover.xyz/signup"
                )
            self.api_key = ""
            self._dev_mode = True
            self._http = None
            return

        self._dev_mode = False
        self.api_key = api_key
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "the-handover-python/0.4.0",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        if self._http is not None:
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
        context_images: Optional[list[str]] = None,
        enforce: bool = False,
    ) -> Decision:
        """Create a decision request (non-blocking).

        Returns a :class:`Decision` with at minimum ``id``, ``status``,
        ``expires_at``, and the request fields populated. For most use cases,
        prefer :meth:`approve` which blocks until the approver responds.

        Args:
            context_images: Up to 5 HTTP(S) URLs of images the approver should
                see alongside the action (e.g. screenshots, charts).
            enforce: When ``True`` the server returns an ``action_permitted``
                flag on :meth:`get` so callers can gate execution without
                re-reading status fields.

        .. note::
            **Breaking change in 0.4.0** — previously this returned a raw
            ``dict``. If you were doing ``d['id']``, switch to ``d.id``.
        """
        if self._dev_mode:
            return self._dev_create(
                action=action,
                approver=approver,
                context=context,
                urgency=urgency,
                response_type=response_type,
                context_images=context_images,
                enforce=enforce,
            )

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
        if context_images:
            body["context_images"] = context_images
        if enforce:
            body["enforce"] = True

        res = self._http.post("/decisions", json=body)
        if res.status_code >= 400:
            data = res.json()
            raise HandoverError(
                f"API error {res.status_code}: {data.get('error', res.text)}"
            )
        # The create endpoint returns a minimal payload; merge with the request
        # body so the returned Decision is immediately useful (action, urgency,
        # etc. visible without an extra .get() round-trip).
        payload = {**body, **res.json()}
        return Decision.from_dict(payload)

    # ── Attachments ──────────────────────────────────────────────────

    def upload_attachment(
        self,
        decision_id: str,
        file: Union[str, Path, tuple[str, bytes, str]],
    ) -> list[Attachment]:
        """Attach a file to a pending decision for the approver to review.

        Args:
            decision_id: The decision to attach to.  Must still be pending.
            file: Either a filesystem path (``str`` or :class:`~pathlib.Path`)
                or a tuple ``(filename, bytes, content_type)``.

        Returns:
            The full list of attachments now on the decision.

        Raises:
            HandoverError: If the upload fails (blocked file type, size limit,
                attachment limit, etc.).  Accepted types include images, PDFs,
                common office documents, plain text, CSV, Markdown, JSON, XML,
                and RTF.  Max 10MB per file, 5 files per decision.
        """
        if isinstance(file, (str, Path)):
            path = Path(file)
            filename = path.name
            data = path.read_bytes()
            content_type = "application/octet-stream"
        else:
            filename, data, content_type = file

        if self._dev_mode:
            attachment = Attachment(
                name=filename,
                url=f"dev://local/{filename}",
                type=content_type,
                size=len(data),
            )
            decision = self._dev_decisions.get(decision_id)
            if decision is not None:
                existing = list(decision.attachments or [])
                existing.append(attachment)
                decision.attachments = existing
            return [attachment]

        # Use a fresh httpx.post so the client's default JSON Content-Type
        # header doesn't clash with the multipart boundary header.
        res = httpx.post(
            f"{self.base_url}/decisions/{decision_id}/attachments",
            files={"file": (filename, data, content_type)},
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "the-handover-python/0.3.0",
            },
            timeout=self._http.timeout,
        )
        if res.status_code >= 400:
            payload = res.json() if res.content else {}
            raise HandoverError(
                f"API error {res.status_code}: {payload.get('error', res.text)}"
            )
        body = res.json()
        return [Attachment.from_dict(a) for a in body.get("attachments", [])]

    def list_attachments(self, decision_id: str) -> list[Attachment]:
        """List attachments currently on a decision."""
        if self._dev_mode:
            decision = self._dev_decisions.get(decision_id)
            return list(decision.attachments or []) if decision else []
        res = self._http.get(f"/decisions/{decision_id}/attachments")
        if res.status_code >= 400:
            payload = res.json() if res.content else {}
            raise HandoverError(
                f"API error {res.status_code}: {payload.get('error', res.text)}"
            )
        body = res.json()
        return [Attachment.from_dict(a) for a in body.get("attachments", [])]

    def get(self, decision_id: str) -> Decision:
        """Get the current state of a decision."""
        if self._dev_mode:
            decision = self._dev_decisions.get(decision_id)
            if decision is None:
                raise HandoverError(f"Decision {decision_id} not found (dev mode)")
            return decision
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
        if self._dev_mode:
            decision = self._dev_decisions.get(decision_id)
            if decision is None:
                raise HandoverError(f"Decision {decision_id} not found (dev mode)")
            status_map = {
                "approve": DecisionStatus.APPROVED,
                "deny": DecisionStatus.DENIED,
                "modify": DecisionStatus.MODIFIED,
            }
            decision.status = status_map.get(action, DecisionStatus.MODIFIED)
            decision.response_notes = notes
            decision.response_data = response_data
            decision.resolved_by = resolved_by or "dev@local"
            decision.resolved_at = _dev.now_iso()
            return decision

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

    # ── Dev mode helpers ─────────────────────────────────────────────

    def _dev_create(
        self,
        action: str,
        approver: str,
        context: Optional[str],
        urgency: str,
        response_type: Optional[ResponseTypeConfig],
        context_images: Optional[list[str]],
        enforce: bool,
    ) -> Decision:
        """Resolve a decision locally — either by auto-approving (when the
        client was created with ``dev_mode=True``) or by prompting the
        developer on stdin (legacy behaviour).
        """
        if self._dev_auto_approve:
            # Silent auto-approve; no prompt, no network call. For CI/tests.
            status: str = "approved"
            notes: Optional[str] = "auto-approved (dev_mode=True)"
            response_data: Optional[dict[str, Any]] = None
            execute_at: Optional[str] = None
        else:
            status, notes, response_data, execute_at = _dev.prompt_decision(
                action=action,
                approver=approver,
                urgency=urgency,
                context=context,
                response_type=response_type,
            )
        now = _dev.now_iso()
        decision_id = f"dev_{uuid.uuid4().hex[:12]}"
        decision = Decision(
            id=decision_id,
            status=DecisionStatus(status),
            action=action,
            context=context,
            urgency=urgency,
            response_notes=notes,
            response_data=response_data,
            resolved_at=now,
            resolved_by="dev@local",
            created_at=now,
            execute_at=execute_at,
            context_images=context_images,
            enforce=enforce,
            action_permitted=(status in ("approved", "modified", "scheduled"))
            if enforce
            else None,
        )
        self._dev_decisions[decision_id] = decision
        return decision

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
        context_images: Optional[list[str]] = None,
        enforce: bool = False,
        poll_interval: float = 2.0,
        max_wait: float = 3600.0,
        amount: Optional[float] = None,
    ) -> Decision:
        """Request approval and block until resolved.

        **This is the primary enforcement mechanism.** It:

        1. Checks the client's :class:`~the_handover.ApprovalPolicy` (if set).
           Actions that don't match any rule are auto-approved immediately.
        2. Creates a decision request for actions that do match.
        3. Polls until the approver responds.
        4. Returns the Decision if approved/modified.
        5. **Raises DecisionDenied if denied** — the agent cannot proceed.
        6. **Raises DecisionExpired if it times out** — the agent cannot proceed.

        Args:
            action: What the agent wants to do.
            approver: Email of the human decision-maker.
            context: Additional background for the approver.
            urgency: ``"low"``, ``"medium"``, ``"high"``, or ``"critical"``.
            amount: Numeric amount associated with this action (e.g. a dollar
                value for a financial transaction).  Evaluated against any
                :class:`~the_handover.AmountRule` in the active policy.
            timeout_minutes: How long before the request expires.
            channel: Notification channel — ``"email"``, ``"webhook"``, ``"slack"``.
            poll_interval: Seconds between status checks.
            max_wait: Maximum seconds to wait before raising
                :class:`~the_handover.DecisionTimeout`.

        Usage::

            # Always needs approval — no policy needed.
            decision = client.approve(
                action="Send 10,000 marketing emails",
                approver="marketing-lead@company.com",
                urgency="high",
            )

            # With a policy — auto-approved if action doesn't match any rule.
            decision = client.approve(
                action="Process payment",
                approver="finance@company.com",
                amount=250.0,   # compared against AmountRule thresholds
            )
        """
        if self.policy is not None and not self.policy.should_require(action, urgency, amount):
            return Decision(
                id="auto",
                status=DecisionStatus.APPROVED,
                action=action,
                context=context,
                urgency=urgency,
                response_notes="Auto-approved — action did not match any policy rule.",
            )

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
            context_images=context_images,
            enforce=enforce,
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
            execute_at = datetime.fromisoformat(
                decision.execute_at.replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)
            wait_seconds = (execute_at - now).total_seconds()
            if wait_seconds > 0:
                time.sleep(wait_seconds)

        return decision
