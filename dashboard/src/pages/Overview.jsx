import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDashboardStats, getSalesChart, generateAiTasks, getAnalytics } from '../api.js'
import { useAuth } from '../context/AuthContext.jsx'

function fmt(n) { return n?.toLocaleString('tr-TR') ?? '-' }
function fmtMoney(n) {
  return n != null
    ? `₺${n.toLocaleString('tr-TR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
    : '-'
}

function MiniSparkline({ days = [] }) {
  if (!days.length) return <div className="mini-chart-empty">Veri bekleniyor</div>
  const W = 620
  const H = 150
  const PAD = 16
  const max = Math.max(...days.map(d => d.revenue), 1)
  const step = (W - PAD * 2) / Math.max(days.length - 1, 1)
  const points = days.map((d, i) => [
    PAD + i * step,
    H - PAD - ((d.revenue / max) * (H - PAD * 2)),
  ])
  const line = points.map(([x, y]) => `${x},${y}`).join(' ')
  const area = `${PAD},${H - PAD} ${line} ${W - PAD},${H - PAD}`
  return (
    <div className="command-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Son 7 gun satis grafigi">
        <defs>
          <linearGradient id="command-chart-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.24" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <polygon points={area} fill="url(#command-chart-fill)" />
        <polyline points={line} fill="none" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        {points.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="4" fill="var(--accent)" />)}
      </svg>
      <div className="command-chart-days">
        {days.map(d => <span key={d.day}>{d.day.slice(5)}</span>)}
      </div>
    </div>
  )
}

function WelcomeHero({ tenant, user, stats }) {
  const name = user?.full_name || user?.username || 'Yonetici'
  const business = tenant?.business_name || user?.tenant?.business_name || 'Isletmeniz'
  const risks = (stats?.stock?.critical_count || 0) + (stats?.cargo?.delayed_count || 0) + (stats?.tickets?.open || 0)
  const mood = risks === 0 ? 'Her sey yolunda.' : `${risks} konu ilginizi bekliyor.`

  return (
    <section className="command-hero">
      <div className="command-hero-copy">
        <div className="command-eyebrow">Otomasyon merkezi</div>
        <h1>Hos geldiniz, {name}.</h1>
        <p>
          {business} bugun sistem tarafindan izleniyor. Siparis, stok, kargo ve musteri taleplerinde
          sadece mudahale gerektiren konulari one cikariyorum.
        </p>
      </div>
      <div className="command-pulse-card">
        <span className="pulse-dot" />
        <div>
          <strong>{mood}</strong>
          <small>30 saniyede bir otomatik yenilenir</small>
        </div>
      </div>
    </section>
  )
}

function AiTasksPanel() {
  const [state, setState] = useState('loading')
  const [payload, setPayload] = useState(null)
  const [dismissed, setDismissed] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('dismissed_tasks') || '[]') } catch { return [] }
  })

  const load = () => {
    setState('loading')
    generateAiTasks()
      .then(r => { setPayload(r); setState('ready') })
      .catch(() => setState('error'))
  }

  useEffect(() => { load() }, [])

  const tasks = (payload?.tasks || []).filter(t => !dismissed.includes(t.id))
  const dismiss = (id) => {
    const next = [...dismissed, id]
    setDismissed(next)
    sessionStorage.setItem('dismissed_tasks', JSON.stringify(next))
  }

  return (
    <section className="command-panel command-panel-primary">
      <div className="command-panel-head">
        <div>
          <span className="command-panel-kicker">AI yapilacaklar</span>
          <h2>Bugun sistemi ne yonetiyor?</h2>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={load}>Yenile</button>
      </div>

      {state === 'loading' && (
        <div className="command-loading">
          <span /><span /><span />
          <b>AI oncelikleri hazirlaniyor</b>
        </div>
      )}

      {state === 'error' && (
        <div className="command-soft-alert">AI gorevleri yuklenemedi. Dashboard verileri yine izleniyor.</div>
      )}

      {state === 'ready' && (
        <>
          <p className="command-brief">{payload?.briefing || 'Bugun icin oncelikli konular hazir.'}</p>
          {tasks.length === 0 ? (
            <div className="command-done">Oncelikli acil aksiyon yok. Sistem izlemeye devam ediyor.</div>
          ) : (
            <div className="command-task-list">
              {tasks.map(task => (
                <article key={task.id} className={`command-task priority-${task.priority || 'normal'}`}>
                  <div className="command-task-icon">{task.icon || '•'}</div>
                  <div className="command-task-body">
                    <h3>{task.title}</h3>
                    <p>{task.body}</p>
                  </div>
                  <div className="command-task-actions">
                    <Link className="btn btn-primary btn-sm" to={task.link || '/assistant'}>Incele</Link>
                    <button className="btn btn-ghost btn-sm" onClick={() => dismiss(task.id)}>Ertele</button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}

function MetricStrip({ stats }) {
  const items = [
    { label: 'Siparis', value: fmt(stats.orders.total), sub: fmtMoney(stats.orders.total_revenue) },
    { label: 'Hazirlanacak', value: fmt(stats.orders.pending), sub: 'paket' },
    { label: 'Riskli kargo', value: fmt(stats.cargo.delayed_count), sub: 'musteri beklemeden' },
    { label: 'Kritik stok', value: fmt(stats.stock.critical_count), sub: 'yenileme' },
    { label: 'Acil bilet', value: fmt(stats.tickets.open), sub: 'insan onayi' },
  ]
  return (
    <div className="command-metrics">
      {items.map(item => (
        <div key={item.label} className="command-metric">
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          <small>{item.sub}</small>
        </div>
      ))}
    </div>
  )
}

function AttentionPanel({ stats, analytics }) {
  const signals = [
    ...(analytics?.risk_signals || []),
    ...((stats.stock.critical_products || []).slice(0, 3).map(p => ({
      title: `${p.name} yenileme bekliyor`,
      body: `Stok ${p.stock_quantity}, esik ${p.low_stock_threshold}.`,
      priority: 'high',
      link: '/inventory',
    }))),
    ...((stats.cargo.delayed || []).slice(0, 2).map(c => ({
      title: `Siparis #${c.id || c.order_id} kargo riski`,
      body: `${c.customer_name} sikayet etmeden bilgilendirilebilir.`,
      priority: 'high',
      link: '/cargo',
    }))),
  ].slice(0, 6)

  return (
    <section className="command-panel">
      <div className="command-panel-head">
        <div>
          <span className="command-panel-kicker">Dikkat isteyenler</span>
          <h2>Sadece mudahale gereken konular</h2>
        </div>
      </div>
      {signals.length === 0 ? (
        <div className="command-done">Bugun icin kritik sinyal yok.</div>
      ) : (
        <div className="attention-list">
          {signals.map((s, i) => (
            <Link key={`${s.title}-${i}`} to={s.link || '/tickets'} className={`attention-item priority-${s.priority || 'normal'}`}>
              <div>
                <strong>{s.title}</strong>
                <span>{s.body}</span>
              </div>
              <small>Incele →</small>
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}

function InsightPanel({ analytics }) {
  const top = analytics?.top_products || []
  const customers = analytics?.repeat_customers || []
  return (
    <section className="command-panel">
      <div className="command-panel-head">
        <div>
          <span className="command-panel-kicker">IcGoru ve analiz</span>
          <h2>Satis ve musteri sinyalleri</h2>
        </div>
        <Link className="btn btn-ghost btn-sm" to="/reports">Raporlar</Link>
      </div>
      <div className="insight-grid">
        <div>
          <h3>En hareketli urunler</h3>
          {top.slice(0, 4).map(p => (
            <div key={p.id} className="insight-row">
              <span>{p.name}</span>
              <strong>{p.sold_qty} adet</strong>
            </div>
          ))}
        </div>
        <div>
          <h3>Tekrar eden musteriler</h3>
          {customers.length === 0 ? (
            <p className="muted">Henuz tekrar eden musteri sinyali yok.</p>
          ) : customers.slice(0, 4).map(c => (
            <div key={c.customer_phone} className="insight-row">
              <span>{c.customer_name}</span>
              <strong>{c.order_count} siparis</strong>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default function Overview() {
  const { user } = useAuth()
  const [stats, setStats] = useState(null)
  const [chart, setChart] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const load = () => {
    Promise.all([getDashboardStats(), getSalesChart(), getAnalytics()])
      .then(([s, c, a]) => {
        setStats(s)
        setChart(c)
        setAnalytics(a)
        setLastUpdated(new Date())
        setError(null)
      })
      .catch(e => setError(e.message))
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [])

  const total7 = useMemo(
    () => chart?.days?.reduce((sum, d) => sum + d.revenue, 0) || 0,
    [chart],
  )

  if (!stats && error) return <div className="error-msg">Sunucuya baglanilamiyor: {error}</div>
  if (!stats) return <div className="spinner" />

  return (
    <div className="command-center">
      {error && <div className="command-soft-alert">Veriler yenilenemedi; son bilinen durum gosteriliyor.</div>}

      <WelcomeHero tenant={stats.tenant} user={user} stats={stats} />
      <MetricStrip stats={stats} />

      <div className="command-main-grid">
        <div className="command-main-column">
          <AiTasksPanel />
          <AttentionPanel stats={stats} analytics={analytics} />
        </div>
        <aside className="command-side-column">
          <section className="command-panel">
            <div className="command-panel-head">
              <div>
                <span className="command-panel-kicker">Son 7 gun</span>
                <h2>{fmtMoney(total7)} satis</h2>
              </div>
            </div>
            <MiniSparkline days={chart?.days || []} />
          </section>
          <InsightPanel analytics={analytics} />
        </aside>
      </div>

      {stats.latest_report && (
        <section className="command-panel command-report-strip">
          <div>
            <span className="command-panel-kicker">AI sabah brifingi</span>
            <p>{stats.latest_report.report_text?.replace(/[#*_`]/g, '').slice(0, 260)}...</p>
          </div>
          <Link className="btn btn-primary btn-sm" to="/reports">Tam rapor</Link>
        </section>
      )}

      {lastUpdated && (
        <div className="command-updated">Son guncelleme: {lastUpdated.toLocaleTimeString('tr-TR')} · sistem izliyor</div>
      )}
    </div>
  )
}
