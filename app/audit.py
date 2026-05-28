"""Privileged-role audit trail and current standing privileges.

Audit question: who has admin power, when did they get it, and who granted it?

Sources:
  - /directoryRoles?$expand=members                           — current standing privileges
  - /roleManagement/directory/roleEligibilityScheduleInstances — current PIM eligibilities
  - /auditLogs/directoryAudits (RoleManagement)               — every grant/revoke
"""
from datetime import datetime
from app.graph import graph_get_all, get_eligible_assignments
from app.utils import (
    lookback_days, audit_lookback_days, utcnow_iso, graph_filter_dt,
    initiator_display, target_user_upn
)


# Tier 0 = critical, Tier 1 = service admin, Tier 2 = read-only / scoped
TIER_MAP = {
    "Global Administrator": 0,
    "Privileged Role Administrator": 0,
    "Privileged Authentication Administrator": 0,
    "Partner Tier2 Support": 0,
    "Application Administrator": 1,
    "Cloud Application Administrator": 1,
    "User Administrator": 1,
    "Exchange Administrator": 1,
    "SharePoint Administrator": 1,
    "Teams Administrator": 1,
    "Security Administrator": 1,
    "Conditional Access Administrator": 1,
    "Intune Administrator": 1,
    "Compliance Administrator": 1,
    "Global Reader": 2,
    "Security Reader": 2,
    "Reports Reader": 2,
    "Message Center Reader": 2,
}


