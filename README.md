# JML Compliance Dashboard (MCP)

A production-style Identity Governance and Administration (IGA) dashboard focused on **Joiners, Movers, and Leavers (JML)** controls, built with **FastAPI + Microsoft Graph + React**.

This project scans Microsoft Entra ID signals, computes compliance posture, surfaces audit evidence, and enables natural-language investigation through an Azure OpenAI-powered agent.

## Why This Project Matters

Most identity incidents happen in the lifecycle gaps:
- New hires with incomplete onboarding controls.
- Role changers retaining stale access.
- Leavers who still have licenses, group memberships, or privileged roles.
- Guest identities that drift unmanaged.

This dashboard operationalizes those risks into a single, actionable command center.

## Core Functionalities

### 1) Joiners Compliance
Tracks newly created accounts and scores provisioning completeness across checks such as:
- Account enabled
- License assigned
- Manager assigned
- Department and employee ID populated
- MFA registration present

### 2) Movers Risk Detection
Identifies users with role/manager/department/title changes from audit logs and flags them for access recertification.

### 3) Leavers Deprovisioning Assurance
Analyzes disabled users and verifies revocation hygiene:
- Licenses removed
- Group memberships removed (AAD, M365/Teams, Distribution Lists, mail-enabled security)
- Privileged role removal
- No post-disable sign-in activity

Includes a pivoted report for **distribution lists containing disabled users**.

### 4) Privileged Access Governance
Combines standing privileged assignments with role change history and PIM eligibilities:
- Current standing admin footprint
- Tier-based role exposure
- Self-grant detection
- Grant/revoke audit trail
- Eligible (PIM) assignment analysis

### 5) Guest Lifecycle Hygiene
Audits B2B/guest accounts for stale or pending invitation risk and inactivity.

### 6) Executive Overview
Computes weighted, executive-ready posture metrics:
- Composite compliance score
- Domain-level compliance scores
- KPI rollups
- Ranked top remediation actions

### 7) AI Audit Agent
Natural-language querying over JML datasets with payload-aware routing and summarization.

Example prompts:
- "Show leavers still holding privileged roles"
- "What are the top onboarding control failures this quarter?"
- "Summarize highest-risk identity lifecycle gaps"

## Portfolio Value / What This Demonstrates

This repository demonstrates:
- Practical identity governance engineering on Microsoft Graph
- Multi-domain audit analytics (J/M/L + privileged + guests)
- Evidence-aware reporting for audit traceability
- Resilience patterns: caching, throttling-aware retries, bounded scans
- Full-stack implementation with a cohesive investigative UX
- LLM integration with token/payload management for enterprise data

## Solution Architecture

```text
React (Vite) UI
  -> FastAPI API layer
     -> Microsoft Graph (users, audit logs, roles, reports)
     -> Azure OpenAI (optional, for NLQ agent)
```

### Backend Highlights
- FastAPI endpoints for each compliance domain.
- In-memory cache with TTL and per-key locking to avoid duplicate expensive Graph fetches.
- Graph client with retry/backoff behavior for throttling and transient failures.
- Audit-log retention-aware query clamping for Graph constraints.
- Bounded page limits and concurrency controls for large tenants.

### Frontend Highlights
- Tabbed executive workflow (Overview, Joiners, Movers, Leavers, Privileged, Guests, AI Agent).
- Searchable/sortable tables.
- Conditional views by risk type.
- Trace/evidence expansion for forensic auditability.

## Tech Stack

### Backend
- Python
- FastAPI
- Uvicorn
- MSAL
- Requests
- python-dotenv
- OpenAI SDK (Azure OpenAI)

### Frontend
- React 19
- Vite
- Axios
- ESLint

## Repository Structure

```text
app/
  main.py         # API surface + cache + CORS + optional static mount
  graph.py        # Microsoft Graph auth + pagination + retry utilities
  joiners.py      # Joiners analytics
  movers.py       # Movers analytics
  leavers.py      # Leavers analytics
  audit.py        # Privileged access analytics
  guests.py       # Guest account analytics
  overview.py     # Composite score + top actions
  agent.py        # Azure OpenAI-powered natural language agent
  utils.py        # Shared date/time/filter helpers

frontend/
  src/pages/      # Feature pages (Overview, Joiners, Movers, etc.)
  src/components/ # Reusable table/cards
  src/services/   # API client
```

## API Surface

Base URL: `http://127.0.0.1:8001`

- `GET /healthz` - Service health
- `GET /joiners` - Joiners analysis (`?refresh=true` bypasses cache)
- `GET /movers` - Movers analysis
- `GET /leavers` - Leavers analysis
- `GET /privileged` - Privileged access audit
- `GET /guests` - Guest audit
- `GET /overview` - Cross-domain executive rollup
- `POST /agent` - AI query endpoint

Example request body for AI endpoint:

```json
{
  "query": "show disabled users still in distribution lists"
}
```

## Local Setup

## 1) Prerequisites
- Python 3.10+
- Node.js 18+
- npm
- Microsoft Entra app registration with required Microsoft Graph application permissions

## 2) Backend Setup

From repository root:

```bash
python -m venv .venv
```

Windows PowerShell:

```bash
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

## 3) Frontend Setup

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5174`.

## 4) Environment Variables

Create a `.env` file in repository root:

