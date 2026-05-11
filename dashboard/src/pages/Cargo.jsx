import { useEffect, useMemo, useState } from 'react'
import { getCargoDashboard, createTicketManual } from '../api.js'
import SortableTh from '../components/SortableTh.jsx'
import { cmpBool, cmpNullableStr, cmpNum, cmpTime } from '../utils/tableSort.js'

function fmtDate(s) {
  return s ? new Date(s).toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'
}

function StatusDot({ delayed }) {
  return delayed
    ? <><span className="dot dot-yellow" />Gecikmeli</>
    : <><span className="dot dot-green" />Aktif</>
}

export default function Cargo() {
  const [data, setData]         = useState(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [ticketMsg, setTicketMsg] = useState({})
  const [tab, setTab]           = useState('all')
  const [sortKey, setSortKey]   = useState('order_id')
  const [sortDir, setSortDir]   = useState('asc')

  const onSort = (key) => {
    if (key === sortKey) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const load = () => {
    setLoading(true)
    getCargoDashboard()
      .then(d => { setData(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const openTicket = async (shipment) => {
    setTicketMsg(prev => ({ ...prev, [shipment.order_id]: 'loading' }))
    try {
      await createTicketManual({
        type: 'cargo_delay',
        title: `Kargo Gecikmesi — Sipariş #${shipment.order_id} (${shipment.customer_name})`,
        description: `Sipariş #${shipment.order_id} kargo durumu: '${shipment.cargo_status}'. Kargo kodu: ${shipment.cargo_tracking_code}. Müşteri: ${shipment.customer_name}`,
        priority: 'high',
        related_order_id: shipment.order_id,
      })
      setTicketMsg(prev => ({ ...prev, [shipment.order_id]: 'ok' }))
    } catch (e) {
      setTicketMsg(prev => ({ ...prev, [shipment.order_id]: `hata: ${e.message}` }))
    }
  }

  const all     = data?.shipments ?? []
  const delayed = all.filter(s => s.is_delayed)
  const active  = all.filter(s => !s.is_delayed)
  const shown   = tab === 'delayed' ? delayed : tab === 'active' ? active : all

  const sorted = useMemo(() => {
    const rows = [...shown]
    const mult = sortDir === 'asc' ? 1 : -1
    rows.sort((a, b) => {
      let cmp = 0
      switch (sortKey) {
        case 'order_id':
          cmp = cmpNum(a.order_id, b.order_id)
          break
        case 'customer_name':
          cmp = cmpNullableStr(a.customer_name, b.customer_name)
          break
        case 'cargo_tracking_code':
          cmp = cmpNullableStr(a.cargo_tracking_code, b.cargo_tracking_code)
          break
        case 'cargo_company':
          cmp = cmpNullableStr(a.cargo_company, b.cargo_company)
          break
        case 'cargo_status':
          cmp = cmpNullableStr(a.cargo_status, b.cargo_status)
          break
        case 'estimated_delivery': {
          const ta = a?.estimated_delivery ? Date.parse(a.estimated_delivery) : NaN
          const tb = b?.estimated_delivery ? Date.parse(b.estimated_delivery) : NaN
          if (Number.isFinite(ta) && Number.isFinite(tb)) cmp = ta - tb
          else cmp = cmpNullableStr(a.estimated_delivery, b.estimated_delivery)
          break
        }
        case 'cargo_last_update':
          cmp = cmpTime(a.cargo_last_update, b.cargo_last_update)
          break
        case 'is_delayed':
          cmp = cmpBool(a.is_delayed, b.is_delayed)
          break
        default:
          cmp = cmpNum(a.order_id, b.order_id)
      }
      return mult * cmp
    })
    return rows
  }, [shown, sortKey, sortDir])

  if (error) return <div className="error-msg">⚠️ {error}</div>
  if (!data) return <div className="spinner" />

  return (
    <>
      {/* KPI bar */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-icon">🚚</div>
          <div className="kpi-label">Toplam Kargoda</div>
          <div className="kpi-value">{data.total}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-icon">✅</div>
          <div className="kpi-label">Sorunsuz</div>
          <div className="kpi-value" style={{ color: 'var(--success)' }}>{active.length}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-icon">⚠️</div>
          <div className="kpi-label">Gecikmeli</div>
          <div className="kpi-value" style={{ color: data.delayed_count > 0 ? 'var(--danger)' : 'var(--success)' }}>
            {data.delayed_count}
          </div>
          {data.delayed_count > 0 && <div className="kpi-sub">müdahale gerekebilir</div>}
        </div>
      </div>

      <div className="card">
        <div className="section-row" style={{ marginBottom: 12 }}>
          <div>
            <div className="tab-bar" style={{ marginBottom: 0, borderBottom: 'none' }}>
              <button className={`tab-btn${tab === 'all' ? ' active' : ''}`} onClick={() => setTab('all')}>
                Tümü ({all.length})
              </button>
              <button className={`tab-btn${tab === 'delayed' ? ' active' : ''}`} onClick={() => setTab('delayed')}>
                ⚠️ Gecikmeli ({delayed.length})
              </button>
              <button className={`tab-btn${tab === 'active' ? ' active' : ''}`} onClick={() => setTab('active')}>
                ✅ Sorunsuz ({active.length})
              </button>
            </div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={load}>🔄 Yenile</button>
        </div>

        {loading ? (
          <div className="spinner" />
        ) : sorted.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🚚</div>
            {tab === 'delayed' ? 'Gecikmeli kargo yok' : 'Kargoda sipariş yok'}
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <SortableTh columnKey="order_id" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>Sipariş</SortableTh>
                  <SortableTh columnKey="customer_name" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>Müşteri</SortableTh>
                  <SortableTh columnKey="cargo_tracking_code" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>Kargo Kodu</SortableTh>
                  <SortableTh columnKey="cargo_company" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>Firma</SortableTh>
                  <SortableTh columnKey="cargo_status" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>Kargo Durumu</SortableTh>
                  <SortableTh columnKey="estimated_delivery" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>Tahmini Teslimat</SortableTh>
                  <SortableTh columnKey="cargo_last_update" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>Son Güncelleme</SortableTh>
                  <SortableTh columnKey="is_delayed" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>Durum</SortableTh>
                  <th aria-label="İşlemler" />
                </tr>
              </thead>
              <tbody>
                {sorted.map(s => (
                  <tr key={s.order_id} style={s.is_delayed ? { background: 'rgba(239,68,68,.04)' } : {}}>
                    <td style={{ fontFamily: 'monospace', color: 'var(--text2)' }}>#{s.order_id}</td>
                    <td style={{ fontWeight: 500 }}>{s.customer_name}</td>
                    <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{s.cargo_tracking_code || '—'}</td>
                    <td style={{ color: 'var(--text2)' }}>{s.cargo_company || '—'}</td>
                    <td style={{ color: s.is_delayed ? 'var(--danger)' : 'var(--text2)', fontWeight: s.is_delayed ? 600 : 400 }}>
                      {s.cargo_status || '—'}
                    </td>
                    <td style={{ color: 'var(--text2)', fontSize: 12 }}>{s.estimated_delivery || '—'}</td>
                    <td style={{ color: 'var(--text3)', fontSize: 12 }}>{fmtDate(s.cargo_last_update)}</td>
                    <td>
                      <span style={{ display: 'inline-flex', alignItems: 'center', fontSize: 12 }}>
                        <StatusDot delayed={s.is_delayed} />
                      </span>
                    </td>
                    <td>
                      {s.is_delayed && (
                        ticketMsg[s.order_id] === 'ok' ? (
                          <span className="badge badge-green">✓ Bilet açıldı</span>
                        ) : ticketMsg[s.order_id] === 'loading' ? (
                          <span className="badge badge-gray">…</span>
                        ) : (
                          <button className="btn btn-danger btn-sm" onClick={() => openTicket(s)}>
                            🎫 Bilet Aç
                          </button>
                        )
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Bilgi kartı */}
      <div className="card" style={{ background: 'rgba(59,130,246,.05)', borderColor: 'rgba(59,130,246,.2)' }}>
        <div className="card-title" style={{ color: 'var(--accent)' }}>🤖 Otomatik Kargo Takibi</div>
        <p style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.6 }}>
          Sistem her <strong>4 saatte bir</strong> kargodaki tüm siparişleri tarar. Gecikme tespit edildiğinde
          LLM otomatik olarak müşteri bilgilendirme mesajı + iç operasyon notu üretir ve bir inceleme bileti açar.
          Açılan biletler <strong>Biletler</strong> sayfasında görünür; müşteri mesajı tek tıkla kopyalanabilir.
        </p>
      </div>
    </>
  )
}
