"""Joiners — users created in the lookback window.

Audit question: did every new hire get fully provisioned?
Checks per joiner:
  - Account enabled
  - At least one license assigned
  - Manager set (HR ownership)
  - Department populated
  - Employee ID set (HR-system identity link)
  - MFA registered
"""
import os
from app.graph import graph_get_all
from app.utils import (
    lookback_days, parse_iso, days_since, utcnow_iso, graph_filter_dt
)

# Cap MFA-report pages to keep scans fast on large tenants. 200 pages × 100
# rows = 20 000 users, which covers any tenant up to that size without
# silently truncating the MFA map. Override via MFA_REPORT_PAGE_LIMIT.
MFA_REPORT_PAGE_LIMIT = int(os.getenv("MFA_REPORT_PAGE_LIMIT", "200"))


def _build_mfa_map():
    try:
        rows = graph_get_all(
            "/reports/credentialUserRegistrationDetails",
            beta=True,
            page_limit=MFA_REPORT_PAGE_LIMIT,
        )
        return {r.get("userPrincipalName"): r.get("isMfaRegistered", False) for r in rows}
    except Exception:
        return {}


def run_joiners_analysis():
    days = lookback_days()
    since_iso = graph_filter_dt(days)

    # Pull joiners with their manager expanded.
    # NOTE: Microsoft Graph allows only ONE $expand per request, so we expand
    # only `manager` (used by the provisioning scorecard). Group membership is
    # not part of the JML provisioning checks; if you need group counts later,
    # fetch /users/{id}/memberOf/microsoft.graph.group per user.
    users = graph_get_all(
        f"/users?$select=id,userPrincipalName,displayName,createdDateTime,accountEnabled,"
        f"employeeHireDate,employeeId,department,jobTitle,assignedLicenses,userType,companyName"
        f"&$expand=manager($select=id,userPrincipalName,displayName)"
        f"&$filter=createdDateTime ge {since_iso}",
        beta=True,
    )

    mfa_map = _build_mfa_map()

    joiners = []
    fully_provisioned = 0
    by_department = {}

    for u in users:
        upn = u.get("userPrincipalName")
        created = u.get("createdDateTime")
        manager = u.get("manager")

        checks = {
            "accountEnabled": bool(u.get("accountEnabled")),
            "hasLicense": len(u.get("assignedLicenses") or []) > 0,
            "hasManager": manager is not None,
            "hasDepartment": bool(u.get("department")),
            "hasEmployeeId": bool(u.get("employeeId")),
            "mfaRegistered": mfa_map.get(upn, False),
        }
        passed = sum(1 for v in checks.values() if v)
        total = len(checks)
        complete = passed == total
        if complete:
            fully_provisioned += 1

        missing = [k for k, v in checks.items() if not v]

        record = {
            "user": upn,
            "displayName": u.get("displayName"),
            "createdDate": created,
            "daysOld": days_since(created),
            "department": u.get("department") or "—",
            "jobTitle": u.get("jobTitle") or "—",
            "employeeId": u.get("employeeId") or "—",
            "manager": (manager or {}).get("userPrincipalName") if manager else None,
            "licenseCount": len(u.get("assignedLicenses") or []),
            "mfaRegistered": checks["mfaRegistered"],
            "provisioningScore": round((passed / total) * 100),
            "missingChecks": missing,
            "status": "Complete" if complete else f"Missing: {', '.join(missing)}",
            # Traceability
            "evidence": {
                "source": "/users + /reports/credentialUserRegistrationDetails",
                "checkedAt": utcnow_iso(),
            },
        }
        joiners.append(record)

        dept = u.get("department") or "Unassigned"
        by_department[dept] = by_department.get(dept, 0) + 1

    total_joiners = len(joiners)
    compliance_rate = round((fully_provisioned / total_joiners) * 100, 1) if total_joiners else 100.0
    incomplete = [j for j in joiners if j["provisioningScore"] < 100]

    return {
        "generatedAt": utcnow_iso(),
        "lookbackDays": days,
        "summary": {
            "totalJoiners": total_joiners,
            "fullyProvisioned": fully_provisioned,
            "incompleteProvisioning": len(incomplete),
            "complianceRate": compliance_rate,
        },
        "insights": {
            "joiners": joiners,
            "incomplete": incomplete,
            "byDepartment": by_department,
        },
        "recommendations": [
            "Investigate incomplete provisioning — flag to HR / IT onboarding",
            "Ensure every new hire has a manager set on day 1",
            "Require an employeeId on every account — it's the join key to your HRIS",
            "Block account activation until MFA is registered",
            "Standardize license assignment via dynamic group rules",
        ],
    }
