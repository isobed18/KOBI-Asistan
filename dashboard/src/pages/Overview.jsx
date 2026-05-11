import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { generateAiTasks, getAnalytics, getDashboardStats, getSalesChart } from '../api.js'
import { useAuth } from '../context/AuthContext.jsx'

function fmt(n) { return n?.toLocaleString('tr-TR') ?? '-' }
function money(n) {
  return n != null ? `₺${n.toLocaleString('tr-TR', { maximumFractionDigits: 0 })}` : '-'
}

/** Eşik altı stokta ne kadar "boşluk" kaldığını 0–100 skorlar; görsel öncelik için. */
function stockCriticality(qty, threshold) {
  const th = Math.max(Number(threshold) || 0, 0)
  const q = Math.max(Number(qty) || 0, 0)
  if (th === 0) {
    if (q <= 0) return { score: 100, label: 'Acil', band: 'critical' }
    return { score: 35, label: 'Eşik yok', band: 'mid' }
  }
  if (q > th) return { score: 0, label: '—', band: 'ok' }
  const score = Math.round((1 - q / th) * 100)
  if (q === 0) return { score: 100, label: 'Tükendi', band: 'critical' }
  if (score >= 80) return { score, label: 'Çok kritik', band: 'critical' }
  if (score >= 55) return { score, label: 'Kritik', band: 'high' }
  if (score >= 30) return { score, label: 'Riskli', band: 'mid' }
  if (score > 0) return { score, label: 'Düşük Riskli', band: 'low' }
  return { score: 0, label: 'Eşikte', band: 'edge' }
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
  const revenues = days.map(d => Number(d.revenue) || 0)
  const minR = revenues.length ? Math.min(...revenues) : 0
  const maxR = revenues.length ? Math.max(...revenues) : 0
  // Sıfırdan max'a değil min–max aralığına oturt: benzer ciro günlerinde çizgi yine hareket eder
  const span = Math.max(maxR - minR, maxR * 0.12, 1)
  const yNorm = rev => (Math.max(0, Number(rev) || 0) - minR) / span
  const step = (W - PAD * 2) / Math.max(days.length - 1, 1)
  const pts = days.map((d, i) => [PAD + i * step, H - PAD - yNorm(d.revenue) * (H - PAD * 2)])
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
        {days.map((d, i) => (
          <span key={d.day} title={`${d.day}: ${money(d.revenue)} · ${fmt(d.order_count)} sipariş`}>
            {days.length > 10 && i % 2 === 1 ? '' : d.day.slice(5)}
          </span>
        ))}
      </div>
    </div>
  )
}

function IconChevronLeft(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <polyline points="15 18 9 12 15 6" />
    </svg>
  )
}

function IconChevronRight(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <polyline points="9 18 15 12 9 6" />
    </svg>
  )
}

function StepShell({ children, step, setStep, totalSteps }) {
  const isLast = step === totalSteps - 1
  const goNext = () => {
    if (isLast) setStep(0)
    else setStep(step + 1)
  }

  return (
    <div className="guided-shell">
      <div className="guided-progress">
        {Array.from({ length: totalSteps }).map((_, i) => (
          <button
            key={i}
            className={`guided-dot${i === step ? ' active' : ''}${i < step ? ' done' : ''}`}
            onClick={() => setStep(i)}
            aria-label={`Adım ${i + 1}`}
          />
        ))}
      </div>
      <div className="guided-carousel-wrap">
        <button
          type="button"
          className="guided-step-chevron guided-step-chevron-prev"
          onClick={() => setStep(Math.max(0, step - 1))}
          disabled={step === 0}
          aria-label="Önceki adım"
        >
          <IconChevronLeft />
        </button>
        <div className="guided-carousel-stage">
          <AnimatePresence mode="wait">
            <motion.section
              key={step}
              className="guided-carousel-panel"
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
            >
              {children}
            </motion.section>
          </AnimatePresence>
        </div>
        <button
          type="button"
          className="guided-step-chevron guided-step-chevron-next"
          onClick={goNext}
          aria-label={isLast ? 'Akışı baştan başlat' : 'Sonraki adım'}
        >
          <IconChevronRight />
        </button>
      </div>
    </div>
  )
}

