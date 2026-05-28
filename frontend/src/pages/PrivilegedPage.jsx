import { useEffect, useState } from "react";
import { fetchPrivileged } from "../services/api";
import SummaryCard from "../components/SummaryCard";
import UserTable from "../components/UserTable";

export default function PrivilegedPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchPrivileged()
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load privileged audit."));
  }, []);

  if (error) return <div className="container"><div className="error">{error}</div></div>;
  if (!data) return <div className="container"><p>Loading…</p></div>;

  return (
    <div className="container">
      <h2 className="page-title">Privileged Access</h2>
      <p className="page-sub">
        Standing admin assignments + grant/revoke audit trail for the last {data.lookbackDays} days.
      </p>

      <SummaryCard summary={data.summary} />

      <h3>Standing Privileges</h3>
      <UserTable users={data.insights.standingPrivileges} />

      <h3>Role Membership Summary</h3>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Role</th>
              <th>Tier</th>
              <th>Members</th>
            </tr>
          </thead>
          <tbody>
            {data.insights.roleSummary.map((r, i) => (
              <tr key={i}>
                <td>{r.role}</td>
                <td>
                  <span className={`badge ${r.tier === 0 ? "danger" : r.tier === 1 ? "warn" : "muted"}`}>
                    Tier {r.tier}
                  </span>
                </td>
                <td>{r.memberCount}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.insights.eligibleAssignments && data.insights.eligibleAssignments.length > 0 ? (
        <>
          <h3>Eligible Assignments (PIM)</h3>
          <p className="page-sub" style={{ marginTop: -6 }}>
            Principals currently <em>eligible</em> to elevate into a role via PIM — distinct from standing assignments above.
          </p>
          <UserTable users={data.insights.eligibleAssignments} />

          {data.insights.eligibleRoleSummary && data.insights.eligibleRoleSummary.length > 0 && (
            <>
              <h3>Eligible Role Summary</h3>
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Role</th>
                      <th>Tier</th>
                      <th>Eligible Principals</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.insights.eligibleRoleSummary.map((r, i) => (
                      <tr key={i}>
                        <td>{r.role}</td>
                        <td>
                          <span className={`badge ${r.tier === 0 ? "danger" : r.tier === 1 ? "warn" : "muted"}`}>
                            Tier {r.tier}
                          </span>
                        </td>
                        <td>{r.eligibleCount}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      ) : (
        <>
          <h3>Eligible Assignments (PIM)</h3>
          <div className="empty">
            No eligible assignments returned. This is normal if the tenant doesn't have Entra ID P2,
            or if the RoleManagement.Read.Directory permission hasn't been granted admin consent.
          </div>
        </>
      )}

      <h3>Role Change Audit Trail</h3>
      <UserTable users={data.insights.roleChanges} />

      {data.insights.multiRoleAdmins && data.insights.multiRoleAdmins.length > 0 && (
        <>
          <h3>Users Holding Multiple Roles</h3>
          <UserTable users={data.insights.multiRoleAdmins} />
        </>
      )}
    </div>
  );
}
