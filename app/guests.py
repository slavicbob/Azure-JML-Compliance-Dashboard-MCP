"""External / guest user audit.

Audit question: who are our guests, who invited them, are they still active,
and do we have stale guests sitting around?
"""
from app.graph import graph_get_all
from app.utils import (
    lookback_days, utcnow_iso, parse_iso, days_since
)


STALE_THRESHOLD_DAYS = 180


def run_guests_audit():
    users = graph_get_all(
        "/users?$select=id,userPrincipalName,displayName,createdDateTime,"
        "signInActivity,externalUserState,externalUserStateChangeDateTime,"
        "companyName,mail,accountEnabled"
        "&$filter=userType eq 'Guest'",
        beta=True,
    )

    guests = []
    stale = 0
    pending_acceptance = 0
    never_signed_in = 0

    for u in users:
        upn = u.get("userPrincipalName")
        last_signin = (u.get("signInActivity") or {}).get("lastSignInDateTime")
        created = u.get("createdDateTime")
        external_state = u.get("externalUserState")
        accepted_at = u.get("externalUserStateChangeDateTime") if external_state == "Accepted" else None

        days_since_signin = days_since(last_signin) if last_signin else None
        is_stale = (days_since_signin is None and (days_since(created) or 0) > STALE_THRESHOLD_DAYS) \
            or (days_since_signin is not None and days_since_signin > STALE_THRESHOLD_DAYS)

        if is_stale:
            stale += 1
        if external_state == "PendingAcceptance":
            pending_acceptance += 1
        if not last_signin:
            never_signed_in += 1

        guests.append({
            "user": upn,
            "displayName": u.get("displayName"),
            "company": u.get("companyName") or "—",
            "mail": u.get("mail") or "—",
            "invitedAt": created,
            "externalState": external_state or "—",
            "acceptedAt": accepted_at,
            "lastSignIn": last_signin or "Never",
            "daysSinceSignIn": days_since_signin,
            "accountEnabled": u.get("accountEnabled"),
            "stale": is_stale,
            "status": "Stale" if is_stale else (external_state or "Active"),
            "evidence": {
                "source": "/users (userType eq Guest)",
                "checkedAt": utcnow_iso(),
            },
        })

    guests.sort(key=lambda g: (not g["stale"], g.get("daysSinceSignIn") or 0), reverse=True)

    total_guests = len(guests)
    active = total_guests - stale - pending_acceptance

    return {
        "generatedAt": utcnow_iso(),
        "thresholdDays": STALE_THRESHOLD_DAYS,
        "summary": {
            "totalGuests": total_guests,
            "staleGuests": stale,
            "pendingAcceptance": pending_acceptance,
            "neverSignedIn": never_signed_in,
            "activeGuests": active,
        },
        "insights": {
            "guests": guests,
            "stale": [g for g in guests if g["stale"]],
            "pending": [g for g in guests if g["externalState"] == "PendingAcceptance"],
        },
        "recommendations": [
            f"Remove or disable guests inactive for >{STALE_THRESHOLD_DAYS} days",
            "Set automatic expiration on B2B invitations",
            "Require sponsor / inviter on every guest creation",
            "Recertify guest access quarterly with the inviting team",
        ],
    }
