import { useEffect, useState } from "react";
import { fetchLeavers } from "../services/api";
import SummaryCard from "../components/SummaryCard";
import UserTable from "../components/UserTable";

export default function LeaversPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState("incomplete");

  useEffect(() => {
    fetchLeavers()
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load leavers."));
  }, []);

  if (error) return <div className="container"><div className="error">{error}</div></div>;
  if (!data) return <div className="container"><p>Loading…</p></div>;

  const views = {
    incomplete: data.insights.incomplete,
    stillPrivileged: data.insights.stillPrivileged,
    stillLicensed: data.insights.stillLicensed,
    stillInDLs: data.insights.stillInDLs || [],
    all: data.insights.leavers,
  };

  const dlsWithDisabled = data.insights.distributionListsWithDisabledMembers || [];

  return (
    <div className="container">
      <h2 className="page-title">Leavers</h2>
      <p className="page-sub">
        Disabled accounts and their deprovisioning status — primary audit failure surface.
      </p>

      <SummaryCard summary={data.summary} />

      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <button className={view === "incomplete" ? "btn-primary" : ""} onClick={() => setView("incomplete")}>
          Incomplete ({data.insights.incomplete.length})
        </button>
        <button className={view === "stillPrivileged" ? "btn-primary" : ""} onClick={() => setView("stillPrivileged")}>
          Active PIM / Standing Roles ({data.insights.stillPrivileged.length})
        </button>
        <button className={view === "stillLicensed" ? "btn-primary" : ""} onClick={() => setView("stillLicensed")}>
          Still licensed ({data.insights.stillLicensed.length})
        </button>
        <button className={view === "stillInDLs" ? "btn-primary" : ""} onClick={() => setView("stillInDLs")}>
          Still in DLs ({views.stillInDLs.length})
        </button>
        <button className={view === "all" ? "btn-primary" : ""} onClick={() => setView("all")}>
          All disabled ({data.insights.leavers.length})
        </button>
      </div>

      <UserTable users={views[view]} />

      <h3>Distribution Lists Containing Disabled Users</h3>
      <p className="page-sub" style={{ marginBottom: 12 }}>
        Pivoted view — each DL with at least one disabled member. Disabled members
        continue receiving mail until removed.
      </p>
      <UserTable users={dlsWithDisabled} />
    </div>
  );
}
