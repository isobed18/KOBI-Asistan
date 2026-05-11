import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDashboardStats } from '../api.js'
import KPICard from '../components/KPICard.jsx'
import StatusBadge, { ORDER_STATUS, TICKET_STATUS, TICKET_TYPE, TICKET_PRIORITY } from '../components/StatusBadge.jsx'

function fmt(n) { return n?.toLocaleString('tr-TR') ?? '—' }
function fmtMoney(n) { return n != null ? `₺${n.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—' }

export default function Overview() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

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

  const totalOrders = orders.total
  const statusKeys = Object.keys(orders.by_status)
  const maxStatus = Math.max(...statusKeys.map(k => orders.by_status[k]), 1)

  return (
    <>
      {error && (
        <div style={{ background: 'rgba(239,68,68,.08)', border: '1px solid rgba(239,68,68,.25)', borderRadius: 'var(--radius)', padding: '8px 14px', marginBottom: 12, fontSize: 13, color: 'var(--danger)' }}>
          ⚠️ Sunucuya bağlanılamıyor — veriler yenilenemedi. Bağlantı geri geldiğinde otomatik güncellenir.
        </div>
      )}
      {lastUpdated && (
        <div style={{ fontSize: 11, color: 'var(--text3)', textAlign: 'right', marginBottom: 8 }}>
          Son güncelleme: {lastUpdated.toLocaleTimeString('tr-TR')} · otomatik 30s
        </div>
      )}
      {/* KPIs */}
      <div className="kpi-grid">
        <KPICard icon="📦" label="Toplam Sipariş" value={fmt(orders.total)} sub={`₺${fmt(orders.total_revenue)} gelir`} />
        <KPICard icon="⏳" label="Hazırlanıyor"   value={fmt(orders.pending)}   color="var(--warning)" sub="kargoya bekliyor" />
        <KPICard icon="🚚" label="Kargoda"         value={fmt(orders.in_cargo)}  color="var(--accent)"  sub={cargo.delayed_count > 0 ? `${cargo.delayed_count} gecikme var` : 'sorunsuz'} />
        <KPICard icon="✅" label="Teslim Edildi"   value={fmt(orders.delivered)} color="var(--success)" />
        <KPICard icon="⚠️" label="Kritik Stok"    value={fmt(stock.critical_count)} color={stock.critical_count > 0 ? 'var(--danger)' : 'var(--success)'} sub="ürün eşik altında" />
        <KPICard icon="🎫" label="Açık Bilet"      value={fmt(tickets.open)} color={tickets.open > 0 ? 'var(--danger)' : 'var(--success)'} sub="insan incelemesi" />
      </div>

      <div className="grid-2">
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
                    borderRadius: 3
                  }} />
                </div>
                <span style={{ color: 'var(--text2)', minWidth: 24, textAlign: 'right', fontSize: 13 }}>{orders.by_status[k]}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Kargo uyarıları */}
        <div className="card">
          <div className="card-title">🚚 Kargo Durumu</div>
          {cargo.delayed.length === 0 ? (
            <div style={{ color: 'var(--success)', fontSize: 13 }}>✅ Tüm kargolar sorunsuz</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {cargo.delayed.slice(0, 5).map(c => (
                <div key={c.order_id} style={{ background: 'rgba(239,68,68,.07)', border: '1px solid rgba(239,68,68,.2)', borderRadius: 'var(--radius)', padding: '8px 12px' }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>Sipariş #{c.order_id} — {c.customer_name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text2)' }}>{c.cargo_tracking_code} · <span style={{ color: 'var(--danger)' }}>{c.current_status}</span></div>
                </div>
              ))}
              {cargo.delayed.length > 5 && <Link to="/cargo" style={{ fontSize: 12, color: 'var(--accent)' }}>+{cargo.delayed.length - 5} daha → Kargo sayfası</Link>}
            </div>
          )}
        </div>
      </div>

      <div className="grid-2">
        {/* Son siparişler */}
        <div className="card">
          <div className="section-row" style={{ marginBottom: 12 }}>
            <div className="card-title" style={{ marginBottom: 0 }}>Son Siparişler</div>
            <Link to="/orders" style={{ fontSize: 12, color: 'var(--accent)' }}>Tümü →</Link>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Müşteri</th>
                  <th>Durum</th>
                  <th>Tutar</th>
                </tr>
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

      {/* Kritik stok */}
      {stock.critical_count > 0 && (
        <div className="card">
          <div className="section-row" style={{ marginBottom: 12 }}>
            <div className="card-title" style={{ marginBottom: 0 }}>⚠️ Kritik Stok Ürünleri</div>
            <Link to="/inventory" style={{ fontSize: 12, color: 'var(--accent)' }}>Stok yönetimi →</Link>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Ürün</th><th>Kategori</th><th>Mevcut</th><th>Eşik</th><th>Durum</th></tr></thead>
              <tbody>
                {stock.critical_products.map(p => (
                  <tr key={p.id}>
                    <td style={{ fontWeight: 500 }}>{p.name}</td>
                    <td style={{ color: 'var(--text2)' }}>{p.category || '—'}</td>
                    <td style={{ color: 'var(--danger)', fontWeight: 600 }}>{p.stock_quantity}</td>
                    <td style={{ color: 'var(--text3)' }}>{p.low_stock_threshold}</td>
                    <td><span className="badge badge-red">Kritik</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Latest AI report */}
      {latest_report && (
        <div className="card">
          <div className="section-row" style={{ marginBottom: 12 }}>
            <div className="card-title" style={{ marginBottom: 0 }}>📄 Son AI Raporu — {latest_report.date}</div>
            <Link to="/reports" style={{ fontSize: 12, color: 'var(--accent)' }}>Tüm raporlar →</Link>
          </div>
          <div style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.6, maxHeight: 160, overflow: 'hidden', position: 'relative' }}>
            {latest_report.report_text?.slice(0, 500)}…
            <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 40, background: 'linear-gradient(transparent, var(--surface))' }} />
          </div>
        </div>
      )}
    </>
  )
}
