"""Executive overview — composite compliance score + Top Actions across JML."""
from app.utils import utcnow_iso


def build_overview(joiners, movers, leavers, audit, guests):
    j = joiners.get("summary", {})
    m = movers.get("summary", {})
    l = leavers.get("summary", {})
    a = audit.get("summary", {})
    g = guests.get("summary", {})

    # Composite compliance score (weights):
    #   Joiner provisioning  35%
    #   Leaver deprovisioning 40%   (highest weight — leavers = audit failure mode)
    #   Guest hygiene        15%
    #   Privileged hygiene   10%
    joiner_compliance = j.get("complianceRate", 100.0)
    leaver_compliance = l.get("complianceRate", 100.0)
    guest_compliance = 100.0 if g.get("totalGuests", 0) == 0 else round(
        100 * (g.get("totalGuests", 0) - g.get("staleGuests", 0)) / max(g.get("totalGuests", 1), 1),
        1,
    )
    # Privileged hygiene: penalize Tier-0 sprawl & self-grants
    tier0 = a.get("tier0Admins", 0)
    self_grants = a.get("selfGrants", 0)
    priv_compliance = max(0.0, 100.0 - (max(0, tier0 - 5) * 5) - (self_grants * 10))

    score = round(
        joiner_compliance * 0.35
        + leaver_compliance * 0.40
        + guest_compliance * 0.15
        + priv_compliance * 0.10,
        1,
    )

    # Top Actions — ranked by audit severity
    actions = []
    if l.get("incompleteDeprovisioning", 0):
        actions.append({
            "title": f"Complete deprovisioning for {l['incompleteDeprovisioning']} leavers",
            "impact": "Active audit failure — disabled accounts still holding access",
            "category": "leavers",
        })
    if leavers.get("insights", {}).get("stillPrivileged"):
        n = len(leavers["insights"]["stillPrivileged"])
        actions.append({
            "title": f"Remove privileged roles from {n} disabled accounts",
            "impact": "Critical: ex-employees retain admin power",
            "category": "leavers",
        })
    if j.get("incompleteProvisioning", 0):
        actions.append({
            "title": f"Finish onboarding for {j['incompleteProvisioning']} joiners",
            "impact": "Day-1 access gaps; HR/IT process break",
            "category": "joiners",
        })
    if m.get("totalMovers", 0):
        actions.append({
            "title": f"Schedule access reviews for {m['totalMovers']} movers",
            "impact": "Stale access from previous role",
            "category": "movers",
        })
    if a.get("selfGrants", 0):
        actions.append({
            "title": f"Investigate {a['selfGrants']} self-granted role assignments",
            "impact": "Possible privilege-escalation indicator",
            "category": "privileged",
        })
    if g.get("staleGuests", 0):
        actions.append({
            "title": f"Remove {g['staleGuests']} stale guest accounts",
            "impact": "External attack surface — unused B2B accounts",
            "category": "guests",
        })
    if a.get("tier0Admins", 0) > 5:
        actions.append({
            "title": f"Reduce Tier-0 admin sprawl ({a['tier0Admins']} accounts)",
            "impact": "Excessive standing global-admin exposure",
            "category": "privileged",
        })

    return {
        "generatedAt": utcnow_iso(),
        "lookbackDays": joiners.get("lookbackDays"),
        "scores": {
            "composite": score,
            "joinerCompliance": joiner_compliance,
            "leaverCompliance": leaver_compliance,
            "guestHygiene": guest_compliance,
            "privilegedHygiene": priv_compliance,
        },
        "kpis": {
            "totalJoiners": j.get("totalJoiners", 0),
            "incompleteProvisioning": j.get("incompleteProvisioning", 0),
            "totalMovers": m.get("totalMovers", 0),
            "totalLeavers": l.get("totalDisabledUsers", 0),
            "recentLeavers": l.get("recentLeavers", 0),
            "incompleteDeprovisioning": l.get("incompleteDeprovisioning", 0),
            "totalGuests": g.get("totalGuests", 0),
            "staleGuests": g.get("staleGuests", 0),
            "tier0Admins": a.get("tier0Admins", 0),
            "selfGrants": a.get("selfGrants", 0),
            "roleChangesInPeriod": a.get("roleChangesInPeriod", 0),
        },
        "topActions": actions[:6],
    }
