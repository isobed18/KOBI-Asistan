import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { getReports, getReport, generateReport } from '../api.js'

function fmtDateTime(s) {
  return s
    ? new Date(s).toLocaleString('tr-TR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—'
}

function fmtTime(s) {
  return s
    ? new Date(s).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })
    : ''
}

/** ISO date string YYYY-MM-DD → okunaklı Türkçe gün */
function fmtReportDay(isoDate) {
  if (!isoDate) return '—'
  const d = new Date(`${isoDate}T12:00:00`)
  return d.toLocaleDateString('tr-TR', {
    weekday: 'short',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

function IconSparkles(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z" />
      <path d="M20 3v4" />
      <path d="M22 5h-4" />
      <path d="M4 17v2" />
      <path d="M5 18H3" />
    </svg>
  )
}

function IconLoader(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="reports-icon-spin" aria-hidden="true" {...props}>
      <path d="M12 2v4" />
      <path d="m16.2 7.8 2.9-2.9" />
      <path d="M18 12h4" />
      <path d="m16.2 16.2 2.9 2.9" />
      <path d="M12 18v4" />
      <path d="m4.9 19.1 2.9-2.9" />
      <path d="M2 12h4" />
      <path d="m4.9 4.9 2.9 2.9" />
    </svg>
  )
}

function IconCalendar(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M8 2v4" />
      <path d="M16 2v4" />
      <rect width="18" height="18" x="3" y="4" rx="2" />
      <path d="M3 10h18" />
    </svg>
  )
}

function IconFileText(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
      <path d="M14 2v4a2 2 0 0 0 2 2h4" />
      <path d="M10 9H8" />
      <path d="M16 13H8" />
      <path d="M16 17H8" />
    </svg>
  )
}

function IconClipboard(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect width="8" height="4" x="8" y="2" rx="1" ry="1" />
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
    </svg>
  )
}

function IconAlertCircle(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4" />
      <path d="M12 8h.01" />
    </svg>
  )
}

function IconChevron(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="m9 18 6-6-6-6" />
    </svg>
  )
}

function IconCheck(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  )
}

