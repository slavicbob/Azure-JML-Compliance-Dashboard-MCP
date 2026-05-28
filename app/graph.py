import os
import re
import time
import csv
import io
from datetime import datetime, timedelta
import requests
from msal import ConfidentialClientApplication
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["https://graph.microsoft.com/.default"]

_msal_app = ConfidentialClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    client_credential=CLIENT_SECRET,
)

_token = None
_token_expiry = 0


def get_token():
    global _token, _token_expiry
    if _token and time.time() < _token_expiry - 60:
        return _token

    result = _msal_app.acquire_token_for_client(scopes=SCOPE)
    if "access_token" not in result:
        raise Exception(f"Token error: {result}")

    _token = result["access_token"]
    _token_expiry = time.time() + result.get("expires_in", 3600)
    return _token


def _request_with_retry(url, headers, max_retries=8):
    """GET with throttle-aware retry.

    On 429, honor Retry-After if present; otherwise back off exponentially
    up to 60s. On 5xx, exponential backoff. Logs each throttle event so the
    operator can see when Graph is pushing back.
    """
    res = None
    for attempt in range(max_retries):
        res = requests.get(url, headers=headers, timeout=60)
        if res.status_code == 429:
            try:
                retry_after = int(res.headers.get("Retry-After", "0") or "0")
            except ValueError:
                retry_after = 0
            wait = retry_after if retry_after > 0 else min(60, 5 * (2 ** attempt))
            print(
                f"[graph]   429 throttled; sleeping {wait}s "
                f"(attempt {attempt + 1}/{max_retries})",
                flush=True,
            )
            time.sleep(wait)
            continue
        if res.status_code >= 500:
            wait = min(30, 2 ** attempt)
            print(f"[graph]   {res.status_code} server error; sleeping {wait}s", flush=True)
            time.sleep(wait)
            continue
        return res
    return res


_MIN_TIME_RE = re.compile(
    r"Minimum allowed time for (\w+) is\s+"
    r"(\d+)/(\d+)/(\d+)\s+(\d+):(\d+):(\d+)\s*(AM|PM)",
    re.IGNORECASE,
)


def _clamp_audit_filter(url, error_text):
    """When Graph returns 400 'Minimum allowed time for activityDateTime is X',
    parse X and rewrite the URL's `<param> ge <timestamp>` clause to that
    minimum. Returns the new URL, or None if the error doesn't match."""
    m = _MIN_TIME_RE.search(error_text)
    if not m:
        return None
    param = m.group(1)
    month, day, year, hour, minute, second = (int(m.group(i)) for i in range(2, 8))
    ampm = m.group(8).upper()
    if ampm == "PM" and hour != 12:
        hour += 12
    if ampm == "AM" and hour == 12:
        hour = 0
    try:
        dt = datetime(year, month, day, hour, minute, second) + timedelta(hours=1)
    except ValueError:
        return None
    iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    pattern = rf"{re.escape(param)}\s+ge\s+[0-9T:Z\-]+"
    new_url, n = re.subn(pattern, f"{param} ge {iso}", url)
    return new_url if n > 0 else None


def graph_get_all(endpoint, beta=False, page_limit=None):
    """Paged GET that follows @odata.nextLink. page_limit caps total pages fetched."""
    token = get_token()
    base = "https://graph.microsoft.com/beta" if beta else "https://graph.microsoft.com/v1.0"
    url = f"{base}{endpoint}"

    short = endpoint.split("?")[0][:80]
    print(f"[graph] GET {short}", flush=True)

    results = []
    pages = 0
    t0 = time.time()
    audit_clamped = False
    while url:
        res = _request_with_retry(url, {"Authorization": f"Bearer {token}"})

        # Self-heal when an /auditLogs filter asks for more retention than
        # the tenant allows — Graph tells us the minimum, we retry with it.
        if (
            res.status_code == 400
            and pages == 0
            and not audit_clamped
            and "Minimum allowed time" in res.text
        ):
            new_url = _clamp_audit_filter(url, res.text)
            if new_url and new_url != url:
                print(f"[graph]   audit retention exceeded; clamping and retrying", flush=True)
                url = new_url
                audit_clamped = True
                continue

        if res.status_code != 200:
            print(f"[graph] ERROR {res.status_code} on {short}: {res.text[:200]}", flush=True)
            raise Exception(f"Graph error ({res.status_code}): {res.text}")
        data = res.json()
        results.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
        pages += 1
        if pages % 5 == 0:
            print(f"[graph]   ...{pages} pages, {len(results)} items, {time.time() - t0:.1f}s", flush=True)
        if page_limit and pages >= page_limit:
            print(f"[graph]   stopped at page_limit={page_limit}", flush=True)
            break
        # Gentle pacing between paginated requests so we stay under Graph's
        # per-second throttle ceiling. ~100ms keeps us at ~10 req/s — the
        # documented soft limit for many Graph endpoints.
        if url:
            time.sleep(0.1)
    print(f"[graph]   done {short}: {len(results)} items in {pages} pages, {time.time() - t0:.1f}s", flush=True)
    return results


