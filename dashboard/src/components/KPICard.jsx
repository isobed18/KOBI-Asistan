export default function KPICard({ icon, label, value, sub, color }) {
  const style = color ? { color } : {}
  return (
    <div className="kpi-card">
      {icon && <div className="kpi-icon">{icon}</div>}
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={style}>{value ?? '—'}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  )
}
