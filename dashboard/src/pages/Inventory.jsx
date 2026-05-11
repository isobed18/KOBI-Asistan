import { useEffect, useState } from 'react'
import { getProducts, updateStock, getStockMovements } from '../api.js'

function StockBar({ qty, threshold }) {
  const max  = Math.max(threshold * 5, qty, 1)
  const pct  = Math.min((qty / max) * 100, 100)
  const color = qty === 0          ? 'var(--danger)'
              : qty <= threshold   ? 'var(--warning)'
              : pct < 60           ? 'var(--accent)'
              : 'var(--success)'
  return (
    <div className="stock-bar-wrap">
      <div className="stock-bar-bg">
        <div className="stock-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="stock-pct">{qty}</span>
    </div>
  )
}

function StockModal({ product, onClose, onUpdated }) {
  const [delta, setDelta]       = useState('')
  const [reason, setReason]     = useState('')
  const [loading, setLoading]   = useState(false)
  const [msg, setMsg]           = useState(null)
  const [movements, setMovements] = useState(null)
  const [tab, setTab]           = useState('update')

  useEffect(() => {
    if (tab === 'history') {
      getStockMovements(product.id, 20).then(setMovements).catch(() => setMovements([]))
    }
  }, [tab, product.id])

  const save = async () => {
    const n = parseInt(delta, 10)
    if (isNaN(n) || n === 0) { setMsg({ ok: false, text: 'Geçerli bir miktar girin.' }); return }
    setLoading(true)
    setMsg(null)
    try {
      await updateStock(product.id, { quantity_change: n, reason: reason || null })
      setMsg({ ok: true, text: `Stok güncellendi. Yeni: ${product.stock_quantity + n}` })
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
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)',
        padding: 24, width: 420, maxHeight: '80vh', display: 'flex', flexDirection: 'column', gap: 14,
      }}>
        <div className="section-row">
          <div style={{ fontWeight: 700, fontSize: 15 }}>{product.name}</div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
        <div style={{ fontSize: 13, color: 'var(--text2)' }}>
          Mevcut: <strong style={{ color: 'var(--text)' }}>{product.stock_quantity}</strong> · Eşik: {product.low_stock_threshold}
        </div>
        <div className="tab-bar" style={{ marginBottom: 0 }}>
          <button className={`tab-btn${tab === 'update' ? ' active' : ''}`} onClick={() => setTab('update')}>Güncelle</button>
          <button className={`tab-btn${tab === 'history' ? ' active' : ''}`} onClick={() => setTab('history')}>📋 Geçmiş</button>
        </div>

        {tab === 'update' ? (
          <>
            <div className="form-group">
              <label>Miktar Değişimi (+ ekle, - çıkar)</label>
              <input
                type="number"
                value={delta}
                onChange={e => setDelta(e.target.value)}
                placeholder="örn. +50 veya -10"
              />
            </div>
            <div className="form-group">
              <label>Neden (opsiyonel)</label>
              <input value={reason} onChange={e => setReason(e.target.value)} placeholder="örn. Yeni sevkiyat" />
            </div>
            <div className="form-row">
              <button className="btn btn-ghost btn-sm" onClick={() => setDelta(String(product.low_stock_threshold * 3))}>
                +{product.low_stock_threshold * 3} (önerilen)
              </button>
            </div>
            {msg && <div className={msg.ok ? 'success-msg' : 'error-msg'}>{msg.text}</div>}
            <button className="btn btn-primary" onClick={save} disabled={loading}>
              {loading ? 'Kaydediliyor…' : '💾 Güncelle'}
            </button>
          </>
        ) : (
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {movements === null ? (
              <div className="spinner" />
            ) : movements.length === 0 ? (
              <div style={{ fontSize: 13, color: 'var(--text3)' }}>Henüz hareket kaydı yok.</div>
            ) : (
              <table style={{ width: '100%', fontSize: 12 }}>
                <thead>
                  <tr>
                    <th>Tarih</th>
                    <th>Delta</th>
                    <th>Neden</th>
                    <th>Önce→Sonra</th>
                  </tr>
                </thead>
                <tbody>
                  {movements.map(m => (
                    <tr key={m.id}>
                      <td style={{ color: 'var(--text3)' }}>{m.created_at?.slice(0, 16)}</td>
                      <td style={{ color: m.delta > 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
                        {m.delta > 0 ? '+' : ''}{m.delta}
                      </td>
                      <td>{m.reason}</td>
                      <td style={{ color: 'var(--text2)' }}>{m.before_qty}→{m.after_qty}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Inventory() {
  const [products, setProducts] = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [search, setSearch]     = useState('')
  const [tab, setTab]           = useState('all')
  const [modal, setModal]       = useState(null)

  const load = () => {
    setLoading(true)
    getProducts()
      .then(d => { setProducts(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const byTab = tab === 'critical'
    ? products.filter(p => p.is_low_stock)
    : tab === 'ok'
    ? products.filter(p => !p.is_low_stock)
    : products

  const filtered = search
    ? byTab.filter(p => p.name.toLowerCase().includes(search.toLowerCase()) || (p.category || '').toLowerCase().includes(search.toLowerCase()))
    : byTab

  const criticalCount = products.filter(p => p.is_low_stock).length

  return (
    <>
      {modal && (
        <StockModal
          product={modal}
          onClose={() => setModal(null)}
          onUpdated={() => { setModal(null); load() }}
        />
      )}

      {/* KPI */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-icon">🗂️</div>
          <div className="kpi-label">Toplam Ürün</div>
          <div className="kpi-value">{products.length}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-icon">⚠️</div>
          <div className="kpi-label">Kritik Stok</div>
          <div className="kpi-value" style={{ color: criticalCount > 0 ? 'var(--danger)' : 'var(--success)' }}>
            {criticalCount}
          </div>
          <div className="kpi-sub">eşik altında</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-icon">✅</div>
          <div className="kpi-label">Yeterli Stok</div>
          <div className="kpi-value" style={{ color: 'var(--success)' }}>{products.length - criticalCount}</div>
        </div>
      </div>

      <div className="card">
        <div className="form-row" style={{ marginBottom: 0 }}>
          <div className="form-group" style={{ flex: 1 }}>
            <label>Ürün Ara</label>
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Ürün adı veya kategori…" />
          </div>
          <button className="btn btn-ghost" onClick={load}>🔄 Yenile</button>
        </div>
      </div>

      <div className="card">
        <div className="tab-bar">
          <button className={`tab-btn${tab === 'all' ? ' active' : ''}`} onClick={() => setTab('all')}>
            Tümü ({products.length})
          </button>
          <button className={`tab-btn${tab === 'critical' ? ' active' : ''}`} onClick={() => setTab('critical')}>
            ⚠️ Kritik ({criticalCount})
          </button>
          <button className={`tab-btn${tab === 'ok' ? ' active' : ''}`} onClick={() => setTab('ok')}>
            ✅ Yeterli ({products.length - criticalCount})
          </button>
        </div>

        {loading ? (
          <div className="spinner" />
        ) : error ? (
          <div className="error-msg">⚠️ {error}</div>
        ) : filtered.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🗂️</div>
            Ürün bulunamadı
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Ürün</th>
                  <th>Kategori</th>
                  <th>Fiyat</th>
                  <th>Stok Seviyesi</th>
                  <th>Eşik</th>
                  <th>Durum</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(p => (
                  <tr key={p.id}>
                    <td style={{ color: 'var(--text3)' }}>{p.id}</td>
                    <td style={{ fontWeight: 500 }}>{p.name}</td>
                    <td style={{ color: 'var(--text2)' }}>{p.category || '—'}</td>
                    <td>₺{p.price?.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</td>
                    <td style={{ minWidth: 140 }}>
                      <StockBar qty={p.stock_quantity} threshold={p.low_stock_threshold} />
                    </td>
                    <td style={{ color: 'var(--text3)' }}>{p.low_stock_threshold}</td>
                    <td>
                      {p.stock_quantity === 0 ? (
                        <span className="badge badge-red">Tükendi</span>
                      ) : p.is_low_stock ? (
                        <span className="badge badge-yellow">Kritik</span>
                      ) : (
                        <span className="badge badge-green">Yeterli</span>
                      )}
                    </td>
                    <td>
                      <button className="btn btn-ghost btn-sm" onClick={() => setModal(p)}>
                        📝 Stok Güncelle
                      </button>
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
        <div className="card-title" style={{ color: 'var(--accent)' }}>🤖 Otomatik Stok Takibi</div>
        <p style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.6 }}>
          Sistem her <strong>2 saatte bir</strong> tüm ürünlerin stok seviyesini tarar. Kritik eşiğin altına düşen
          ürünler için LLM otomatik olarak <strong>önerilen sipariş miktarını</strong> hesaplar ve
          <strong> tedarikçiye taslak e-posta</strong> hazırlar. Oluşturulan biletler Biletler sayfasında görünür;
          tek tıkla e-posta kopyalanabilir.
        </p>
      </div>
    </>
  )
}
