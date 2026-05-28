"""Movers — users whose role/manager/department changed in the lookback window.

Audit question: when someone changed role, did their access get reviewed and updated?

Source: /auditLogs/directoryAudits — "Update user" events that touch manager,
department, or jobTitle. We DO NOT re-fetch each user — the audit log itself
already captures the property transitions, and a per-user enrichment is an
N+1 anti-pattern on tenants with many movers.
"""
import os
from app.graph import graph_get_all
from app.utils import (
    audit_lookback_days, utcnow_iso, graph_filter_dt,
    initiator_display, target_user_id, target_user_upn, modified_props
)


TRACKED_PROPS = {"manager", "Department", "JobTitle", "CompanyName"}

# Hard cap on how many audit pages to pull, so a chatty tenant can't make us
# scan forever. Each page is 100 events. 50 pages = 5000 events.
AUDIT_PAGE_LIMIT = int(os.getenv("MOVERS_AUDIT_PAGE_LIMIT", "50"))


def run_movers_analysis():
    days = audit_lookback_days()
    since = graph_filter_dt(days)

    # Pull "Update user" events in window. Capped for safety on chatty tenants.
    audits = graph_get_all(
        f"/auditLogs/directoryAudits"
        f"?$filter=category eq 'UserManagement' and activityDisplayName eq 'Update user' "
        f"and activityDateTime ge {since}"
        f"&$orderby=activityDateTime desc",
        page_limit=AUDIT_PAGE_LIMIT,
    )

    # Aggregate by user
    by_user = {}
    for a in audits:
        uid = target_user_id(a)
        if not uid:
            continue
        props = modified_props(a)
        # Only count if a tracked property changed
        relevant = {k: v for k, v in props.items() if k in TRACKED_PROPS}
        if not relevant:
            continue

        upn = target_user_upn(a)
        entry = by_user.setdefault(uid, {
            "user": upn,
            "userId": uid,
            "changes": [],
            "firstChange": a.get("activityDateTime"),
            "lastChange": a.get("activityDateTime"),
        })
        entry["lastChange"] = max(entry["lastChange"], a.get("activityDateTime") or "")
        entry["firstChange"] = min(entry["firstChange"], a.get("activityDateTime") or "9999")
        for prop, (old, new) in relevant.items():
            entry["changes"].append({
                "property": prop,
                "oldValue": old,
                "newValue": new,
                "changedAt": a.get("activityDateTime"),
                "changedBy": initiator_display(a),
                "activityId": a.get("id"),
                "correlationId": a.get("correlationId"),
            })

    # Build mover records directly from audit data — no per-user re-fetch.
    movers = []
    for uid, entry in by_user.items():
        dept_changes = [c for c in entry["changes"] if c["property"] == "Department"]
        mgr_changes = [c for c in entry["changes"] if c["property"] == "manager"]
        title_changes = [c for c in entry["changes"] if c["property"] == "JobTitle"]

        movers.append({
            "user": entry["user"],
            "departmentTransition": _format_transition(dept_changes) if dept_changes else None,
            "titleTransition": _format_transition(title_changes) if title_changes else None,
            "managerTransition": "manager changed" if mgr_changes else None,
            "changeCount": len(entry["changes"]),
            "firstChange": entry["firstChange"],
            "lastChange": entry["lastChange"],
            "changedBy": entry["changes"][-1].get("changedBy") if entry["changes"] else None,
            "needsAccessReview": True,
            # Traceability
            "evidence": {
                "source": "/auditLogs/directoryAudits",
                "auditChanges": entry["changes"],
                "checkedAt": utcnow_iso(),
            },
        })

    # Sort by recency
    movers.sort(key=lambda m: m["lastChange"] or "", reverse=True)

    # Top dept transitions for the executive view
    transitions = {}
    for m in movers:
        if m.get("departmentTransition"):
            transitions[m["departmentTransition"]] = transitions.get(m["departmentTransition"], 0) + 1
    top_transitions = sorted(
        ({"transition": k, "count": v} for k, v in transitions.items()),
        key=lambda x: x["count"], reverse=True
    )[:10]

    return {
        "generatedAt": utcnow_iso(),
        "lookbackDays": days,
        "summary": {
            "totalMovers": len(movers),
            "needsAccessReview": len(movers),
            "topTransitionCount": len(top_transitions),
        },
        "insights": {
            "movers": movers,
            "topTransitions": top_transitions,
        },
        "recommendations": [
            "Schedule access reviews for every mover within 14 days of role change",
            "Remove group memberships tied to previous role",
            "Recertify license entitlements after role change",
            "Update Conditional Access scope (if role-based)",
        ],
    }


def _format_transition(changes):
    """Build 'OldDept → NewDept' from the first and last department change."""
    sorted_changes = sorted(changes, key=lambda c: c.get("changedAt") or "")
    first_old = sorted_changes[0].get("oldValue") or "—"
    last_new = sorted_changes[-1].get("newValue") or "—"
    return f"{first_old} → {last_new}"
