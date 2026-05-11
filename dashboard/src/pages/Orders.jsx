import { useEffect, useState } from 'react'
import { getOrders, updateOrderStatus } from '../api.js'
import StatusBadge, { ORDER_STATUS } from '../components/StatusBadge.jsx'

const STATUSES = ['', 'hazırlanıyor', 'kargoda', 'teslim_edildi', 'iptal']

function fmtMoney(n) { return n != null ? `₺${n.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}` : '—' }
function fmtDate(s)  { return s ? new Date(s).toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—' }

function OrderDetailDrawer({ order, onClose, onUpdated }) {
  const [newStatus, setNewStatus]     = useState(order.status)
  const [cargoCode, setCargoCode]     = useState(order.cargo_tracking_code || '')
  const [cargoCompany, setCargoCompany] = useState(order.cargo_company || '')
  const [loading, setLoading]         = useState(false)
  const [msg, setMsg]                 = useState(null)

  const save = async () => {
    setLoading(true)
    setMsg(null)
    try {
      await updateOrderStatus(order.id, {
        status: newStatus,
        cargo_tracking_code: cargoCode || null,
        cargo_company: cargoCompany || null,
      })
      setMsg({ ok: true, text: 'Güncellendi.' })
      onUpdated()
    } catch (e) {
      setMsg({ ok: false, text: e.message })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.6)', zIndex: 100,
      display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end',
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        width: 420, background: 'var(--surface)', height: '100%', borderLeft: '1px solid var(--border)',
        overflow: 'auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16,
      }}>
        <div className="section-row">
          <div style={{ fontWeight: 700, fontSize: 16 }}>Sipariş #{order.id}</div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕ Kapat</button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {[
            ['Müşteri', order.customer_name],
            ['Telefon', order.customer_phone || '—'],
            ['Takip Kodu', order.tracking_code || '—'],
            ['Toplam', fmtMoney(order.total_price)],
            ['Tarih', fmtDate(order.created_at)],
            ['Güncelleme', fmtDate(order.updated_at)],
          ].map(([k, v]) => (
            <div key={k}>
              <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 2 }}>{k}</div>
              <div style={{ fontSize: 13, fontWeight: 500 }}>{v}</div>
            </div>
          ))}
        </div>

        {order.notes && (
          <div style={{ background: 'var(--surface2)', borderRadius: 'var(--radius)', padding: '8px 12px', fontSize: 13 }}>
            <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 4 }}>Not</div>
            {order.notes}
          </div>
        )}

        {/* Ürünler */}
        <div>
          <div className="card-title">Ürünler</div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '4px 0', fontSize: 11, color: 'var(--text3)' }}>Ürün</th>
                <th style={{ textAlign: 'right', padding: '4px 0', fontSize: 11, color: 'var(--text3)' }}>Adet</th>
                <th style={{ textAlign: 'right', padding: '4px 0', fontSize: 11, color: 'var(--text3)' }}>Birim</th>
              </tr>
            </thead>
            <tbody>
              {(order.items || []).map((it, i) => (
                <tr key={i}>
                  <td style={{ padding: '4px 0', fontSize: 13 }}>{it.product_name}</td>
                  <td style={{ textAlign: 'right', fontSize: 13 }}>{it.quantity}</td>
                  <td style={{ textAlign: 'right', fontSize: 13 }}>{fmtMoney(it.unit_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Durum güncelleme */}
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div className="card-title">Durum Güncelle</div>
          <div className="form-group">
            <label>Yeni Durum</label>
            <select value={newStatus} onChange={e => setNewStatus(e.target.value)}>
              {STATUSES.slice(1).map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          {(newStatus === 'kargoda' || cargoCode) && (
            <>
              <div className="form-group">
                <label>Kargo Takip Kodu</label>
                <input value={cargoCode} onChange={e => setCargoCode(e.target.value)} placeholder="örn. KRG-ABC123" />
              </div>
              <div className="form-group">
                <label>Kargo Firması</label>
                <input value={cargoCompany} onChange={e => setCargoCompany(e.target.value)} placeholder="örn. Aras Kargo" />
              </div>
            </>
          )}
          {msg && <div className={msg.ok ? 'success-msg' : 'error-msg'}>{msg.text}</div>}
          <button className="btn btn-primary" onClick={save} disabled={loading}>
            {loading ? 'Kaydediliyor…' : '💾 Kaydet'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Orders() {
  const [orders, setOrders]       = useState([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch]       = useState('')
  const [selected, setSelected]   = useState(null)

  const load = (params = {}) => {
    setLoading(true)
    getOrders(params)
      .then(d => { setOrders(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    const params = {}
    if (statusFilter) params.status = statusFilter
    load(params)
  }, [statusFilter])

  const filtered = search
    ? orders.filter(o =>
        o.customer_name?.toLowerCase().includes(search.toLowerCase()) ||
        String(o.id).includes(search) ||
        o.tracking_code?.toLowerCase().includes(search.toLowerCase())
      )
    : orders

  return (
    <>
      {selected && (
        <OrderDetailDrawer
          order={selected}
          onClose={() => setSelected(null)}
          onUpdated={() => { setSelected(null); load(statusFilter ? { status: statusFilter } : {}) }}
        />
      )}

      <div className="card">
        <div className="form-row" style={{ marginBottom: 0 }}>
          <div className="form-group" style={{ flex: 1 }}>
            <label>Ara (müşteri, takip kodu, ID)</label>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Müşteri adı veya sipariş no…"
            />
          </div>
          <div className="form-group">
            <label>Durum Filtresi</label>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
              {STATUSES.map(s => <option key={s} value={s}>{s || 'Tüm Durumlar'}</option>)}
            </select>
          </div>
          <button className="btn btn-ghost" onClick={() => load(statusFilter ? { status: statusFilter } : {})}>
            🔄 Yenile
          </button>
        </div>
      </div>

      {error && <div className="error-msg">⚠️ {error}</div>}

      <div className="card">
        {loading ? (
          <div className="spinner" />
        ) : filtered.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📦</div>
            Sipariş bulunamadı
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Müşteri</th>
                  <th>Telefon</th>
                  <th>Durum</th>
                  <th>Kargo</th>
                  <th>Tutar</th>
                  <th>Tarih</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(o => (
                  <tr key={o.id}>
                    <td style={{ color: 'var(--text3)', fontFamily: 'monospace' }}>#{o.id}</td>
                    <td style={{ fontWeight: 500 }}>{o.customer_name}</td>
                    <td style={{ color: 'var(--text2)' }}>{o.customer_phone || '—'}</td>
                    <td><StatusBadge value={o.status} map={ORDER_STATUS} /></td>
                    <td style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--text2)' }}>
                      {o.cargo_tracking_code
                        ? `${o.cargo_tracking_code} (${o.cargo_company || '?'})`
                        : <span style={{ color: 'var(--text3)' }}>—</span>}
                    </td>
                    <td style={{ fontWeight: 500 }}>
                      {o.total_price != null ? `₺${o.total_price.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}` : '—'}
                    </td>
                    <td style={{ color: 'var(--text3)', fontSize: 12 }}>{fmtDate(o.created_at)}</td>
                    <td>
                      <button className="btn btn-ghost btn-sm" onClick={() => setSelected(o)}>
                        Detay →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
