"""Leavers — disabled accounts and their deprovisioning status.

Audit question: when someone left, was their access fully revoked?
Checks per leaver:
  - Account disabled
  - Licenses removed
  - Group memberships cleared (AAD security, M365/Teams, Distribution Lists,
    mail-enabled security groups)
  - Not a member of any privileged role
  - No sign-in activity post-disable (sanity check)

Group membership is pulled via /users/{id}/transitiveMemberOf rather than
$expand=memberOf so that nested memberships and Distribution Lists are not
truncated by Graph's expand limit.

Active role data (including currently-PIM-active roles) comes from
/directoryRoles?$expand=members. Eligible-but-not-active PIM assignments
would require RoleManagement.Read.Directory, which is intentionally not in
this app's permission set.

Cross-references /auditLogs/directoryAudits for the disable event itself.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from app.graph import graph_get_all
from app.utils import (
    lookback_days, audit_lookback_days, utcnow_iso, graph_filter_dt,
    parse_iso, days_since, initiator_display, target_user_id
)


# How many transitiveMemberOf calls to run in parallel. Microsoft Graph's
# per-app throttling sits around 10 req/s for many endpoints, so 10 is a
# safe default; tune via env if needed.
LEAVERS_CONCURRENCY = int(os.getenv("LEAVERS_CONCURRENCY", "10"))


def _build_disable_events_map():
    """Map user_id -> {disabledAt, disabledBy, activityId} from directoryAudits."""
    since = graph_filter_dt(audit_lookback_days())
    try:
        audits = graph_get_all(
            f"/auditLogs/directoryAudits"
            f"?$filter=category eq 'UserManagement' and activityDisplayName eq 'Disable account' "
            f"and activityDateTime ge {since}"
        )
    except Exception:
        audits = []

    out = {}
    for a in audits:
        uid = target_user_id(a)
        if not uid:
            continue
        ts = a.get("activityDateTime")
        if uid in out and (out[uid].get("disabledAt") or "") > (ts or ""):
            continue
        out[uid] = {
            "disabledAt": ts,
            "disabledBy": initiator_display(a),
            "activityId": a.get("id"),
            "correlationId": a.get("correlationId"),
        }
    return out


def _get_user_groups_detail(user_id):
    """Categorized transitive group memberships for one user. Returns:
      {
        'aadSecurity':       [{id, displayName}],
        'm365':              [{id, displayName, mail}],   # M365 Groups + Teams
        'distributionList':  [{id, displayName, mail}],   # classic Exchange DLs
        'mailSecurity':      [{id, displayName, mail}],   # mail-enabled SGs
      }
    Uses transitiveMemberOf so users in nested groups are caught.
    """
    empty = {"aadSecurity": [], "m365": [], "distributionList": [], "mailSecurity": []}
    try:
        items = graph_get_all(
            f"/users/{user_id}/transitiveMemberOf/microsoft.graph.group"
            f"?$select=id,displayName,mail,groupTypes,securityEnabled,mailEnabled",
            page_limit=20,
        )
    except Exception:
        return empty

    out = {"aadSecurity": [], "m365": [], "distributionList": [], "mailSecurity": []}
    for g in items:
        is_m365 = "Unified" in (g.get("groupTypes") or [])
        mail_enabled = bool(g.get("mailEnabled"))
        sec_enabled = bool(g.get("securityEnabled"))
        entry = {
            "id": g.get("id"),
            "displayName": g.get("displayName") or g.get("id"),
            "mail": g.get("mail"),
        }
        if is_m365:
            out["m365"].append(entry)
        elif mail_enabled and not sec_enabled:
            out["distributionList"].append(entry)
        elif mail_enabled and sec_enabled:
            out["mailSecurity"].append(entry)
        else:
            out["aadSecurity"].append(entry)
    return out


def run_leavers_analysis():
    days = lookback_days()

    users = graph_get_all(
        "/users?$select=id,userPrincipalName,displayName,accountEnabled,department,"
        "jobTitle,assignedLicenses,signInActivity,userType"
        "&$filter=accountEnabled eq false",
        beta=True,
    )

    disable_events = _build_disable_events_map()

    # user_id -> [active role names]. Covers permanent assignments AND
    # currently-PIM-active assignments — both appear as members of
    # /directoryRoles when active. Eligible-but-not-active PIM assignments
    # are not surfaced here (would require RoleManagement.Read.Directory).
    role_assignments = {}
    try:
        roles = graph_get_all("/directoryRoles?$expand=members")
        for role in roles:
            name = role.get("displayName")
            for m in role.get("members", []):
                uid = m.get("id")
                if uid and name:
                    role_assignments.setdefault(uid, []).append(name)
    except Exception:
        pass
    privileged_ids = set(role_assignments.keys())

    leavers = []
    fully_deprovisioned = 0
    recent_leavers_count = 0

    # DL-centric aggregate: dl_id -> {distributionList, mail, disabledMembers, ...}
    dls_aggregate = {}

    # Pre-fetch transitiveMemberOf for every disabled user in parallel —
    # this is the only N+1 pattern in the entire codebase, and at large
    # tenants (thousands of disabled users) it dominates wall-clock time
    # if run sequentially. Functionality is identical to the serial loop;
    # we just bound the concurrency to avoid Graph throttling.
    group_details_by_uid = {}
    user_ids = [u.get("id") for u in users if u.get("id")]
    if user_ids:
        def _fetch(uid):
            return uid, _get_user_groups_detail(uid)
        with ThreadPoolExecutor(max_workers=LEAVERS_CONCURRENCY) as executor:
            for uid, detail in executor.map(_fetch, user_ids):
                group_details_by_uid[uid] = detail

    for u in users:
        upn = u.get("userPrincipalName")
        uid = u.get("id")
        license_count = len(u.get("assignedLicenses") or [])
        last_signin = (u.get("signInActivity") or {}).get("lastSignInDateTime")
        disable_evt = disable_events.get(uid, {})
        disabled_at = disable_evt.get("disabledAt")
        disabled_days_ago = days_since(disabled_at) if disabled_at else None

        # Detailed group memberships via transitiveMemberOf (pre-fetched in parallel)
        group_detail = group_details_by_uid.get(
            uid, {"aadSecurity": [], "m365": [], "distributionList": [], "mailSecurity": []}
        )
        aad_count = len(group_detail["aadSecurity"])
        m365_count = len(group_detail["m365"])
        dl_count = len(group_detail["distributionList"])
        ms_count = len(group_detail["mailSecurity"])
        total_groups = aad_count + m365_count + dl_count + ms_count

        active_roles = role_assignments.get(uid, [])

        checks = {
            "accountDisabled": u.get("accountEnabled") is False,
            "licensesRemoved": license_count == 0,
            "groupsCleared": total_groups == 0,
            "notPrivileged": uid not in privileged_ids,
            "noPostDisableSignIn": _no_signin_after(last_signin, disabled_at),
        }
        passed = sum(1 for v in checks.values() if v)
        total = len(checks)
        complete = passed == total
        if complete:
            fully_deprovisioned += 1

        is_recent = disabled_days_ago is not None and disabled_days_ago <= days
        if is_recent:
            recent_leavers_count += 1

        missing = [k for k, v in checks.items() if not v]

        # Pivot DL membership into the DL-centric aggregate
        for dl in group_detail["distributionList"]:
            dl_id = dl["id"]
            agg = dls_aggregate.setdefault(dl_id, {
                "distributionList": dl["displayName"],
                "mail": dl.get("mail") or "—",
                "disabledMembers": [],
                "disabledMemberCount": 0,
            })
            agg["disabledMembers"].append(upn)
            agg["disabledMemberCount"] += 1

        leavers.append({
            "user": upn,
            "displayName": u.get("displayName"),
            "department": u.get("department") or "—",
            "jobTitle": u.get("jobTitle") or "—",
            "disabledAt": disabled_at,
            "disabledDaysAgo": disabled_days_ago,
            "disabledBy": disable_evt.get("disabledBy"),
            "licenseCount": license_count,
            "groupCount": total_groups,
            "aadSecurityGroupCount": aad_count,
            "m365GroupCount": m365_count,
            "distributionListCount": dl_count,
            "mailSecurityGroupCount": ms_count,
            "distributionLists": [g["displayName"] for g in group_detail["distributionList"]],
            "stillPrivileged": uid in privileged_ids,
            "activeRoles": active_roles,
            "lastSignIn": last_signin,
            "deprovisioningScore": round((passed / total) * 100),
            "missingChecks": missing,
            "status": "Fully deprovisioned" if complete else f"Missing: {', '.join(missing)}",
            "recentLeaver": is_recent,
            "evidence": {
                "source": "/users + /auditLogs/directoryAudits + /users/{id}/transitiveMemberOf + /directoryRoles",
                "disableActivityId": disable_evt.get("activityId"),
                "correlationId": disable_evt.get("correlationId"),
                "checkedAt": utcnow_iso(),
            },
        })

    leavers.sort(key=lambda x: (x["deprovisioningScore"], -(days_since(x["disabledAt"]) or 99999)))

    total_leavers = len(leavers)
    incomplete = [l for l in leavers if l["deprovisioningScore"] < 100]
    compliance_rate = round((fully_deprovisioned / total_leavers) * 100, 1) if total_leavers else 100.0

    # Finalize DL-centric view (join member list to a string for table display)
    dls_with_disabled = sorted(
        dls_aggregate.values(),
        key=lambda d: d["disabledMemberCount"],
        reverse=True,
    )
    for d in dls_with_disabled:
        d["disabledMembers"] = ", ".join(d["disabledMembers"])

    return {
        "generatedAt": utcnow_iso(),
        "lookbackDays": days,
        "summary": {
            "totalDisabledUsers": total_leavers,
            "recentLeavers": recent_leavers_count,
            "fullyDeprovisioned": fully_deprovisioned,
            "incompleteDeprovisioning": len(incomplete),
            "complianceRate": compliance_rate,
            "dlsWithDisabledMembers": len(dls_with_disabled),
        },
        "insights": {
            "leavers": leavers,
            "incomplete": incomplete,
            "stillPrivileged": [l for l in leavers if l["stillPrivileged"]],
            "stillLicensed": [l for l in leavers if l["licenseCount"] > 0],
            "stillInDLs": [l for l in leavers if l["distributionListCount"] > 0],
            "distributionListsWithDisabledMembers": dls_with_disabled,
        },
        "recommendations": [
            "Reclaim licenses from every disabled account",
            "Remove all group memberships at offboarding (AAD security, M365, DLs, Teams)",
            "Ensure leavers are removed from privileged roles immediately",
            "Audit Distribution Lists quarterly — disabled members continue to receive mail",
            "Force session sign-out (revokeSignInSessions) at offboarding",
        ],
    }


def _no_signin_after(last_signin, disabled_at):
    if not disabled_at:
        return True
    ls = parse_iso(last_signin)
    da = parse_iso(disabled_at)
    if not ls or not da:
        return True
    return ls <= da
