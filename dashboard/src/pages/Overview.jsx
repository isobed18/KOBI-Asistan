import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { generateAiTasks, getAnalytics, getDashboardStats, getSalesChart } from '../api.js'
import { useAuth } from '../context/AuthContext.jsx'

function fmt(n) { return n?.toLocaleString('tr-TR') ?? '-' }
function money(n) {
  return n != null ? `₺${n.toLocaleString('tr-TR', { maximumFractionDigits: 0 })}` : '-'
}

const variants = {
  enter: { opacity: 0, y: 14, scale: 0.985 },
  center: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: -10, scale: 0.99 },
}

function Sparkline({ days = [] }) {
  const W = 760
  const H = 190
  const PAD = 18
  const max = Math.max(...days.map(d => d.revenue), 1)
  const step = (W - PAD * 2) / Math.max(days.length - 1, 1)
  const pts = days.map((d, i) => [PAD + i * step, H - PAD - (d.revenue / max) * (H - PAD * 2)])
  const line = pts.map(([x, y]) => `${x},${y}`).join(' ')
  const area = `${PAD},${H - PAD} ${line} ${W - PAD},${H - PAD}`
  return (
    <div className="guided-chart">
      <svg viewBox={`0 0 ${W} ${H}`}>
        <defs>
          <linearGradient id="guidedFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity=".2" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={area} fill="url(#guidedFill)" />
        <polyline points={line} fill="none" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        {pts.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="4" fill="var(--accent)" />)}
      </svg>
      <div className="guided-chart-labels">
        {days.map(d => <span key={d.day}>{d.day.slice(5)}</span>)}
      </div>
    </div>
  )
}

