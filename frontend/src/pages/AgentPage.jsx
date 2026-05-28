import { useState } from "react";
import { fetchAgent } from "../services/api";
import UserTable from "../components/UserTable";

const TITLES = {
  joiners: "Joiners",
  movers: "Movers",
  leavers: "Leavers",
  privileged: "Privileged",
  guests: "Guests",
  combined: "Results",
  summary: "Summary",
};

function formatLabel(key) {
  return key.replace(/([A-Z])/g, " $1").replace(/^./, (s) => s.toUpperCase()).trim();
}

function tryParse(s) {
  if (typeof s !== "string") return s;
  const cleaned = s.replace(/```json/gi, "").replace(/```/g, "").trim();
  try { return JSON.parse(cleaned); } catch { return s; }
}

function unwrap(response) {
  if (!response) return null;
  let { type, data } = response;

  if (type === "raw" && typeof data === "string") {
    const parsed = tryParse(data);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && "type" in parsed) {
      return unwrap(parsed);
    }
    return { type: "auto", data: parsed };
  }
  if (typeof data === "string") {
    const parsed = tryParse(data);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && "type" in parsed) {
      return unwrap(parsed);
    }
    return { type, data: parsed };
  }
  return { type, data };
}

function renderCell(value) {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) {
    if (value.length === 0) return "—";
    if (typeof value[0] === "object") return <UserTable users={value} />;
    return value.join(", ");
  }
  if (typeof value === "object") return <pre>{JSON.stringify(value, null, 2)}</pre>;
  return String(value);
}

export default function AgentPage() {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const runQuery = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResponse(null);
    try {
      const res = await fetchAgent(query);
      setResponse(res.data);
    } catch (err) {
      console.error(err);
      setError("Something went wrong while running the agent.");
    }
    setLoading(false);
  };

  const renderResult = () => {
    const unwrapped = unwrap(response);
    if (!unwrapped) return null;
    const { type, data } = unwrapped;
    const title = TITLES[type] || "Result";

    const isEmpty =
      data === null || data === undefined ||
      (Array.isArray(data) && data.length === 0) ||
      (typeof data === "object" && !Array.isArray(data) && Object.keys(data).length === 0);

    if (isEmpty) return (<><h3>{title}</h3><div className="empty">No results.</div></>);

    if (Array.isArray(data) && typeof data[0] === "object") {
      return (<><h3>{title}</h3><UserTable users={data} /></>);
    }
    if (Array.isArray(data)) {
      return (<><h3>{title}</h3><p>{data.join(", ")}</p></>);
    }
    if (typeof data === "object") {
      const allPrimitive = Object.values(data).every(
        (v) => v === null || ["string", "number", "boolean"].includes(typeof v)
      );
      if (allPrimitive) {
        return (
          <>
            <h3>{title}</h3>
            <div className="summary-container">
              {Object.entries(data).map(([k, v]) => (
                <div key={k} className="card">
                  <div className="card-label">{formatLabel(k)}</div>
                  <div className="card-value">{v ?? "—"}</div>
                </div>
              ))}
            </div>
          </>
        );
      }
      return (
        <>
          <h3>{title}</h3>
          <div className="table-wrapper">
            <table>
              <tbody>
                {Object.entries(data).map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ fontWeight: 600, width: "30%" }}>{formatLabel(k)}</td>
                    <td>{renderCell(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      );
    }
    return (<><h3>{title}</h3><p>{String(data)}</p></>);
  };

  return (
    <div className="container">
      <h2 className="page-title">AI Audit Agent</h2>
      <p className="page-sub">
        Natural-language queries across joiners, movers, leavers, privileged, and guests.
      </p>

      <div className="agent-input">
        <textarea
          placeholder={"Ask anything (e.g., \"show leavers still holding privileged roles\" or \"who self-granted a role this quarter\")"}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={4}
        />
        <button onClick={runQuery} disabled={loading}>
          {loading ? "Running…" : "Run"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="agent-response">{renderResult()}</div>
    </div>
  );
}
