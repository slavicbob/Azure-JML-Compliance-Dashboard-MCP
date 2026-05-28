import { useEffect, useState } from "react";
import { fetchMovers } from "../services/api";
import SummaryCard from "../components/SummaryCard";
import UserTable from "../components/UserTable";

export default function MoversPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchMovers()
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load movers."));
  }, []);

  if (error) return <div className="container"><div className="error">{error}</div></div>;
  if (!data) return <div className="container"><p>Loading…</p></div>;

  return (
    <div className="container">
      <h2 className="page-title">Movers</h2>
      <p className="page-sub">
        Users whose manager, department, job title, or company changed in the last {data.lookbackDays} days
        — schedule access reviews for each.
      </p>

      <SummaryCard summary={data.summary} />

      <h3>Movers Requiring Access Review</h3>
      <UserTable users={data.insights.movers} />

      {data.insights.topTransitions && data.insights.topTransitions.length > 0 && (
        <>
          <h3>Top Department Transitions</h3>
          <div className="table-wrapper">
            <table>
              <thead><tr><th>Transition</th><th>Count</th></tr></thead>
              <tbody>
                {data.insights.topTransitions.map((t, i) => (
                  <tr key={i}><td>{t.transition}</td><td>{t.count}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
