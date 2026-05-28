import { useEffect, useState } from "react";
import { fetchGuests } from "../services/api";
import SummaryCard from "../components/SummaryCard";
import UserTable from "../components/UserTable";

export default function GuestsPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState("stale");

  useEffect(() => {
    fetchGuests()
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load guests."));
  }, []);

  if (error) return <div className="container"><div className="error">{error}</div></div>;
  if (!data) return <div className="container"><p>Loading…</p></div>;

  const views = {
    stale: data.insights.stale,
    pending: data.insights.pending,
    all: data.insights.guests,
  };

  return (
    <div className="container">
      <h2 className="page-title">Guest Accounts</h2>
      <p className="page-sub">
        External / B2B users — stale threshold {data.thresholdDays} days.
      </p>

      <SummaryCard summary={data.summary} />

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button className={view === "stale" ? "btn-primary" : ""} onClick={() => setView("stale")}>
          Stale ({data.insights.stale.length})
        </button>
        <button className={view === "pending" ? "btn-primary" : ""} onClick={() => setView("pending")}>
          Pending invite ({data.insights.pending.length})
        </button>
        <button className={view === "all" ? "btn-primary" : ""} onClick={() => setView("all")}>
          All ({data.insights.guests.length})
        </button>
      </div>

      <UserTable users={views[view]} />
    </div>
  );
}
