import { useState } from "react";
import OverviewPage from "./pages/OverviewPage";
import JoinersPage from "./pages/JoinersPage";
import MoversPage from "./pages/MoversPage";
import LeaversPage from "./pages/LeaversPage";
import PrivilegedPage from "./pages/PrivilegedPage";
import GuestsPage from "./pages/GuestsPage";
import AgentPage from "./pages/AgentsPage";

const TABS = [
  { id: "overview",   label: "Overview" },
  { id: "joiners",    label: "Joiners" },
  { id: "movers",     label: "Movers" },
  { id: "leavers",    label: "Leavers" },
  { id: "privileged", label: "Privileged" },
  { id: "guests",     label: "Guests" },
  { id: "agent",      label: "AI Agent" },
];

function App() {
  const [tab, setTab] = useState("overview");

  return (
    <>
      <header className="app-header">
        <h1>JML Compliance Audit</h1>
        <div className="tab-buttons">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={tab === t.id ? "active" : ""}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>

      {tab === "overview"   && <OverviewPage onNavigate={setTab} />}
      {tab === "joiners"    && <JoinersPage />}
      {tab === "movers"     && <MoversPage />}
      {tab === "leavers"    && <LeaversPage />}
      {tab === "privileged" && <PrivilegedPage />}
      {tab === "guests"     && <GuestsPage />}
      {tab === "agent"      && <AgentPage />}
    </>
  );
}

export default App;
