import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getTickets, getTicketStats, updateTicketStatus } from '../api.js'
import StatusBadge, { TICKET_STATUS, TICKET_TYPE, TICKET_PRIORITY } from '../components/StatusBadge.jsx'
import {
  IconAiSparkles,
  IconBtnCheck,
  IconBtnPlay,
  IconBtnRefresh,
  IconEmptyTicket,
  IconSmallBox,
  IconSmallCalendar,
  IconSmallClipboard,
  IconSmallPackage,
  IconTabAlertCircle,
  IconTabCheckCircle,
  IconTabGrid,
  IconTabLoader,
} from '../components/DataListIcons.jsx'

function fmtDate(s) {
  return s ? new Date(s).toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
}

function LLMContent({ raw, type }) {
  const [expanded, setExpanded] = useState(false)
  if (!raw) return null

  let parsed = null
  try { parsed = JSON.parse(raw) } catch { /* raw string */ }

  return (
    <div>
      <button
        type="button"
        className="btn btn-ghost btn-sm ticket-ai-toggle"
        style={{ marginBottom: 6 }}
        onClick={() => setExpanded(e => !e)}
      >
        <span className="ticket-btn-icon" aria-hidden>
          <IconAiSparkles />
        </span>
        {expanded ? 'AI İçeriği Gizle' : 'AI İçeriğini Göster'}
      </button>
      {expanded && (
        <div className="ticket-llm">
          {parsed ? (
            type === 'cargo_delay' ? (
              <>
                {parsed.musteri_mesaji && (
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ fontWeight: 600, color: 'var(--accent)', marginBottom: 4 }}>Müşteri mesajı</div>
                    <div style={{ background: 'var(--surface)', padding: '8px 10px', borderRadius: 6 }}>
                      {parsed.musteri_mesaji}
                    </div>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      style={{ marginTop: 4 }}
                      onClick={() => navigator.clipboard.writeText(parsed.musteri_mesaji)}
                    >
                      <span className="ticket-btn-icon" aria-hidden>
                        <IconSmallClipboard />
                      </span>
                      Kopyala
                    </button>
                  </div>
                )}
                {parsed.ic_not && (
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--warning)', marginBottom: 4 }}>İç not</div>
                    <div>{parsed.ic_not}</div>
                  </div>
                )}
              </>
            ) : type === 'stock_alert' ? (
              <>
                {parsed.onerilen_miktar != null && (
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ fontWeight: 600, color: 'var(--success)', marginBottom: 4 }}>
                      Önerilen sipariş miktarı: {parsed.onerilen_miktar} adet
                    </div>
                  </div>
                )}
                {parsed.tedarikci_emaili && (
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--accent)', marginBottom: 4 }}>Tedarikçi e-postası taslağı</div>
                    <div style={{ background: 'var(--surface)', padding: '8px 10px', borderRadius: 6, whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 12 }}>
                      {parsed.tedarikci_emaili}
                    </div>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      style={{ marginTop: 4 }}
                      onClick={() => navigator.clipboard.writeText(parsed.tedarikci_emaili)}
                    >
                      <span className="ticket-btn-icon" aria-hidden>
                        <IconSmallClipboard />
                      </span>
                      Kopyala
                    </button>
                  </div>
                )}
              </>
            ) : (
              <pre style={{ fontSize: 12 }}>{JSON.stringify(parsed, null, 2)}</pre>
            )
          ) : (
            <div style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{raw}</div>
          )}
        </div>
      )}
    </div>
  )
}

const TICKET_TAB_KEYS = new Set(['open', 'in_progress', 'resolved', 'all'])

function readTicketTabFromSearchParams(sp) {
  const raw = (sp.get('tab') || '').trim()
  if (!raw) return 'all'
  return TICKET_TAB_KEYS.has(raw) ? raw : 'all'
}

function TicketCard({ ticket, onUpdated }) {
  const [loading, setLoading] = useState(false)

  const changeStatus = async (newStatus) => {
    setLoading(true)
    try {
      await updateTicketStatus(ticket.id, newStatus)
      onUpdated()
    } catch (e) {
      alert(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <article className={`ticket-card ticket-card--modern priority-${ticket.priority}`}>
      <div className="ticket-card-top">
        <div className="ticket-badges-row">
          <StatusBadge value={ticket.type} map={TICKET_TYPE} />
          <StatusBadge value={ticket.priority} map={TICKET_PRIORITY} />
          <StatusBadge value={ticket.status} map={TICKET_STATUS} />
        </div>
        <h3 className="ticket-title">{ticket.title}</h3>
      </div>

      <div className="ticket-meta ticket-meta--icons">
        <span className="ticket-meta-item">
          <span className="ticket-meta-icon" aria-hidden>#</span>
          Bilet {ticket.id}
        </span>
        <span className="ticket-meta-item">
          <span className="ticket-meta-icon" aria-hidden>
            <IconSmallCalendar />
          </span>
          {fmtDate(ticket.created_at)}
        </span>
        {ticket.related_order_id && (
          <span className="ticket-meta-item">
            <span className="ticket-meta-icon" aria-hidden>
              <IconSmallPackage />
            </span>
            Sipariş #{ticket.related_order_id}
          </span>
        )}
        {ticket.related_product_id && (
          <span className="ticket-meta-item">
            <span className="ticket-meta-icon" aria-hidden>
              <IconSmallBox />
            </span>
            Ürün #{ticket.related_product_id}
          </span>
        )}
        {ticket.resolved_at && (
          <span className="ticket-meta-item ticket-meta-item--success">
            <span className="ticket-meta-icon" aria-hidden>
              <IconTabCheckCircle />
            </span>
            Çözüldü: {fmtDate(ticket.resolved_at)}
          </span>
        )}
      </div>

      {ticket.description && <div className="ticket-desc">{ticket.description}</div>}

      <LLMContent raw={ticket.llm_content} type={ticket.type} />

      <div className="ticket-actions">
        {ticket.status === 'open' && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => changeStatus('in_progress')} disabled={loading}>
            <span className="ticket-btn-icon" aria-hidden>
              <IconBtnPlay />
            </span>
            İşleme Al
          </button>
        )}
        {ticket.status !== 'resolved' && (
          <button type="button" className="btn btn-success btn-sm" onClick={() => changeStatus('resolved')} disabled={loading}>
            <span className="ticket-btn-icon" aria-hidden>
              <IconBtnCheck />
            </span>
            Çözüldü
          </button>
        )}
        {ticket.status === 'resolved' && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => changeStatus('open')} disabled={loading}>
            <span className="ticket-btn-icon" aria-hidden>
              <IconBtnRefresh />
            </span>
            Yeniden Aç
          </button>
        )}
      </div>
    </article>
  )
}