def graph_get_one(endpoint, beta=False):
    """Single GET, returns the JSON body or raises."""
    token = get_token()
    base = "https://graph.microsoft.com/beta" if beta else "https://graph.microsoft.com/v1.0"
    res = _request_with_retry(f"{base}{endpoint}", {"Authorization": f"Bearer {token}"})
    if res.status_code != 200:
        raise Exception(f"Graph error ({res.status_code}): {res.text}")
    return res.json()


def get_eligible_assignments():
    """Fetch PIM eligible role-assignment instances (current eligibilities).

    Hits /roleManagement/directory/roleEligibilityScheduleInstances with
    principal + roleDefinition expanded so callers don't have to make a
    second lookup per row. Requires the RoleManagement.Read.Directory
    application permission. On tenants without Entra ID P2, the endpoint
    returns 200 with an empty value list; on failure we return [] and let
    the caller fall through to its existing logic.

    Returns a list of normalized dicts:
      {
        "user": <upn or displayName fallback>,
        "displayName": <principal display name>,
        "principalId": <user/group/SP id>,
        "principalType": "user" | "group" | "servicePrincipal" | None,
        "role": <role displayName>,
        "roleDefinitionId": <id>,
        "directoryScopeId": "/" or "/administrativeUnit/{id}",
        "memberType": "Direct" | "Inherited" | "Group",
        "assignmentType": "Assigned" | "Activated",
        "startDateTime": <iso>,
        "endDateTime": <iso or null for permanent>,
        "scheduleInstanceId": <id>,
      }
    """
    try:
        rows = graph_get_all(
            "/roleManagement/directory/roleEligibilityScheduleInstances"
            "?$expand=principal,roleDefinition"
        )
    except Exception as e:
        print(f"[graph]   eligible-assignments fetch failed: {e}", flush=True)
        return []

    out = []
    for r in rows:
        principal = r.get("principal") or {}
        role_def = r.get("roleDefinition") or {}
        # principal['@odata.type'] looks like '#microsoft.graph.user' — strip prefix.
        odata_type = (principal.get("@odata.type") or "").split(".")[-1].lower() or None
        out.append({
            "user": principal.get("userPrincipalName") or principal.get("displayName") or "—",
            "displayName": principal.get("displayName"),
            "principalId": r.get("principalId"),
            "principalType": odata_type,
            "role": role_def.get("displayName") or "Unknown",
            "roleDefinitionId": r.get("roleDefinitionId"),
            "directoryScopeId": r.get("directoryScopeId"),
            "memberType": r.get("memberType"),
            "assignmentType": r.get("assignmentType"),
            "startDateTime": r.get("startDateTime"),
            "endDateTime": r.get("endDateTime"),
            "scheduleInstanceId": r.get("id"),
        })
    return out


def graph_get_csv_report(endpoint, beta=False):
    """Fetch a Microsoft 365 usage report (CSV) and return list[dict]."""
    token = get_token()
    base = "https://graph.microsoft.com/beta" if beta else "https://graph.microsoft.com/v1.0"
    res = _request_with_retry(f"{base}{endpoint}", {"Authorization": f"Bearer {token}"})
    if res.status_code != 200:
        raise Exception(f"Graph report error ({res.status_code}): {res.text}")
    reader = csv.DictReader(io.StringIO(res.text))
    return list(reader)