def run_privileged_audit():
    days = lookback_days()

    # Current standing privileges
    roles = graph_get_all("/directoryRoles?$expand=members")

    # Two passes:
    #  1) walk every (role, member) pair to keep an assignment-level count
    #     (for the totalStandingPrivileges KPI and role_summary), and
    #     simultaneously build a per-user aggregation bucket.
    #  2) finalize one row per user with their full role list, role-count,
    #     highest (lowest-numbered) tier, and a roleIds evidence list.
    role_summary = {}
    user_buckets = {}              # upn -> aggregation bucket
    standing_assignment_count = 0  # total (user, role) pairs across the tenant

    for role in roles:
        name = role.get("displayName") or "Unknown"
        members = role.get("members") or []
        tier = TIER_MAP.get(name, 2)
        role_summary[name] = {"role": name, "memberCount": len(members), "tier": tier}

        for m in members:
            upn = m.get("userPrincipalName") or m.get("displayName") or "unknown"
            standing_assignment_count += 1
            bucket = user_buckets.setdefault(upn, {
                "user": upn,
                "userId": m.get("id"),
                "displayName": m.get("displayName"),
                "userType": m.get("userType"),
                "_roles": set(),
                "_role_ids": [],
                "_tiers": [],
            })
            if name not in bucket["_roles"]:
                bucket["_roles"].add(name)
                bucket["_role_ids"].append(role.get("id"))
                bucket["_tiers"].append(tier)

    # Finalize per-user standing rows. Sort by highest privilege (lowest
    # tier number) first, then by number of roles held descending.
    standing = []
    for upn, b in user_buckets.items():
        sorted_roles = sorted(b["_roles"])
        highest_tier = min(b["_tiers"]) if b["_tiers"] else 2
        standing.append({
            "user": b["user"],
            # Hidden by UserTable (HIDDEN_COLUMNS includes "userId") but
            # we need it on the record so we can join to eligibilities.
            "userId": b["userId"],
            "displayName": b["displayName"],
            "userType": b["userType"],
            "standingRoles": sorted_roles,
            "standingRoleCount": len(sorted_roles),
            "highestTier": highest_tier,
            "evidence": {
                "source": "/directoryRoles?$expand=members",
                "roleIds": b["_role_ids"],
                "checkedAt": utcnow_iso(),
            },
        })
    standing.sort(key=lambda s: (s["highestTier"], -s["standingRoleCount"], s["user"] or ""))

    role_summary_list = sorted(
        role_summary.values(),
        key=lambda r: (r["tier"], -r["memberCount"]),
    )

    # Eligible PIM assignments — separate from standing because the audit
    # question is different: who *could* elevate vs. who currently holds power.
    # Requires RoleManagement.Read.Directory. Returns [] gracefully on tenants
    # without Entra ID P2 or if the permission is missing.
    eligible_raw = get_eligible_assignments()
    eligible_assignments = []
    eligible_by_role = {}
    eligible_user_set = set()
    for e in eligible_raw:
        role_name = e.get("role") or "Unknown"
        tier = TIER_MAP.get(role_name, 2)
        upn = e.get("user")
        eligible_user_set.add(upn)
        eligible_assignments.append({
            "user": upn,
            "displayName": e.get("displayName"),
            "role": role_name,
            "tier": tier,
            "principalType": e.get("principalType"),
            "memberType": e.get("memberType"),
            "assignmentType": e.get("assignmentType"),
            "scope": e.get("directoryScopeId"),
            "startDateTime": e.get("startDateTime"),
            "endDateTime": e.get("endDateTime") or "Permanent",
            "evidence": {
                "source": "/roleManagement/directory/roleEligibilityScheduleInstances",
                "scheduleInstanceId": e.get("scheduleInstanceId"),
                "roleDefinitionId": e.get("roleDefinitionId"),
                "checkedAt": utcnow_iso(),
            },
        })
        bucket = eligible_by_role.setdefault(role_name, {"role": role_name, "tier": tier, "eligibleCount": 0})
        bucket["eligibleCount"] += 1

    eligible_role_summary = sorted(
        eligible_by_role.values(),
        key=lambda r: (r["tier"], -r["eligibleCount"]),
    )

    tier0_eligible = sum(1 for e in eligible_assignments if e["tier"] == 0)

    # Build a per-user view of eligibility so we can annotate the standing
    # table. We join on the principal's directory object id (not UPN),
    # because:
    #   1. PIM-eligible *groups* have no UPN — their principal is the
    #      group's id, and the eligibility flows to whichever users are
    #      members of that group. We expand transitiveMembers per group
    #      below so those users actually get credit on the standing table.
    #   2. UPN case can drift between endpoints; ids are stable.
    eligible_roles_by_user_id = {}      # userId -> set(role names)
    group_role_map = {}                 # groupId -> set(role names)

    for e in eligible_raw:
        pid = e.get("principalId")
        if not pid:
            continue
        role_name = e.get("role") or "Unknown"
        ptype = (e.get("principalType") or "").lower()
        if ptype == "user":
            eligible_roles_by_user_id.setdefault(pid, set()).add(role_name)
        elif ptype == "group":
            group_role_map.setdefault(pid, set()).add(role_name)
        # servicePrincipal eligibilities are intentionally ignored —
        # they don't show up in the standing-user table anyway.

    # Fan each group eligibility out to its transitive members. This is one
    # extra Graph call per PIM-eligible group; the count is usually small
    # (typical tenants have <20 PIM groups). Failures are non-fatal — we
    # just lose that group's contribution.
    for group_id, role_names in group_role_map.items():
        try:
            members = graph_get_all(f"/groups/{group_id}/transitiveMembers?$select=id")
            for m in members:
                mid = m.get("id")
                if mid:
                    eligible_roles_by_user_id.setdefault(mid, set()).update(role_names)
        except Exception as ex:
            print(f"[audit] group {group_id} member expand failed: {ex}", flush=True)
            continue

    # Enrich each standing row. If a user has no eligibilities, we still
    # set the fields (empty list / 0) so the column appears for every row.
    for s in standing:
        uid = s.get("userId")
        roles_for_user = sorted(eligible_roles_by_user_id.get(uid, set())) if uid else []
        s["eligibleAssignmentCount"] = len(roles_for_user)
        s["eligibleAssignmentRoles"] = roles_for_user

    # Role change history — bounded by tenant audit-log retention
    since = graph_filter_dt(audit_lookback_days())
    try:
        audits = graph_get_all(
            f"/auditLogs/directoryAudits"
            f"?$filter=category eq 'RoleManagement' and activityDateTime ge {since}"
            f"&$orderby=activityDateTime desc"
        )
    except Exception:
        audits = []

    role_changes = []
    grants = 0
    revokes = 0
    self_grants = 0

    for a in audits:
        activity = a.get("activityDisplayName") or ""
        actor = initiator_display(a)
        target_upn = target_user_upn(a)

        # Role name extracted from targetResources of type "Role"
        role_name = None
        for t in a.get("targetResources") or []:
            if t.get("type") == "Role":
                role_name = t.get("displayName")
                break

        is_grant = "Add member to role" in activity or "Assign" in activity
        is_revoke = "Remove member from role" in activity

        if is_grant:
            grants += 1
        if is_revoke:
            revokes += 1
        if target_upn and actor and target_upn.lower() == actor.lower() and is_grant:
            self_grants += 1

        role_changes.append({
            "time": a.get("activityDateTime"),
            "activity": activity,
            "role": role_name or "—",
            "tier": TIER_MAP.get(role_name, 2),
            "targetUser": target_upn or "—",
            "actor": actor,
            "selfGrant": (target_upn and actor and target_upn.lower() == actor.lower() and is_grant),
            "result": a.get("result"),
            "evidence": {
                "source": "/auditLogs/directoryAudits",
                "activityId": a.get("id"),
                "correlationId": a.get("correlationId"),
            },
        })

    # `standing` is already one row per user with standingRoleCount /
    # highestTier baked in — derive the rollups from it instead of from
    # the now-removed per-pair list.
    multi_role_users = [
        {"user": s["user"], "roleCount": s["standingRoleCount"]}
        for s in standing if s["standingRoleCount"] > 1
    ]
    multi_role_users.sort(key=lambda x: x["roleCount"], reverse=True)

    tier0_count = sum(1 for s in standing if s["highestTier"] == 0)

    return {
        "generatedAt": utcnow_iso(),
        "lookbackDays": days,
        "summary": {
            # Total (user, role) assignments across the tenant — preserves
            # the prior KPI meaning even though `standing` is now collapsed.
            "totalStandingPrivileges": standing_assignment_count,
            "uniqueAdmins": len(standing),
            "tier0Admins": tier0_count,
            "multiRoleAdmins": len(multi_role_users),
            "totalEligibleAssignments": len(eligible_assignments),
            "uniqueEligibleAdmins": len(eligible_user_set),
            "tier0Eligible": tier0_eligible,
            "roleChangesInPeriod": len(role_changes),
            "roleGrants": grants,
            "roleRevokes": revokes,
            "selfGrants": self_grants,
        },
        "insights": {
            "standingPrivileges": standing,
            "roleSummary": role_summary_list,
            "eligibleAssignments": eligible_assignments,
            "eligibleRoleSummary": eligible_role_summary,
            "roleChanges": role_changes,
            "multiRoleAdmins": multi_role_users,
        },
        "recommendations": [
            "Limit Tier-0 admins to absolute minimum (target: ≤5)",
            "Investigate any self-granted role assignments",
            "Use PIM for just-in-time admin elevation",
            "Review Tier-0 eligible assignments — even un-activated, they're attack paths",
            "Recertify standing admin assignments quarterly",
        ],
    }