const TYPE_FILTER_OPTIONS = [
  { value: 'cargo_delay', label: TICKET_TYPE.cargo_delay.label },
  { value: 'stock_alert', label: TICKET_TYPE.stock_alert.label },
  { value: 'cancellation_request', label: TICKET_TYPE.cancellation_request.label },
  { value: 'complaint', label: TICKET_TYPE.complaint.label },
  { value: 'refund_request', label: TICKET_TYPE.refund_request.label },
  { value: 'anomaly', label: TICKET_TYPE.anomaly.label },
  { value: 'other', label: TICKET_TYPE.other.label },
]

export default function Tickets() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = useMemo(() => readTicketTabFromSearchParams(searchParams), [searchParams])
  const setTab = useCallback(
    (key) => {
      const next = new URLSearchParams(searchParams)
      if (key === 'all') {
        next.delete('tab')
      } else {
        next.set('tab', key)
      }
      setSearchParams(next, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  const [tickets, setTickets] = useState([])
  const [ticketStats, setTicketStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [typeFilter, setTypeFilter] = useState('')

  const refreshStats = () => {
    getTicketStats().then(setTicketStats).catch(() => setTicketStats(null))
  }

  const load = () => {
    setLoading(true)
    refreshStats()
    const params = {}
    if (tab !== 'all') params.status = tab
    if (typeFilter) params.type = typeFilter
    getTickets(params)
      .then(d => { setTickets(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [tab, typeFilter])

  const byStatus = ticketStats?.by_status || {}
  const countOpen = Number(byStatus.open) || 0
  const countInProgress = Number(byStatus.in_progress) || 0
  const countResolved = Number(byStatus.resolved) || 0
  const countAll = ticketStats
    ? Object.values(byStatus).reduce((a, n) => a + (Number(n) || 0), 0)
    : 0

  return (
    <div className="tickets-page">
      <div className="card tickets-hero-card">
        <div className="card-title">Müdahale kayıtları</div>
        <p className="tickets-hero-lead">
          Kargo gecikmesi, kritik stok ve müşteri talepleri için açılan kayıtlar. Durum sekmeleri ve tip filtresi ile daraltın.
        </p>
      </div>

      <div className="card tickets-panel-card data-list-card">
        <div className="tickets-toolbar">
          <div className="tab-bar tickets-tab-bar" role="tablist" aria-label="Bilet durumu">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'all'}
              className={`tab-btn${tab === 'all' ? ' active' : ''}`}
              onClick={() => setTab('all')}
            >
              <span className="tab-btn-icon" aria-hidden>
                <IconTabGrid />
              </span>
              Tümü ({countAll})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'open'}
              className={`tab-btn${tab === 'open' ? ' active' : ''}`}
              onClick={() => setTab('open')}
            >
              <span className="tab-btn-icon ticket-tab-icon--open" aria-hidden>
                <IconTabAlertCircle />
              </span>
              Açık ({countOpen})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'in_progress'}
              className={`tab-btn${tab === 'in_progress' ? ' active' : ''}`}
              onClick={() => setTab('in_progress')}
            >
              <span className="tab-btn-icon ticket-tab-icon--progress" aria-hidden>
                <IconTabLoader />
              </span>
              İşlemde ({countInProgress})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'resolved'}
              className={`tab-btn${tab === 'resolved' ? ' active' : ''}`}
              onClick={() => setTab('resolved')}
            >
              <span className="tab-btn-icon ticket-tab-icon--resolved" aria-hidden>
                <IconTabCheckCircle />
              </span>
              Çözüldü ({countResolved})
            </button>
          </div>
          <div className="form-group tickets-type-filter">
            <label htmlFor="ticket-type-filter">Tip</label>
            <select id="ticket-type-filter" value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
              <option value="">Tüm tipler</option>
              {TYPE_FILTER_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        </div>

        {error && <div className="error-msg">⚠️ {error}</div>}

        {loading ? (
          <div className="spinner" />
        ) : tickets.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon empty-icon--svg" aria-hidden>
              <IconEmptyTicket />
            </div>
            {tab === 'open' ? 'Açık bilet yok — harika!' : 'Bu kategoride bilet yok'}
          </div>
        ) : (
          <div className="ticket-list">
            {tickets.map(t => (
              <TicketCard key={t.id} ticket={t} onUpdated={load} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
