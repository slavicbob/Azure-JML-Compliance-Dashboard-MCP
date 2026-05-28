"""AI Agent — natural language queries across JML data.

Payload management:
  The raw scan datasets carry per-record `evidence` blocks (audit-log IDs,
  correlation IDs) and `auditChanges` (full property-change history) for the
  UI's traceability features. None of this helps the LLM answer questions,
  but it inflates the request body to many MB on large tenants and trips
  Azure OpenAI's 10 MB per-message cap.

  We do three things before calling the model:
    1. Strip heavy fields (`evidence`, `auditChanges`) from every record.
    2. Truncate each insight array to MAX_RECORDS (default 100).
    3. Route on query keywords — only include the datasets that look
       relevant to the user's question.
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()

try:
    from openai import AzureOpenAI
    _client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    ) if os.getenv("AZURE_OPENAI_KEY") else None
except Exception:
    _client = None

MODEL = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

# How many records per insight list to send to the model. The summary still
# carries the total counts, so the model always knows the dataset size.
MAX_RECORDS = int(os.getenv("AGENT_MAX_RECORDS_PER_INSIGHT", "100"))

# Fields to drop from every record before serialization.
_DROP_FIELDS = {"evidence", "auditChanges"}

# Keyword → dataset routing. Anything that doesn't match a keyword falls
# back to "all datasets included" so the agent still works for vague queries.
_KEYWORD_ROUTES = {
    "joiners":    {"joiner", "new hire", "onboard", "provision", "created"},
    "movers":     {"mover", "moved", "role change", "transfer", "promotion", "department change"},
    "leavers":    {"leaver", "left", "disabled", "offboard", "deprovision", "terminat",
                   "distribution list", "dl ", "in dls", "still in dl"},
    "privileged": {"privileged", "admin", "pim", "tier 0", "tier-0", "role assign",
                   "self-grant", "self grant", "global admin"},
    "guests":     {"guest", "external", "b2b", "invite", "stale guest"},
}


def _compact_record(rec):
    """Return a record dict with heavy traceability fields removed."""
    if not isinstance(rec, dict):
        return rec
    return {k: v for k, v in rec.items() if k not in _DROP_FIELDS}


def _compact_dataset(dataset):
    """Strip heavy fields and truncate insight arrays in a single dataset."""
    if not isinstance(dataset, dict):
        return dataset

    out = {
        "generatedAt": dataset.get("generatedAt"),
        "lookbackDays": dataset.get("lookbackDays"),
        "thresholdDays": dataset.get("thresholdDays"),
        "summary": dataset.get("summary"),
    }
    insights = dataset.get("insights") or {}
    compact_insights = {}
    for key, val in insights.items():
        if isinstance(val, list):
            compact_insights[key] = [_compact_record(r) for r in val[:MAX_RECORDS]]
        else:
            compact_insights[key] = val
    out["insights"] = compact_insights
    out["recommendations"] = dataset.get("recommendations")
    # Remove None values for compactness
    return {k: v for k, v in out.items() if v is not None}


def _select_relevant(query: str, datasets: dict):
    """Return only the datasets that appear relevant to the query.

    Falls back to all datasets if no keyword matches — vague queries
    ('summarize the tenant') still get the full picture.
    """
    q = (query or "").lower()
    matched = {name for name, keywords in _KEYWORD_ROUTES.items()
               if any(kw in q for kw in keywords)}
    if not matched:
        return datasets
    return {name: data for name, data in datasets.items() if name in matched}


def run_agent(query: str, joiners=None, movers=None, leavers=None, audit=None, guests=None):
    if not _client:
        return {
            "type": "raw",
            "data": "AI Agent is not configured. Set AZURE_OPENAI_KEY in .env to enable.",
        }

    # 1. Compact each dataset (strip heavy fields, truncate insight lists).
    full_datasets = {
        "joiners":    _compact_dataset(joiners),
        "movers":     _compact_dataset(movers),
        "leavers":    _compact_dataset(leavers),
        "privileged": _compact_dataset(audit),
        "guests":     _compact_dataset(guests),
    }

    # 2. Keyword-route — only include datasets that look relevant to the query.
    selected = _select_relevant(query, full_datasets)

    # 3. Build the user content. Always include a one-line "datasets included"
    #    header so the model knows what it has (and what it doesn't).
    parts = [f"User query:\n{query}", f"\nDatasets included: {', '.join(sorted(selected.keys()))}"]
    for name, data in selected.items():
        parts.append(f"\n{name.title()}:\n{json.dumps(data, default=str)}")
    user_content = "\n".join(parts)

    response = _client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a compliance / identity-governance auditor's assistant.\n\n"
                    "The user message contains a subset of these datasets: joiners, "
                    "movers, leavers, privileged-role audit, and guests. The header "
                    "line 'Datasets included' tells you which are present.\n\n"
                    "Each dataset has a `summary` with TRUE totals plus an `insights` "
                    "section that may have been truncated to the top 100 records per "
                    "list. When answering 'how many' type questions, prefer the "
                    "summary counts; for samples and superlatives, use insights.\n\n"
                    "Return a JSON object with EXACTLY this shape:\n"
                    "{\n"
                    '  "type": "<one of: joiners | movers | leavers | privileged | guests | combined | summary>",\n'
                    '  "data": <array of records, single object, or summary object>\n'
                    "}\n\n"
                    "Rules:\n"
                    "- 'data' MUST be valid JSON, never a string.\n"
                    "- Each record should have a 'user' field plus the most relevant fields.\n"
                    "- For superlative queries (top N, most recent, oldest) sort and return the top 5.\n"
                    "- Omit fields that aren't relevant.\n"
                    "- No prose, no markdown — JSON only."
                ),
            },
            {"role": "user", "content": user_content},
        ],
    )

    raw = response.choices[0].message.content
    try:
        structured = json.loads(raw)
    except Exception:
        structured = {"type": "raw", "data": raw}

    return {"type": structured.get("type", "raw"), "data": structured.get("data")}
