import { useEffect, useState } from "react";
import { fetchOverview } from "../services/api";

function scoreColor(score) {
  if (score >= 90) return "ok";
  if (score >= 70) return "warn";
  return "danger";
}

export default function OverviewPage({ onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = (refresh = false) => {
    setLoading(true);
    setError(null);
    fetchOverview(refresh)
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load overview."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  if (error) return <div className="container"><div className="error">{error}</div></div>;
  if (!data) return <div className="container"><p>Loading…</p></div>;

  const { scores, kpis, topActions, generatedAt, lookbackDays } = data;

  return (
    <div className="container">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8, flexWrap: "wrap", gap: 12 }}>
        <h2 className="page-title">Executive Overview</h2>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Last scan: {generatedAt ? new Date(generatedAt).toLocaleString() : "—"} · {lookbackDays}-day window
          </span>
          <button onClick={() => load(true)} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>
      <p className="page-sub">Identity lifecycle compliance posture at a glance — audit-ready.</p>

      <div className="score-card">
        <div>
          <div className="score-label">Composite Compliance Score</div>
          <div className="score-value" style={{
            color: scores.composite >= 90 ? "var(--ok)" : scores.composite >= 70 ? "var(--warn)" : "var(--danger)"
          }}>
            {scores.composite}
            <span style={{ fontSize: 20, color: "var(--text-muted)", marginLeft: 4 }}>/ 100</span>
          </div>
        </div>
        <div className="score-meta">
          <div>Joiner provisioning: <strong>{scores.joinerCompliance}%</strong></div>
          <div>Leaver deprovisioning: <strong>{scores.leaverCompliance}%</strong></div>
          <div>Guest hygiene: <strong>{scores.guestHygiene}%</strong></div>
          <div>Privileged hygiene: <strong>{scores.privilegedHygiene}%</strong></div>
        </div>
      </div>

      <h3>Lifecycle KPIs</h3>
      <div className="summary-container">
        <div className="card">
          <div className="card-label">Joiners</div>
          <div className="card-value">{kpis.totalJoiners}</div>
        </div>
        <div className={`card ${kpis.incompleteProvisioning ? "warn" : "ok"}`}>
          <div className="card-label">Incomplete Onboarding</div>
          <div className="card-value">{kpis.incompleteProvisioning}</div>
        </div>
        <div className="card">
          <div className="card-label">Movers</div>
          <div className="card-value">{kpis.totalMovers}</div>
        </div>
        <div className="card">
          <div className="card-label">Disabled Users</div>
          <div className="card-value">{kpis.totalLeavers}</div>
        </div>
        <div className={`card ${kpis.incompleteDeprovisioning ? "danger" : "ok"}`}>
          <div className="card-label">Incomplete Offboarding</div>
          <div className="card-value">{kpis.incompleteDeprovisioning}</div>
        </div>
        <div className="card">
          <div className="card-label">Guests</div>
          <div className="card-value">{kpis.totalGuests}</div>
        </div>
        <div className={`card ${kpis.staleGuests ? "warn" : ""}`}>
          <div className="card-label">Stale Guests</div>
          <div className="card-value">{kpis.staleGuests}</div>
        </div>
        <div className={`card ${kpis.tier0Admins > 5 ? "warn" : ""}`}>
          <div className="card-label">Tier-0 Admins</div>
          <div className="card-value">{kpis.tier0Admins}</div>
        </div>
        <div className={`card ${kpis.selfGrants ? "danger" : ""}`}>
          <div className="card-label">Self-Granted Roles</div>
          <div className="card-value">{kpis.selfGrants}</div>
        </div>
        <div className="card">
          <div className="card-label">Role Changes (window)</div>
          <div className="card-value">{kpis.roleChangesInPeriod}</div>
        </div>
      </div>

      <h3>Top Audit Actions</h3>
      {topActions && topActions.length ? (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Priority</th>
                <th>Action</th>
                <th>Impact</th>
                <th>Area</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {topActions.map((a, i) => (
                <tr key={i}>
                  <td>#{i + 1}</td>
                  <td>{a.title}</td>
                  <td>{a.impact}</td>
                  <td>
                    <span className={`badge ${
                      a.category === "leavers" || a.category === "privileged" ? "danger" :
                      a.category === "joiners" || a.category === "movers" ? "warn" : "muted"
                    }`}>
                      {a.category}
                    </span>
                  </td>
                  <td>
                    <button onClick={() => onNavigate(a.category)}>View →</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty">No outstanding compliance actions — tenant is audit-clean.</div>
      )}
    </div>
  );
}
