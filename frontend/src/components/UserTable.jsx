import { Fragment, useMemo, useState } from "react";

const DATE_RE = /^\d{4}-\d{2}-\d{2}T/;

function formatDate(iso) {
  try {
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    const days = Math.floor((Date.now() - d.getTime()) / 86400000);
    return `${d.toLocaleDateString()} (${days}d ago)`;
  } catch {
    return iso;
  }
}

const HIDDEN_COLUMNS = new Set(["evidence", "userId"]);

// Override the auto-generated "Group Count" → "AAD/M365/Teams Group Count" etc.
// Add more entries here as needed; falls back to camelCase → Title Case for
// any key not listed.
const HEADER_OVERRIDES = {
  groupCount: "Total Group Count",
  aadSecurityGroupCount: "AAD Security Group Count",
  m365GroupCount: "M365 Group / Teams Count",
  distributionListCount: "Distribution List Count",
  mailSecurityGroupCount: "Mail-Enabled Security Group Count",
  activeRoles: "Active PIM / Standing Roles",
  distributionLists: "Distribution Lists",
  disabledMembers: "Disabled Members (UPN)",
  disabledMemberCount: "Disabled Member Count",
  distributionList: "Distribution List",
  eligibleAssignmentCount: "Eligible PIM Count",
  eligibleAssignmentRoles: "Eligible PIM Roles",
};

export default function UserTable({ users }) {
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const [expanded, setExpanded] = useState(null);

  if (!users || users.length === 0) {
    return <div className="empty">No data</div>;
  }

  const columns = Object.keys(users[0]).filter((c) => !HIDDEN_COLUMNS.has(c));
  const hasEvidence = users.some((u) => u.evidence);

  const formatHeader = (key) => {
    if (HEADER_OVERRIDES[key]) return HEADER_OVERRIDES[key];
    return key.replace(/([A-Z])/g, " $1").replace(/^./, (s) => s.toUpperCase()).trim();
  };

  // Keys we prefer when picking a display label out of a nested object.
  // Order matters — first hit wins.
  const NAME_KEYS = ["role", "roleName", "displayName", "name", "title", "user", "userPrincipalName"];

  const formatNested = (obj) => {
    if (obj === null || obj === undefined) return "—";
    if (typeof obj !== "object") return String(obj);
    // Prefer a known name-y field for a clean label.
    for (const k of NAME_KEYS) {
      if (obj[k] != null && typeof obj[k] !== "object") {
        // Append tier if present and not already in the label — handy for PIM/role results.
        if (obj.tier !== undefined && obj.tier !== null) return `${obj[k]} (T${obj.tier})`;
        return String(obj[k]);
      }
    }
    // Fall back to a compact "k: v" join, skipping nested objects.
    const parts = Object.entries(obj)
      .filter(([, v]) => v !== null && v !== undefined && typeof v !== "object")
      .map(([k, v]) => `${k}: ${v}`);
    return parts.length ? parts.join(", ") : JSON.stringify(obj);
  };

  const formatCell = (val) => {
    if (val === null || val === undefined) return "—";
    if (Array.isArray(val)) {
      if (val.length === 0) return "—";
      return val.map((v) => (typeof v === "object" ? formatNested(v) : String(v))).join(", ");
    }
    if (typeof val === "object") return formatNested(val);
    if (typeof val === "boolean") return val ? "✓" : "✗";
    if (typeof val === "string" && DATE_RE.test(val)) return formatDate(val);
    return val;
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) => JSON.stringify(u).toLowerCase().includes(q));
  }, [users, search]);

  const sorted = useMemo(() => {
    if (!sortBy) return filtered;
    const copy = [...filtered];
    copy.sort((a, b) => {
      const av = a[sortBy], bv = b[sortBy];
      const an = typeof av === "number" ? av : parseFloat(av);
      const bn = typeof bv === "number" ? bv : parseFloat(bv);
      const numeric = !isNaN(an) && !isNaN(bn);
      const cmp = numeric ? an - bn : String(av ?? "").localeCompare(String(bv ?? ""));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [filtered, sortBy, sortDir]);

  const toggleSort = (col) => {
    if (sortBy === col) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortBy(col); setSortDir("asc"); }
  };

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, gap: 12 }}>
        <input
          type="text"
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            padding: "6px 12px",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            background: "var(--surface)",
            color: "var(--text)",
            fontSize: 13,
            fontFamily: "inherit",
            outline: "none",
            minWidth: 220,
          }}
        />
        <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
          {sorted.length} of {users.length} rows
        </span>
      </div>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              {columns.map((key) => (
                <th
                  key={key}
                  onClick={() => toggleSort(key)}
                  style={{ cursor: "pointer", userSelect: "none" }}
                >
                  {formatHeader(key)}
                  {sortBy === key && (sortDir === "asc" ? " ↑" : " ↓")}
                </th>
              ))}
              {hasEvidence && <th>Evidence</th>}
            </tr>
          </thead>
          <tbody>
            {sorted.map((user, i) => {
              const key = user.user || user.id || i;
              const isExpanded = expanded === key;
              return (
                <Fragment key={key}>
                  <tr>
                    {columns.map((col) => (
                      <td key={col}>{formatCell(user[col])}</td>
                    ))}
                    {hasEvidence && (
                      <td>
                        <button
                          style={{ padding: "4px 10px", fontSize: 11 }}
                          onClick={() => setExpanded(isExpanded ? null : key)}
                        >
                          {isExpanded ? "Hide" : "Trace"}
                        </button>
                      </td>
                    )}
                  </tr>
                  {isExpanded && user.evidence && (
                    <tr>
                      <td colSpan={columns.length + 1} style={{ background: "var(--surface-2)" }}>
                        <div className="evidence-block">
                          <strong>Source:</strong> {user.evidence.source}<br />
                          <strong>Checked at:</strong> {user.evidence.checkedAt}<br />
                          {user.evidence.activityId && (<><strong>Activity ID:</strong> {user.evidence.activityId}<br /></>)}
                          {user.evidence.correlationId && (<><strong>Correlation ID:</strong> {user.evidence.correlationId}<br /></>)}
                          {user.evidence.disableActivityId && (<><strong>Disable Activity ID:</strong> {user.evidence.disableActivityId}<br /></>)}
                          {user.evidence.roleId && (<><strong>Role ID:</strong> {user.evidence.roleId}<br /></>)}
                          {Array.isArray(user.evidence.roleIds) && user.evidence.roleIds.length > 0 && (
                            <><strong>Role IDs:</strong> {user.evidence.roleIds.join(", ")}<br /></>
                          )}
                          {user.evidence.auditChanges && (
                            <>
                              <strong>Audit changes:</strong>
                              <pre style={{ marginTop: 4, fontSize: 11 }}>
                                {JSON.stringify(user.evidence.auditChanges, null, 2)}
                              </pre>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
