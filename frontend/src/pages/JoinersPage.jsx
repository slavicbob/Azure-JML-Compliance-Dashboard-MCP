import { useEffect, useState } from "react";
import { fetchJoiners } from "../services/api";
import SummaryCard from "../components/SummaryCard";
import UserTable from "../components/UserTable";

export default function JoinersPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState("incomplete");

  useEffect(() => {
    fetchJoiners()
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load joiners."));
  }, []);

  if (error) return <div className="container"><div className="error">{error}</div></div>;
  if (!data) return <div className="container"><p>Loading…</p></div>;

  const list = view === "all" ? data.insights.joiners : data.insights.incomplete;

  return (
    <div className="container">
      <h2 className="page-title">Joiners</h2>
      <p className="page-sub">
        New accounts created in the last {data.lookbackDays} days — provisioning checklist per user.
      </p>

      <SummaryCard summary={data.summary} />

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button
          className={view === "incomplete" ? "btn-primary" : ""}
          onClick={() => setView("incomplete")}
        >
          Incomplete only ({data.insights.incomplete.length})
        </button>
        <button
          className={view === "all" ? "btn-primary" : ""}
          onClick={() => setView("all")}
        >
          All joiners ({data.insights.joiners.length})
        </button>
      </div>

      <UserTable users={list} />

      {data.insights.byDepartment && Object.keys(data.insights.byDepartment).length > 0 && (
        <>
          <h3>Joiners by Department</h3>
          <div className="table-wrapper">
            <table>
              <thead><tr><th>Department</th><th>Count</th></tr></thead>
              <tbody>
                {Object.entries(data.insights.byDepartment)
                  .sort((a, b) => b[1] - a[1])
                  .map(([dept, count]) => (
                    <tr key={dept}><td>{dept}</td><td>{count}</td></tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