```env
# Microsoft Graph app credentials
CLIENT_ID=<entra-app-client-id>
CLIENT_SECRET=<entra-app-client-secret>
TENANT_ID=<entra-tenant-id>

# Optional AI agent (Azure OpenAI)
AZURE_OPENAI_KEY=<key>
AZURE_OPENAI_ENDPOINT=<https://...openai.azure.com>
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT=<deployment-name>

# Scan windows and performance tuning
JML_LOOKBACK_DAYS=90
JML_AUDIT_LOOKBACK_DAYS=27
MFA_REPORT_PAGE_LIMIT=200
MOVERS_AUDIT_PAGE_LIMIT=50
LEAVERS_CONCURRENCY=10
AGENT_MAX_RECORDS_PER_INSIGHT=100

# Optional frontend API base override (frontend/.env)
# VITE_API_BASE_URL=http://127.0.0.1:8001
```

## Typical Use Cases

- Internal IT audit readiness and evidence collection
- Quarterly access recertification support
- Identity governance operations for SOC/ISO control programs
- Offboarding quality assurance and license reclamation
- Privileged access exposure monitoring
- Guest account hygiene and third-party lifecycle governance

## Real-World Applications

- Enterprise IAM program reporting
- Security operations identity hygiene dashboarding
- Managed security service onboarding/offboarding controls
- Compliance engineering proof-of-control tooling
- Executive risk posture reporting for identity lifecycle KPIs

## Data and Compliance Caveats

- **Graph retention and licensing**: Audit-log lookback depth is tenant-license dependent; the app defaults to a safe audit window.
- **Permission scope sensitivity**: Some privileged/PIM insights require elevated Graph permissions (for example, role management read capabilities).
- **Large tenant trade-offs**: To control latency and API limits, several analyses intentionally cap page depth and truncate AI context payloads.
- **Cache freshness**: API responses are cached (30 min TTL). Use `?refresh=true` when immediate consistency is required.
- **AI response boundaries**: The AI agent relies on selected/truncated datasets for performance; use domain endpoints for exhaustive exports.
- **In-memory cache**: Current cache is process-local; multi-instance deployments require external cache for shared consistency.

## Current Known Implementation Caveats

- Frontend import paths currently appear inconsistent in two places:
  - `frontend/src/App.jsx` imports `./pages/AgentsPage` while the page file is `AgentPage.jsx`.
  - Several page files import `../services/api` while the service file is `Api.js`.

These may work inconsistently depending on platform and filesystem behavior; normalize naming/casing before production deployment.

## Security Notes

- Store secrets in environment variables or managed secret stores.
- Prefer certificate/managed-identity auth patterns in production over static secrets.
- Restrict Graph application permissions to least privilege and review admin consent regularly.
- Treat exported audit evidence as sensitive operational data.

## Suggested Roadmap

- Add persistent datastore for historical trend lines and diffing between scans.
- Add role-based application access and tenant scoping in UI.
- Add export pipelines (CSV/PDF) and policy-as-code checks.
- Add automated remediation workflows (ticketing/approval hooks).
- Add containerization and cloud deployment blueprint.

## License / Usage

No license file is currently present in this repository. Add a project license before external distribution.

## Text-Based Architecture Diagram

```text
              +----------------------------------+
              |            End Users             |
              |  (Security, IAM, Audit, IT Ops) |
              +-----------------+----------------+
              |
              v
              +----------------------------------+
              |   React Frontend (Vite, :5174)   |
              |  - Overview / Joiners / Movers   |
              |  - Leavers / Privileged / Guests |
              |  - AI Agent Query Console        |
              +-----------------+----------------+
              |
             HTTP/JSON (Axios) |
              v
              +----------------------------------+
              |      FastAPI Backend (:8001)     |
              |  app/main.py                     |
              |  - REST endpoints per domain     |
              |  - 30-min in-memory cache        |
              |  - per-key locking + refresh     |
              +-----------+-----------+----------+
              |           |
       domain analytics modules |           | AI/NLQ endpoint
              v           v
  +----------------------------------+   +----------------------------------+
  |  Analytics Engine (Python)       |   |     Azure OpenAI (optional)      |
  |  - joiners.py                    |   |  - agent.py query orchestration   |
  |  - movers.py                     |   |  - keyword-based dataset routing  |
  |  - leavers.py                    |   |  - structured JSON responses      |
  |  - audit.py (privileged)         |   +----------------------------------+
  |  - guests.py                     |
  |  - overview.py (composite score)|
  +-----------------+----------------+
        |
        | Microsoft Graph API calls (MSAL app auth)
        v
  +----------------------------------------------------------------+
  |                     Microsoft Graph / Entra ID                 |
  |  /users, /auditLogs/directoryAudits, /directoryRoles, reports  |
  |  roleEligibilityScheduleInstances, transitiveMemberOf, etc.    |
  +----------------------------------------------------------------+

Data Flow Summary
1. Frontend calls FastAPI endpoints for each compliance domain.
2. Backend analytics modules query Graph and compute risk/compliance outputs.
3. Results are cached and returned as summary + insights + recommendations.
4. Overview aggregates all domains into weighted executive posture scores.
5. AI Agent route optionally sends compacted domain data to Azure OpenAI.
```

## Disclaimer

This project is a generalized and sanitized portfolio implementation inspired by enterprise automation scenarios. No proprietary company information, credentials, production configurations, or internal business logic are included.