function ReportMarkdown({ text }) {
  if (!text?.trim()) return null
  return (
    <div className="reports-markdown">
      <ReactMarkdown
        components={{
          a: ({ children, href, ...rest }) => {
            if (href?.startsWith('/')) {
              return (
                <Link to={href} {...rest}>
                  {children}
                </Link>
              )
            }
            return (
              <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
                {children}
              </a>
            )
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

export default function Reports() {
  const [reports, setReports] = useState([])
  const [selected, setSelected] = useState(null)
  const [selectedFull, setSelectedFull] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState(null)
  const [genResult, setGenResult] = useState(null)

  const dateDupCount = useMemo(() => {
    const m = new Map()
    for (const r of reports) {
      m.set(r.date, (m.get(r.date) || 0) + 1)
    }
    return m
  }, [reports])

  const load = () => {
    setLoading(true)
    getReports()
      .then(d => {
        setReports(d)
        setError(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  const openReport = async id => {
    setSelected(id)
    setSelectedFull(null)
    try {
      const r = await getReport(id)
      setSelectedFull(r)
    } catch (e) {
      setSelectedFull({ error: e.message })
    }
  }

  const generate = async () => {
    setGenerating(true)
    setGenResult(null)
    try {
      const r = await generateReport()
      setGenResult({ ok: true, text: `Rapor #${r.report_id} oluşturuldu.` })
      load()
      setSelected(r.report_id)
      setSelectedFull({
        id: r.report_id,
        report_id: r.report_id,
        date: r.date,
        created_at: new Date().toISOString(),
        report_text: r.report_text,
      })
    } catch (e) {
      setGenResult({ ok: false, text: e.message })
    } finally {
      setGenerating(false)
    }
  }

  const reportId = selectedFull && (selectedFull.report_id ?? selectedFull.id)

  return (
    <>
      <div className="card reports-hero-card">
        <div className="reports-hero">
          <div className="reports-hero-copy">
            <div className="reports-hero-kicker">Günlük özet</div>
            <h1 className="reports-hero-title">AI destekli günlük raporlar</h1>
            <p className="reports-hero-lead">
              Sipariş, stok ve kargo verileri analiz edilerek yönetici özeti formatında Türkçe rapor üretilir.
              Sabah 08:00&apos;de otomatik oluşturulur veya aşağıdan manuel tetiklenebilir.
            </p>
          </div>
          <button type="button" className="btn btn-primary reports-hero-btn" onClick={generate} disabled={generating}>
            {generating ? <IconLoader /> : <IconSparkles />}
            <span>{generating ? 'Oluşturuluyor…' : 'Rapor oluştur'}</span>
          </button>
        </div>
        {genResult && (
          <div className={genResult.ok ? 'success-msg reports-feedback' : 'error-msg reports-feedback'}>
            {genResult.ok ? <IconCheck /> : <IconAlertCircle />}
            <span>{genResult.text}</span>
          </div>
        )}
        {generating && (
          <div className="reports-gen-hint">
            <IconLoader />
            <span>Model yanıtı hazırlanıyor; genelde 10–30 saniye sürer.</span>
          </div>
        )}
      </div>

      <div className="card">
        <div className="reports-split">
          <aside className="reports-list-col">
            <div className="reports-list-heading">Geçmiş raporlar</div>

            {error && (
              <div className="error-msg reports-inline-alert">
                <IconAlertCircle />
                <span>{error}</span>
              </div>
            )}

            {loading ? (
              <div className="spinner" />
            ) : reports.length === 0 ? (
              <div className="reports-empty">
                <IconFileText className="reports-empty-icon" />
                <p className="reports-empty-text">Henüz kayıtlı rapor yok. Üstteki düğmeyle ilk raporu oluşturun.</p>
              </div>
            ) : (
              <ul className="reports-date-list">
                {reports.map(r => {
                  const showTime = (dateDupCount.get(r.date) || 0) > 1
                  return (
                    <li key={r.id}>
                      <button
                        type="button"
                        className="reports-date-row"
                        data-selected={selected === r.id ? 'true' : 'false'}
                        onClick={() => openReport(r.id)}
                      >
                        <span className="reports-date-row-icon">
                          <IconCalendar />
                        </span>
                        <span className="reports-date-row-text">
                          <span className="reports-date-row-primary">{fmtReportDay(r.date)}</span>
                          {showTime ? (
                            <span className="reports-date-row-meta">{fmtTime(r.created_at)}</span>
                          ) : null}
                        </span>
                        <IconChevron className="reports-date-row-chevron" />
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </aside>

          <div className="reports-detail-col">
            {selected == null ? (
              <div className="reports-detail-placeholder">
                <IconFileText className="reports-detail-placeholder-svg" />
                <div className="reports-detail-placeholder-hint">Listeden bir rapor seçin</div>
              </div>
            ) : !selectedFull ? (
              <div className="spinner" />
            ) : selectedFull.error ? (
              <div className="error-msg reports-inline-alert">
                <IconAlertCircle />
                <span>{selectedFull.error}</span>
              </div>
            ) : (
              <div className="reports-detail-inner">
                <div className="reports-detail-head">
                  <div className="reports-detail-head-text">
                    <div className="reports-detail-id">Rapor #{reportId}</div>
                    <div className="reports-detail-meta">
                      {fmtReportDay(selectedFull.date)} · {fmtDateTime(selectedFull.created_at)}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm reports-copy-btn"
                    onClick={() => navigator.clipboard.writeText(selectedFull.report_text || '')}
                  >
                    <IconClipboard />
                    <span>Kopyala</span>
                  </button>
                </div>
                <div className="reports-markdown-scroll">
                  <ReportMarkdown text={selectedFull.report_text} />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
