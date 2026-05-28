"""Shared helpers for date parsing, traceability, and compliance scoring."""
import os
import re
from datetime import datetime, timezone


def lookback_days() -> int:
    try:
        return int(os.getenv("JML_LOOKBACK_DAYS", "90"))
    except (TypeError, ValueError):
        return 90


def audit_lookback_days() -> int:
    """Audit-log retention is capped by the tenant's Entra ID licensing
    (typically 30 days on P1/P2). We default to 27 to stay safely under that
    limit. Override via JML_AUDIT_LOOKBACK_DAYS if your tenant has a longer
    retention enabled.
    """
    try:
        return int(os.getenv("JML_AUDIT_LOOKBACK_DAYS", "27"))
    except (TypeError, ValueError):
        return 27


def parse_iso(s):
    """Parse an ISO 8601 datetime; returns None on failure."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def days_since(s):
    """Days since an ISO timestamp, or None."""
    dt = parse_iso(s)
    if not dt:
        return None
    return (datetime.now(timezone.utc) - dt).days


def utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


def graph_filter_dt(days_back: int) -> str:
    """Format a Graph $filter-compatible UTC timestamp N days back."""
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")


def initiator_display(audit_entry):
    """Pull a human-readable 'who did this' string from a directoryAudits entry."""
    init = audit_entry.get("initiatedBy") or {}
    user = init.get("user") or {}
    app = init.get("app") or {}
    return (
        user.get("userPrincipalName")
        or user.get("displayName")
        or app.get("displayName")
        or "system"
    )


def target_user_id(audit_entry):
    """Extract the targeted user id from an audit log entry, if any."""
    targets = audit_entry.get("targetResources") or []
    for t in targets:
        if t.get("type") == "User" and t.get("id"):
            return t["id"]
    return None


def target_user_upn(audit_entry):
    targets = audit_entry.get("targetResources") or []
    for t in targets:
        if t.get("type") == "User":
            return t.get("userPrincipalName") or t.get("displayName")
    return None


def modified_props(audit_entry):
    """Return {property: (old, new)} dict from modifiedProperties."""
    out = {}
    for p in audit_entry.get("modifiedProperties") or []:
        name = p.get("displayName")
        if not name:
            continue
        old = _strip_quotes(p.get("oldValue"))
        new = _strip_quotes(p.get("newValue"))
        out[name] = (old, new)
    return out


_QUOTE_RE = re.compile(r'^"|"$')


def _strip_quotes(v):
    if v is None:
        return None
    if isinstance(v, str):
        return _QUOTE_RE.sub("", v).strip()
    return v
