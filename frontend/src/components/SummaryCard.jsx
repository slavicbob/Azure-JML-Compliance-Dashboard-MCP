export default function SummaryCard({ summary }) {
  const formatLabel = (key) =>
    key
      .replace(/([A-Z])/g, " $1")
      .replace(/^./, (s) => s.toUpperCase())
      .trim();

  const formatValue = (val) => {
    if (val === null || val === undefined) return "—";
    if (typeof val === "number") return val.toLocaleString();
    return String(val);
  };

  return (
    <div className="summary-container">
      {Object.entries(summary).map(([key, value]) => (
        <div key={key} className="card">
          <div className="card-label">{formatLabel(key)}</div>
          <div className="card-value">{formatValue(value)}</div>
        </div>
      ))}
    </div>
  );
}