function StepShell({ children, step, setStep, totalSteps }) {
  return (
    <div className="guided-shell">
      <div className="guided-progress">
        {Array.from({ length: totalSteps }).map((_, i) => (
          <button
            key={i}
            className={`guided-dot${i === step ? ' active' : ''}${i < step ? ' done' : ''}`}
            onClick={() => setStep(i)}
            aria-label={`Adim ${i + 1}`}
          />
        ))}
      </div>
      <AnimatePresence mode="wait">
        <motion.section
          key={step}
          variants={variants}
          initial="enter"
          animate="center"
          exit="exit"
          transition={{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
        >
          {children}
        </motion.section>
      </AnimatePresence>
      <div className="guided-nav">
        <button className="guided-nav-btn" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}>
          Geri
        </button>
        <button className="guided-nav-btn primary" onClick={() => setStep(Math.min(totalSteps - 1, step + 1))}>
          {step === totalSteps - 1 ? 'Akisi Basa Al' : 'Sonraki'}
        </button>
      </div>
    </div>
  )
}

function WelcomeStep({ user, tenant }) {
  const business = tenant?.business_name || user?.tenant?.business_name || 'Isletmeniz'
  const name = user?.full_name || user?.username || 'Mehmet Bey'
  return (
    <div className="guided-welcome">
      <span className="guided-kicker">Otomasyon merkezi hazir</span>
      <h1>Hos geldiniz, {name}.</h1>
      <p>
        {business} bugun arka planda izleniyor. Size tum veriyi yigmiyorum; sadece karar vermeniz
        gereken anlari adim adim gosteriyorum.
      </p>
      <div className="guided-calm-line">
        <span className="guided-live" /> Sistem siparis, stok, kargo ve musteri taleplerini izliyor.
      </div>
    </div>
  )
}

function TodayStep({ stats, chart, latestReport }) {
  const days = chart?.days || []
  const today = days[days.length - 1]
  const yesterday = days[days.length - 2]
  const change = yesterday?.revenue ? Math.round(((today.revenue - yesterday.revenue) / yesterday.revenue) * 100) : 0
  const cards = [
    { label: 'Bugunku satis', value: money(today?.revenue || 0), sub: `${change >= 0 ? '+' : ''}${change}% dune gore` },
    { label: 'Gelen siparis', value: fmt(today?.order_count || 0), sub: `${fmt(stats.orders.total)} toplam kayit` },
    { label: 'Hazirlanacak', value: fmt(stats.orders.pending), sub: 'paket bekliyor' },
    { label: 'Acil sinyal', value: fmt(stats.stock.critical_count + stats.cargo.delayed_count + stats.tickets.open), sub: 'mudahale gerekebilir' },
  ]
  return (
    <div className="guided-step-grid">
      <div className="guided-main-card">
        <span className="guided-kicker">Bugun</span>
        <h2>11 Mayis 2026</h2>
        <div className="guided-metric-grid">
          {cards.map(c => (
            <div className="guided-metric" key={c.label}>
              <span>{c.label}</span>
              <strong>{c.value}</strong>
              <small>{c.sub}</small>
            </div>
          ))}
        </div>
        <Sparkline days={days} />
      </div>
      <aside className="guided-brief-card">
        <span className="guided-kicker">AI brifingi</span>
        <p>{latestReport?.report_text?.replace(/[#*_`]/g, '').slice(0, 520) || 'Bugunku rapor henuz uretilmedi. Sistem yine operasyon sinyallerini izliyor.'}</p>
        <Link to="/reports" className="guided-link">Raporlara git →</Link>
      </aside>
    </div>
  )
}

function OrdersStep({ stats }) {
  const orders = stats.recent_orders || []
  return (
    <div className="guided-main-card">
      <span className="guided-kicker">Hazirlanacak isler</span>
      <h2>Paketler ve operasyon akisiniz</h2>
      <p className="guided-muted">Once hazirlanacak siparisler, sonra kargo riski. Sistem musteri sormadan once sizi uyarir.</p>
      <div className="guided-list">
        {orders.slice(0, 5).map(o => (
          <Link key={o.id} to="/orders" className="guided-row">
            <div>
              <strong>Siparis #{o.id} · {o.customer_name}</strong>
              <span>{o.status} · {money(o.total_price)}</span>
            </div>
            <small>Detay →</small>
          </Link>
        ))}
      </div>
    </div>
  )
}

function ApprovalStep({ stats, analytics }) {
  const tickets = stats.tickets.recent || []
  const large = analytics?.large_orders || []
  const repeat = analytics?.repeat_customers || []
  return (
    <div className="guided-step-grid">
      <div className="guided-main-card">
        <span className="guided-kicker">Onay bekleyenler</span>
        <h2>Sadece karar gerektiren konular</h2>
        <div className="guided-list">
          {tickets.length === 0 && large.length === 0 ? (
            <div className="guided-empty">Bugun onay bekleyen kritik konu yok.</div>
          ) : (
            <>
              {tickets.slice(0, 4).map(t => (
                <Link key={t.id} to="/tickets" className="guided-row urgent">
                  <div><strong>{t.title}</strong><span>{t.type} · {t.priority}</span></div>
                  <small>Incele →</small>
                </Link>
              ))}
              {large.slice(0, 3).map(o => (
                <Link key={o.id} to="/orders" className="guided-row">
                  <div><strong>Yuklu siparis #{o.id}</strong><span>{o.customer_name} · {o.total_items} adet · {money(o.total_price)}</span></div>
                  <small>Onayla →</small>
                </Link>
              ))}
            </>
          )}
        </div>
      </div>
      <aside className="guided-brief-card">
        <span className="guided-kicker">Musteri sinyali</span>
        {repeat.length === 0 ? (
          <p>Sadakat veya tekrar eden musteri sinyali henuz belirgin degil.</p>
        ) : (
          repeat.slice(0, 3).map(c => (
            <div className="guided-mini-customer" key={c.customer_phone}>
              <strong>{c.customer_name}</strong>
              <span>{c.order_count} siparis · {money(c.revenue)}</span>
            </div>
          ))
        )}
      </aside>
    </div>
  )
}

function ActionsStep({ aiTasks }) {
  const tasks = aiTasks?.tasks || []
  return (
    <div className="guided-main-card">
      <span className="guided-kicker">AI aksiyonlari</span>
      <h2>Uygulama bugun bunlari oneriyor</h2>
      <p className="guided-muted">{aiTasks?.briefing || 'Oncelikli gorevler hazirlaniyor.'}</p>
      <div className="guided-list">
        {tasks.length === 0 ? (
          <div className="guided-empty">Sistem izliyor; su an acil aksiyon yok.</div>
        ) : tasks.map(t => (
          <div key={t.id} className={`guided-action priority-${t.priority || 'normal'}`}>
            <div>
              <strong>{t.title}</strong>
              <span>{t.body}</span>
            </div>
            <div className="guided-action-buttons">
              <Link to={t.link || '/assistant'} className="guided-action-primary">Incele</Link>
              <button>Ertele</button>
            </div>
          </div>
        ))}
      </div>
      <div className="guided-final-actions">
        <Link to="/assistant" className="guided-big-link">AI Asistan ile islem yap</Link>
        <Link to="/tickets" className="guided-big-link muted">Mudahale paneli</Link>
      </div>
    </div>
  )
}

export default function Overview() {
  const { user } = useAuth()
  const [step, setStep] = useState(0)
  const [stats, setStats] = useState(null)
  const [chart, setChart] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [aiTasks, setAiTasks] = useState(null)
  const [error, setError] = useState(null)

  const load = () => {
    Promise.all([getDashboardStats(), getSalesChart(), getAnalytics()])
      .then(([s, c, a]) => {
        setStats(s)
        setChart(c)
        setAnalytics(a)
        setError(null)
      })
      .catch(e => setError(e.message))

    generateAiTasks()
      .then(setAiTasks)
      .catch(() => setAiTasks({
        briefing: 'AI gorevleri su an hazirlanamadi; operasyon verileri izleniyor.',
        tasks: [],
      }))
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [])

  const steps = useMemo(() => {
    if (!stats) return []
    return [
      <WelcomeStep user={user} tenant={stats.tenant} />,
      <TodayStep stats={stats} chart={chart} latestReport={stats.latest_report} />,
      <OrdersStep stats={stats} />,
      <ApprovalStep stats={stats} analytics={analytics} />,
      <ActionsStep aiTasks={aiTasks} />,
    ]
  }, [stats, chart, analytics, aiTasks, user])

  if (!stats && error) return <div className="error-msg">Sunucuya baglanilamiyor: {error}</div>
  if (!stats) return <div className="guided-loading">Isletmeniz hazirlaniyor<span /><span /><span /></div>

  return (
    <div className="guided-page">
      {error && <div className="guided-soft-error">Veriler yenilenemedi; son bilinen durum gosteriliyor.</div>}
      <StepShell step={step} setStep={setStep} totalSteps={steps.length}>
        {steps[step]}
      </StepShell>
    </div>
  )
}
