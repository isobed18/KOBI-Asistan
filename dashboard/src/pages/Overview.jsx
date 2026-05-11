import { useEffect, useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import { getDashboardStats, getSalesChart, generateAiTasks } from '../api.js'
import KPICard from '../components/KPICard.jsx'
import StatusBadge, { ORDER_STATUS, TICKET_STATUS, TICKET_TYPE } from '../components/StatusBadge.jsx'
import { useAuth } from '../context/AuthContext.jsx'

function fmt(n)      { return n?.toLocaleString('tr-TR') ?? '—' }
function fmtMoney(n) {
  return n != null
    ? `₺${n.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : '—'
}

// ---------------------------------------------------------------------------
// Welcome Banner — sadece ilk açılışta gösterilir (per-session)
// ---------------------------------------------------------------------------
function WelcomeBanner({ user }) {
  const [visible, setVisible] = useState(false)
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Günaydın' : hour < 18 ? 'İyi öğleden sonralar' : 'İyi akşamlar'
  const name = user?.full_name || user?.username || 'Yönetici'

  useEffect(() => {
    const key = 'wb_' + new Date().toDateString()
    if (!sessionStorage.getItem(key)) {
      sessionStorage.setItem(key, '1')
      setVisible(true)
      const t = setTimeout(() => setVisible(false), 5000)
      return () => clearTimeout(t)
    }
  }, [])

  if (!visible) return null
  return (
    <div className="welcome-banner">
      <div className="welcome-inner">
        <span className="welcome-wave">👋</span>
        <div>
          <div className="welcome-title">{greeting}, {name}!</div>
          <div className="welcome-sub">İşletmenizin bugünkü durumu yükleniyor…</div>
        </div>
        <button className="welcome-close" onClick={() => setVisible(false)}>✕</button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sales Chart — SVG tabanlı, son 7 gün
// ---------------------------------------------------------------------------
function SalesChart() {
  const [chartData, setChartData] = useState(null)
  useEffect(() => { getSalesChart().then(setChartData).catch(() => {}) }, [])

  if (!chartData) return <div style={{ height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text3)', fontSize: 13 }}>Yükleniyor…</div>

  const days = chartData.days
  const maxRev = Math.max(...days.map(d => d.revenue), 1)
  const W = 520, H = 100, PAD = 8
  const step = (W - PAD * 2) / (days.length - 1)

  const points = days.map((d, i) => [PAD + i * step, H - PAD - ((d.revenue / maxRev) * (H - PAD * 2))])
  const polyline = points.map(([x, y]) => `${x},${y}`).join(' ')
  const area = `${PAD},${H - PAD} ` + polyline + ` ${W - PAD},${H - PAD}`

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 100 }}>
        <defs>
          <linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <polygon points={area} fill="url(#sg)" />
        <polyline points={polyline} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />
        {points.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="3" fill="var(--accent)" />
        ))}
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text3)', marginTop: 4 }}>
        {days.map(d => (
          <span key={d.day}>{d.day.slice(5)}</span>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 16, marginTop: 8, fontSize: 12, color: 'var(--text2)' }}>
        <span>💰 <b>{fmtMoney(days.reduce((s, d) => s + d.revenue, 0))}</b> toplam</span>
        <span>📦 <b>{days.reduce((s, d) => s + d.order_count, 0)}</b> sipariş</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// AI Task Bar
// ---------------------------------------------------------------------------
const TASK_PRIORITY_COLOR = { high: 'var(--danger)', normal: 'var(--accent)', low: 'var(--text3)' }

function AiTaskBar() {
  const [state, setState]   = useState('idle')  // idle | loading | loaded | error
  const [tasks, setTasks]   = useState([])
  const [briefing, setBrief] = useState('')
  const [dismissed, setDismissed] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('dismissed_tasks') || '[]') } catch { return [] }
  })

  const load = () => {
    setState('loading')
    generateAiTasks()
      .then(r => {
        setBrief(r.briefing || '')
        setTasks(r.tasks || [])
        setState('loaded')
      })
      .catch(() => setState('error'))
  }

  useEffect(() => { load() }, [])

  const dismiss = (id) => {
    const next = [...dismissed, id]
    setDismissed(next)
    sessionStorage.setItem('dismissed_tasks', JSON.stringify(next))
  }

  const visible = tasks.filter(t => !dismissed.includes(t.id))

  if (state === 'idle' || state === 'loading') {
    return (
      <div className="ai-taskbar ai-taskbar-loading">
        <span className="ai-taskbar-icon">🤖</span>
        <span style={{ fontSize: 13, color: 'var(--text2)' }}>AI görev listesi hazırlanıyor…</span>
        <div className="chat-typing" style={{ marginLeft: 8 }}><span /><span /><span /></div>
      </div>
    )
  }

  if (state === 'error' || visible.length === 0) {
    return (
      <div className="ai-taskbar">
        <span className="ai-taskbar-icon">✅</span>
        <span style={{ fontSize: 13, color: 'var(--text2)' }}>
          {state === 'error' ? 'AI bağlantı hatası — görevler yüklenemedi.' : 'Harika! Bugün için öncelikli görev yok.'}
        </span>
        <button className="btn btn-ghost btn-sm" style={{ marginLeft: 'auto' }} onClick={load}>↺ Yenile</button>
      </div>
    )
  }

  return (
    <div className="ai-taskbar-wrap">
      <div className="ai-taskbar-header">
        <span className="ai-taskbar-icon">🤖</span>
        <div>
          <div style={{ fontWeight: 600, fontSize: 14 }}>AI Asistan Önerileri</div>
          <div style={{ fontSize: 12, color: 'var(--text2)' }}>{briefing}</div>
        </div>
        <button className="btn btn-ghost btn-sm" style={{ marginLeft: 'auto' }} onClick={load}>↺ Yenile</button>
      </div>
      <div className="ai-task-list">
        {visible.map(t => (
          <div key={t.id} className="ai-task-card">
            <div className="ai-task-icon">{t.icon}</div>
            <div className="ai-task-body">
              <div className="ai-task-title" style={{ color: TASK_PRIORITY_COLOR[t.priority] }}>{t.title}</div>
              <div className="ai-task-desc">{t.body}</div>
            </div>
            <div className="ai-task-actions">
              <Link to={t.link} className="btn btn-primary btn-sm">İncele →</Link>
              <button className="btn btn-ghost btn-sm" onClick={() => dismiss(t.id)} title="Görev kapat">✕</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Overview
// ---------------------------------------------------------------------------
export default function Overview() {
  const { user } = useAuth()
  const [data, setData]         = useState(null)
  const [error, setError]       = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const load = () =>
    getDashboardStats()
      .then(d => { setData(d); setLastUpdated(new Date()); setError(null) })
      .catch(e => setError(e.message))

  useEffect(() => {
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [])

  if (!data && error) return <div className="error-msg">⚠️ Sunucuya bağlanılamıyor: {error}</div>
  if (!data)          return <div className="spinner" />

  const { orders, stock, cargo, tickets, recent_orders, latest_report } = data
  const statusKeys = Object.keys(orders.by_status)
  const maxStatus  = Math.max(...statusKeys.map(k => orders.by_status[k]), 1)

  return (
    <>
      <WelcomeBanner user={user} />

      {error && (
        <div style={{ background: 'rgba(239,68,68,.08)', border: '1px solid rgba(239,68,68,.25)', borderRadius: 'var(--radius)', padding: '8px 14px', marginBottom: 12, fontSize: 13, color: 'var(--danger)' }}>
          ⚠️ Sunucuya bağlanılamıyor — veriler yenilenemedi.
        </div>
      )}

      {/* AI Task Bar */}
      <AiTaskBar />

      {/* KPIs */}
      <div className="kpi-grid" style={{ marginTop: 16 }}>
        <KPICard icon="📦" label="Toplam Sipariş"  value={fmt(orders.total)}      sub={`${fmtMoney(orders.total_revenue)} gelir`} />
        <KPICard icon="⏳" label="Hazırlanıyor"    value={fmt(orders.pending)}    color="var(--warning)" sub="kargoya bekliyor" />
        <KPICard icon="🚚" label="Kargoda"          value={fmt(orders.in_cargo)}   color="var(--accent)"  sub={cargo.delayed_count > 0 ? `${cargo.delayed_count} gecikme` : 'sorunsuz'} />
        <KPICard icon="✅" label="Teslim Edildi"    value={fmt(orders.delivered)}  color="var(--success)" />
        <KPICard icon="⚠️" label="Kritik Stok"     value={fmt(stock.critical_count)} color={stock.critical_count > 0 ? 'var(--danger)' : 'var(--success)'} sub="eşik altında" />
        <KPICard icon="🎫" label="Açık Bilet"       value={fmt(tickets.open)} color={tickets.open > 0 ? 'var(--danger)' : 'var(--success)'} sub="insan incelemesi" />
      </div>

      <div className="grid-2" style={{ marginTop: 16 }}>
        {/* Satış grafiği */}
        <div className="card">
          <div className="card-title">📈 Son 7 Günlük Satışlar</div>
          <SalesChart />
        </div>

        {/* Sipariş dağılımı */}
        <div className="card">
          <div className="card-title">Sipariş Durumu Dağılımı</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {statusKeys.map(k => (
              <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <StatusBadge value={k} map={ORDER_STATUS} />
                <div style={{ flex: 1, height: 6, background: 'var(--surface2)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${(orders.by_status[k] / maxStatus) * 100}%`,
                    background: k === 'teslim_edildi' ? 'var(--success)'
                              : k === 'kargoda'       ? 'var(--accent)'
                              : k === 'hazırlanıyor'  ? 'var(--warning)'
                              : 'var(--danger)',
                    borderRadius: 3,
                    transition: 'width .6s ease',
                  }} />
                </div>
                <span style={{ color: 'var(--text2)', minWidth: 24, textAlign: 'right', fontSize: 13 }}>{orders.by_status[k]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 16 }}>
        {/* Son siparişler */}
        <div className="card">
          <div className="section-row" style={{ marginBottom: 12 }}>
            <div className="card-title" style={{ marginBottom: 0 }}>Son Siparişler</div>
            <Link to="/orders" style={{ fontSize: 12, color: 'var(--accent)' }}>Tümü →</Link>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>#</th><th>Müşteri</th><th>Durum</th><th>Tutar</th></tr>
              </thead>
              <tbody>
                {recent_orders.map(o => (
                  <tr key={o.id}>
                    <td style={{ color: 'var(--text3)' }}>#{o.id}</td>
                    <td>{o.customer_name}</td>
                    <td><StatusBadge value={o.status} map={ORDER_STATUS} /></td>
                    <td>{fmtMoney(o.total_price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Son biletler */}
        <div className="card">
          <div className="section-row" style={{ marginBottom: 12 }}>
            <div className="card-title" style={{ marginBottom: 0 }}>Son Biletler</div>
            <Link to="/tickets" style={{ fontSize: 12, color: 'var(--accent)' }}>Tümü →</Link>
          </div>
          {tickets.recent.length === 0 ? (
            <div style={{ color: 'var(--text3)', fontSize: 13 }}>Henüz bilet yok</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {tickets.recent.map(t => (
                <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                  <StatusBadge value={t.type} map={TICKET_TYPE} />
                  <span style={{ flex: 1, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.title}</span>
                  <StatusBadge value={t.status} map={TICKET_STATUS} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Kargo uyarıları */}
      {cargo.delayed.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="section-row" style={{ marginBottom: 12 }}>
            <div className="card-title" style={{ marginBottom: 0 }}>🚚 Geciken Kargolar</div>
            <Link to="/cargo" style={{ fontSize: 12, color: 'var(--accent)' }}>Kargo sayfası →</Link>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {cargo.delayed.slice(0, 5).map(c => (
              <div key={c.order_id} style={{ background: 'rgba(239,68,68,.07)', border: '1px solid rgba(239,68,68,.2)', borderRadius: 'var(--radius)', padding: '8px 12px' }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>Sipariş #{c.order_id} — {c.customer_name}</div>
                <div style={{ fontSize: 12, color: 'var(--text2)' }}>{c.cargo_tracking_code} · <span style={{ color: 'var(--danger)' }}>{c.current_status}</span></div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Kritik stok */}
      {stock.critical_count > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="section-row" style={{ marginBottom: 12 }}>
            <div className="card-title" style={{ marginBottom: 0 }}>⚠️ Kritik Stok</div>
            <Link to="/inventory" style={{ fontSize: 12, color: 'var(--accent)' }}>Stok yönetimi →</Link>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Ürün</th><th>Kategori</th><th>Mevcut</th><th>Eşik</th></tr></thead>
              <tbody>
                {stock.critical_products.map(p => (
                  <tr key={p.id}>
                    <td style={{ fontWeight: 500 }}>{p.name}</td>
                    <td style={{ color: 'var(--text2)' }}>{p.category || '—'}</td>
                    <td style={{ color: 'var(--danger)', fontWeight: 600 }}>{p.stock_quantity}</td>
                    <td style={{ color: 'var(--text3)' }}>{p.low_stock_threshold}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Son AI raporu */}
      {latest_report && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="section-row" style={{ marginBottom: 12 }}>
            <div className="card-title" style={{ marginBottom: 0 }}>📄 Son AI Raporu — {latest_report.date}</div>
            <Link to="/reports" style={{ fontSize: 12, color: 'var(--accent)' }}>Tüm raporlar →</Link>
          </div>
          <div style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.6, maxHeight: 140, overflow: 'hidden', position: 'relative' }}>
            {latest_report.report_text?.slice(0, 450)}…
            <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 36, background: 'linear-gradient(transparent, var(--surface))' }} />
          </div>
        </div>
      )}

      {lastUpdated && (
        <div style={{ fontSize: 11, color: 'var(--text3)', textAlign: 'right', marginTop: 12 }}>
          Son güncelleme: {lastUpdated.toLocaleTimeString('tr-TR')} · otomatik 30s
        </div>
      )}
    </>
  )
}