function WelcomeStep({ user, tenant }) {
  const business = tenant?.business_name || user?.tenant?.business_name || 'İşletmeniz'
  const name = user?.full_name || user?.username || 'Mehmet Bey'
  return (
    <div className="guided-welcome">
      <span className="guided-kicker">Otomasyon merkezi hazır</span>
      <h1>Hoş geldin, {name}.</h1>
      <p>
        Veriyi tablo tablo
        üstünüze yıkmıyor; yalnızca müdahale etmeniz gereken anları sırayla, sade bir akışla
        önünüze getiriyorum.
      </p>
      <div className="guided-calm-line">
        <span className="guided-live" /> Sipariş, stok, kargo ve müşteri talepleri senin için sürekli
        taranıyor.
      </div>
    </div>
  )
}

function TodayStep({ stats, chart, latestReport }) {
  const days = chart?.days || []
  const today = days[days.length - 1]
  const yesterday = days[days.length - 2]
  const change = yesterday?.revenue ? Math.round(((today.revenue - yesterday.revenue) / yesterday.revenue) * 100) : 0
  const reportDateStr = latestReport?.date
    ? new Date(`${latestReport.date}T12:00:00`).toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })
    : new Date().toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })
  const lb = stats?.live_briefing
  const briefingParagraphs = Array.isArray(lb?.paragraphs) && lb.paragraphs.length ? lb.paragraphs : null
  const briefingHeadline = latestReport?.briefing?.headlines?.[0]
  const legacyBriefingBody = briefingHeadline
    ? `${briefingHeadline}${latestReport?.briefing?.headlines?.[1] ? ` ${latestReport.briefing.headlines[1]}` : ''}`
    : (latestReport?.report_text?.replace(/[#*_`]/g, '').slice(0, 520) || 'Bugünkü rapor henüz üretilmedi. Sistem yine operasyon sinyallerini izliyor.')
  const cards = [
    { label: 'Bugünkü satış', value: money(today?.revenue || 0), sub: `${change >= 0 ? '+' : ''}${change}% düne göre` },
    { label: 'Gelen sipariş', value: fmt(today?.order_count || 0), sub: `${fmt(stats.orders.total)} toplam kayıt` },
    { label: 'Hazırlanacak', value: fmt(stats.orders.pending), sub: 'paket bekliyor' },
    { label: 'Acil sinyal', value: fmt(stats.stock.critical_count + stats.cargo.delayed_count + stats.tickets.open), sub: 'müdahale gerekebilir' },
  ]
  return (
    <div className="guided-step-grid">
      <div className="guided-main-card">
        <span className="guided-kicker">Günün özeti</span>
        <h2>{reportDateStr}</h2>
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
        {briefingParagraphs ? (
          <>
            {briefingParagraphs.map((t, i) => (
              <p key={i} className={i === 0 ? 'guided-brief-lead' : undefined}>{t}</p>
            ))}
            <p className="guided-brief-meta">
              Anlık veri · {lb.as_of_date}
              {latestReport?.date && latestReport.date !== lb.as_of_date ? ` · Son LLM raporu: ${latestReport.date}` : ''}
            </p>
          </>
        ) : (
          <p>{legacyBriefingBody}</p>
        )}
        <Link to="/reports" className="guided-link">Raporlara git →</Link>
      </aside>
    </div>
  )
}

const CRITICAL_STOCK_OVERVIEW_CAP = 80

function OrdersStep({ stats }) {
  const criticalProducts = stats.stock?.critical_products || []
  const totalCritical = stats.stock?.critical_count ?? criticalProducts.length

  const rankedStock = [...criticalProducts]
    .map((p) => ({ ...p, _crit: stockCriticality(p.stock_quantity, p.low_stock_threshold) }))
    .filter((p) => p._crit.band !== 'ok')
    .sort((a, b) => b._crit.score - a._crit.score || a.stock_quantity - b.stock_quantity)
    .slice(0, CRITICAL_STOCK_OVERVIEW_CAP)

  return (
    <div className="guided-main-card guided-stock-step">
      <span className="guided-kicker">Kritik stok</span>
      <h2>
        {totalCritical
          ? `${fmt(totalCritical)} ürünün stoğu kritik durumda`
          : 'Stoğu kritik durumda ürün yok'}
      </h2>
      <p className="guided-muted guided-stock-step-lead">
        Çubuk ve skor, stoğun eşiğe göre ne kadar geride olduğunu gösterir (yüksek = daha acil).
        {totalCritical > rankedStock.length ? ` Öncelik sırasıyla ilk ${fmt(rankedStock.length)} ürün; tamamı için envanter.` : ''}
      </p>
      {rankedStock.length === 0 ? (
        <div className="guided-empty guided-stock-empty">Tüm ürünler eşik üstünde veya yeterli tamponda.</div>
      ) : (
        <ul className="guided-stock-list">
          {rankedStock.map((p) => {
            const { score, label, band } = p._crit
            const barW = Math.min(100, Math.max(band === 'edge' ? 10 : 14, score))
            return (
              <li key={p.id} className="guided-stock-item">
                <div className="guided-stock-item-top">
                  <div className="guided-stock-item-name">
                    <strong>{p.name}</strong>
                    {p.category ? <span className="guided-stock-cat">{p.category}</span> : null}
                  </div>
                  <span className={`guided-severity-pill guided-severity-pill--${band}`}>{label}</span>
                </div>
                <div className="guided-stock-item-meta">
                  <span>{fmt(p.stock_quantity)} adet</span>
                  <span className="guided-stock-meta-sep">·</span>
                  <span>eşik {fmt(p.low_stock_threshold)}</span>
                  <span className="guided-stock-meta-sep">·</span>
                  <span className="guided-stock-score" title="Eşiğe göre risk skoru">skor {score}</span>
                </div>
                <div className="guided-severity-track" role="presentation">
                  <div
                    className="guided-severity-fill"
                    data-band={band}
                    style={{ width: `${barW}%` }}
                  />
                </div>
              </li>
            )
          })}
        </ul>
      )}
      <Link to="/inventory" className="guided-link">Stok envanterine git →</Link>
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
            <div className="guided-empty">Bugün onay bekleyen kritik konu yok.</div>
          ) : (
            <>
              {tickets.slice(0, 4).map(t => (
                <Link key={t.id} to="/tickets" className="guided-row urgent">
                  <div><strong>{t.title}</strong><span>{t.type} · {t.priority}</span></div>
                  <small>İncele →</small>
                </Link>
              ))}
              {large.slice(0, 3).map(o => (
                <Link key={o.id} to="/orders" className="guided-row">
                  <div><strong>Yüklü sipariş #{o.id}</strong><span>{o.customer_name} · {o.total_items} adet · {money(o.total_price)}</span></div>
                  <small>Onayla →</small>
                </Link>
              ))}
            </>
          )}
        </div>
      </div>
      <aside className="guided-brief-card">
        <span className="guided-kicker">Müşteri sinyali</span>
        {repeat.length === 0 ? (
          <p>Sadakat veya tekrar eden müşteri sinyali henüz belirgin değil.</p>
        ) : (
          repeat.slice(0, 3).map(c => (
            <div className="guided-mini-customer" key={c.customer_phone}>
              <strong>{c.customer_name}</strong>
              <span>{c.order_count} sipariş · {money(c.revenue)}</span>
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
      <span className="guided-kicker">AI aksiyonları</span>
      <h2>Uygulama bugün bunları öneriyor</h2>
      <p className="guided-muted">{aiTasks?.briefing || 'Öncelikli görevler hazırlanıyor.'}</p>
      <div className="guided-list">
        {tasks.length === 0 ? (
          <div className="guided-empty">Sistem izliyor; şu an acil aksiyon yok.</div>
        ) : tasks.map(t => (
          <div key={t.id} className={`guided-action priority-${t.priority || 'normal'}`}>
            <div>
              <strong>{t.title}</strong>
              <span>{t.body}</span>
            </div>
            <div className="guided-action-buttons">
              <Link to={t.link || '/assistant'} className="guided-action-primary">İncele</Link>
              <button>Ertele</button>
            </div>
          </div>
        ))}
      </div>
      <div className="guided-final-actions">
        <Link to="/assistant" className="guided-big-link">AI Asistan ile işlem yap</Link>
        <Link to="/tickets" className="guided-big-link muted">Müdahale paneli</Link>
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
    Promise.all([getDashboardStats(), getSalesChart(14), getAnalytics()])
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
        briefing: 'AI görevleri şu an hazırlanamadı; operasyon verileri izleniyor.',
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

  if (!stats && error) return <div className="error-msg">Sunucuya bağlanılamıyor: {error}</div>
  if (!stats) return <div className="guided-loading">İşletmeniz hazırlanıyor<span /><span /><span /></div>

  return (
    <div className="guided-page">
      {error && <div className="guided-soft-error">Veriler yenilenemedi; son bilinen durum gösteriliyor.</div>}
      <StepShell step={step} setStep={setStep} totalSteps={steps.length}>
        {steps[step]}
      </StepShell>
    </div>
  )
}
