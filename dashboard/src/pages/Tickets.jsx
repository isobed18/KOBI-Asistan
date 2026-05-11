import { useEffect, useState } from 'react'
import { getTickets, updateTicketStatus } from '../api.js'
import StatusBadge, { TICKET_STATUS, TICKET_TYPE, TICKET_PRIORITY } from '../components/StatusBadge.jsx'

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
        className="btn btn-ghost btn-sm"
        style={{ marginBottom: 6 }}
        onClick={() => setExpanded(e => !e)}
      >
        🤖 {expanded ? 'AI İçeriği Gizle' : 'AI İçeriğini Göster'}
      </button>
      {expanded && (
        <div className="ticket-llm">
          {parsed ? (
            type === 'cargo_delay' ? (
              <>
                {parsed.musteri_mesaji && (
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ fontWeight: 600, color: 'var(--accent)', marginBottom: 4 }}>📱 Müşteri Mesajı</div>
                    <div style={{ background: 'var(--surface)', padding: '8px 10px', borderRadius: 6 }}>
                      {parsed.musteri_mesaji}
                    </div>
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ marginTop: 4 }}
                      onClick={() => navigator.clipboard.writeText(parsed.musteri_mesaji)}
                    >📋 Kopyala</button>
                  </div>
                )}
                {parsed.ic_not && (
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--warning)', marginBottom: 4 }}>📋 İç Not</div>
                    <div>{parsed.ic_not}</div>
                  </div>
                )}
              </>
            ) : type === 'stock_alert' ? (
              <>
                {parsed.onerilen_miktar != null && (
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ fontWeight: 600, color: 'var(--success)', marginBottom: 4 }}>
                      📦 Önerilen Sipariş Miktarı: {parsed.onerilen_miktar} adet
                    </div>
                  </div>
                )}
                {parsed.tedarikci_emaili && (
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--accent)', marginBottom: 4 }}>✉️ Tedarikçi E-postası Taslağı</div>
                    <div style={{ background: 'var(--surface)', padding: '8px 10px', borderRadius: 6, whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 12 }}>
                      {parsed.tedarikci_emaili}
                    </div>
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ marginTop: 4 }}
                      onClick={() => navigator.clipboard.writeText(parsed.tedarikci_emaili)}
                    >📋 Kopyala</button>
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
    <div className={`ticket-card priority-${ticket.priority}`}>
      <div className="ticket-header">
        <div>
          <StatusBadge value={ticket.type} map={TICKET_TYPE} />
        </div>
        <div className="ticket-title">{ticket.title}</div>
        <StatusBadge value={ticket.priority} map={TICKET_PRIORITY} />
        <StatusBadge value={ticket.status} map={TICKET_STATUS} />
      </div>

      <div className="ticket-meta">
        <span>Bilet #{ticket.id}</span>
        <span>📅 {fmtDate(ticket.created_at)}</span>
        {ticket.related_order_id && <span>📦 Sipariş #{ticket.related_order_id}</span>}
        {ticket.related_product_id && <span>🗂️ Ürün #{ticket.related_product_id}</span>}
        {ticket.resolved_at && <span>✅ Çözüldü: {fmtDate(ticket.resolved_at)}</span>}
      </div>

      {ticket.description && <div className="ticket-desc">{ticket.description}</div>}

      <LLMContent raw={ticket.llm_content} type={ticket.type} />

      <div className="ticket-actions">
        {ticket.status === 'open' && (
          <button className="btn btn-ghost btn-sm" onClick={() => changeStatus('in_progress')} disabled={loading}>
            ▶️ İşleme Al
          </button>
        )}
        {ticket.status !== 'resolved' && (
          <button className="btn btn-success btn-sm" onClick={() => changeStatus('resolved')} disabled={loading}>
            ✅ Çözüldü
          </button>
        )}
        {ticket.status === 'resolved' && (
          <button className="btn btn-ghost btn-sm" onClick={() => changeStatus('open')} disabled={loading}>
            🔄 Yeniden Aç
          </button>
        )}
      </div>
    </div>
  )
}

export default function Tickets() {
  const [tickets, setTickets]   = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [tab, setTab]           = useState('open')
  const [typeFilter, setTypeFilter] = useState('')

  const load = () => {
    setLoading(true)
    const params = {}
    if (tab !== 'all') params.status = tab
    if (typeFilter)    params.type   = typeFilter
    getTickets(params)
      .then(d => { setTickets(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [tab, typeFilter])

  const openCount       = tickets.filter(t => t.status === 'open').length
  const inProgressCount = tickets.filter(t => t.status === 'in_progress').length

  return (
    <>
      <div className="form-row">
        <div className="form-group">
          <label>Tip Filtresi</label>
          <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
            <option value="">Tüm Tipler</option>
            <option value="cargo_delay">🚚 Kargo Gecikmesi</option>
            <option value="stock_alert">📦 Stok Uyarısı</option>
            <option value="cancellation_request">❌ İptal Talebi</option>
            <option value="complaint">⚠️ Şikayet</option>
            <option value="refund_request">💰 İade Talebi</option>
            <option value="anomaly">🔍 Anomali</option>
            <option value="other">Diğer</option>
          </select>
        </div>
        <button className="btn btn-ghost" style={{ alignSelf: 'flex-end' }} onClick={load}>🔄 Yenile</button>
      </div>

      <div className="tab-bar">
        <button className={`tab-btn${tab === 'open' ? ' active' : ''}`} onClick={() => setTab('open')}>
          🔴 Açık
        </button>
        <button className={`tab-btn${tab === 'in_progress' ? ' active' : ''}`} onClick={() => setTab('in_progress')}>
          🟡 İşlemde
        </button>
        <button className={`tab-btn${tab === 'resolved' ? ' active' : ''}`} onClick={() => setTab('resolved')}>
          🟢 Çözüldü
        </button>
        <button className={`tab-btn${tab === 'all' ? ' active' : ''}`} onClick={() => setTab('all')}>
          Tümü
        </button>
      </div>

      {error && <div className="error-msg">⚠️ {error}</div>}

      {loading ? (
        <div className="spinner" />
      ) : tickets.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🎫</div>
          {tab === 'open' ? 'Açık bilet yok — harika!' : 'Bu kategoride bilet yok'}
        </div>
      ) : (
        <div className="ticket-list">
          {tickets.map(t => (
            <TicketCard key={t.id} ticket={t} onUpdated={load} />
          ))}
        </div>
      )}

      {/* Bilgi kartı */}
      <div className="card" style={{ background: 'rgba(59,130,246,.05)', borderColor: 'rgba(59,130,246,.2)' }}>
        <div className="card-title" style={{ color: 'var(--accent)' }}>🤖 AI Destekli Bilet Sistemi</div>
        <p style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.6 }}>
          Biletler üç yoldan otomatik oluşturulur: <strong>(1)</strong> Müşteri chat'te sipariş iptali veya
          şikayet bildirdiğinde AI agent <code>create_ticket</code> aracını çağırır.
          <strong> (2)</strong> Kargo gecikmesi tespit edildiğinde LLM müşteri mesajı + iç not üretir.
          <strong> (3)</strong> Kritik stok uyarısında LLM sipariş miktarı önerisi + tedarikçi e-postası hazırlar.
          AI içeriği "AI İçeriğini Göster" butonu ile tek tıkla görüntülenip kopyalanabilir.
        </p>
      </div>
    </>
  )
}
