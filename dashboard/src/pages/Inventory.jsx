import { useEffect, useMemo, useRef, useState } from 'react'
import { createProduct, deleteProduct, getProducts, patchProduct } from '../api.js'
import SortableTh from '../components/SortableTh.jsx'
import { cmpNullableStr, cmpNum } from '../utils/tableSort.js'

function stockStatusRank(p) {
  if (p.stock_quantity === 0) return 0
  if (p.is_low_stock) return 1
  return 2
}

function StockBar({ qty, threshold }) {
  const max = Math.max(threshold * 5, qty, 1)
  const pct = Math.min((qty / max) * 100, 100)
  const color = qty === 0 ? 'var(--danger)'
    : qty <= threshold ? 'var(--warning)'
    : pct < 60 ? 'var(--accent)'
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

function InlineTextEditor({ initialValue, disabled, onSubmit, onDismiss }) {
  const [v, setV] = useState(initialValue ?? '')
  const ref = useRef(null)
  const skipBlur = useRef(false)

  useEffect(() => {
    ref.current?.focus()
    ref.current?.select?.()
  }, [])

  const trySave = () => {
    const next = (v ?? '').trim()
    const prev = (initialValue ?? '').trim()
    if (next !== prev) onSubmit(next)
    else onDismiss()
  }

  return (
    <input
      ref={ref}
      type="text"
      className="inventory-inline-input"
      value={v}
      disabled={disabled}
      onChange={e => setV(e.target.value)}
      onDoubleClick={e => e.stopPropagation()}
      onBlur={() => {
        if (skipBlur.current) {
          skipBlur.current = false
          return
        }
        trySave()
      }}
      onKeyDown={e => {
        if (e.key === 'Escape') {
          e.preventDefault()
          skipBlur.current = true
          onDismiss()
        }
        if (e.key === 'Enter') {
          e.preventDefault()
          ref.current?.blur()
        }
      }}
    />
  )
}

function InlineNumberEditor({ initialValue, min = 0, step, disabled, alignNum, onSubmit, onDismiss }) {
  const [v, setV] = useState(String(initialValue ?? ''))
  const ref = useRef(null)
  const skipBlur = useRef(false)

  useEffect(() => {
    ref.current?.focus()
    ref.current?.select?.()
  }, [])

  const trySave = () => {
    const n = parseFloat(v)
    if (Number.isNaN(n)) {
      onDismiss()
      return
    }
    const prev = Number(initialValue)
    if (step !== undefined && step < 1) {
      const rounded = Math.round(n * 100) / 100
      if (Math.abs(rounded - prev) <= 0.0001) {
        onDismiss()
        return
      }
      onSubmit(rounded)
      return
    }
    const rounded = Math.round(n)
    if (rounded === prev) {
      onDismiss()
      return
    }
    onSubmit(rounded)
  }

  return (
    <input
      ref={ref}
      type="number"
      className={`inventory-inline-input${alignNum ? ' inventory-inline-input--num' : ''}`}
      value={v}
      disabled={disabled}
      min={min}
      step={step}
      onChange={e => setV(e.target.value)}
      onDoubleClick={e => e.stopPropagation()}
      onBlur={() => {
        if (skipBlur.current) {
          skipBlur.current = false
          return
        }
        trySave()
      }}
      onKeyDown={e => {
        if (e.key === 'Escape') {
          e.preventDefault()
          skipBlur.current = true
          onDismiss()
        }
        if (e.key === 'Enter') {
          e.preventDefault()
          ref.current?.blur()
        }
      }}
    />
  )
}

/** Satıra basılı tutunca silme onayı (ms) */
const LONG_PRESS_DELETE_MS = 620

const emptyNewProduct = () => ({
  name: '',
  category: '',
  price: '',
  stock_quantity: '',
  low_stock_threshold: '10',
})

function AddProductModal({ onClose, onCreated }) {
  const [form, setForm] = useState(() => emptyNewProduct())
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState(null)

  const set = (key, val) => {
    setForm(f => ({ ...f, [key]: val }))
    setMsg(null)
  }

  const submit = async () => {
    const name = (form.name || '').trim()
    if (!name) {
      setMsg({ ok: false, text: 'Ürün adı zorunludur.' })
      return
    }
    const price = parseFloat(form.price)
    if (Number.isNaN(price) || price < 0) {
      setMsg({ ok: false, text: 'Geçerli bir fiyat girin (≥ 0).' })
      return
    }
    const stock_quantity = parseInt(form.stock_quantity, 10)
    if (Number.isNaN(stock_quantity) || stock_quantity < 0) {
      setMsg({ ok: false, text: 'Geçerli bir stok miktarı girin (≥ 0).' })
      return
    }
    const low_stock_threshold = parseInt(form.low_stock_threshold, 10)
    if (Number.isNaN(low_stock_threshold) || low_stock_threshold < 0) {
      setMsg({ ok: false, text: 'Geçerli bir eşik değeri girin (≥ 0).' })
      return
    }

    const body = {
      name,
      price: Math.round(price * 100) / 100,
      stock_quantity,
      low_stock_threshold,
      ...(form.category.trim() ? { category: form.category.trim() } : { category: null }),
    }

    setLoading(true)
    setMsg(null)
    try {
      await createProduct(body)
      setMsg({ ok: true, text: 'Ürün eklendi.' })
      onCreated()
      onClose()
    } catch (e) {
      setMsg({ ok: false, text: e.message })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-product-title"
      onClick={e => e.target === e.currentTarget && !loading && onClose()}
    >
      <div className="modal-panel modal-panel--md">
        <div className="section-row" style={{ marginBottom: 4 }}>
          <div id="add-product-title" style={{ fontWeight: 700, fontSize: 16 }}>Yeni ürün</div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => !loading && onClose()} disabled={loading}>
            ✕
          </button>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 16 }}>
          Tüm alanları doldurun; ürün veritabanına kaydedilir ve listede görünür.
        </p>

        <div className="form-group">
          <label>Ürün adı *</label>
          <input value={form.name} onChange={e => set('name', e.target.value)} placeholder="Örn. Organik zeytinyağı 1L" autoFocus />
        </div>
        <div className="form-group">
          <label>Kategori</label>
          <input value={form.category} onChange={e => set('category', e.target.value)} placeholder="Örn. Gıda" />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label>Fiyat (₺) *</label>
            <input type="number" min={0} step="0.01" value={form.price} onChange={e => set('price', e.target.value)} placeholder="0.00" />
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label>Stok adedi *</label>
            <input type="number" min={0} step={1} value={form.stock_quantity} onChange={e => set('stock_quantity', e.target.value)} placeholder="0" />
          </div>
        </div>
        <div className="form-group">
          <label>Kritik stok eşiği *</label>
          <input type="number" min={0} step={1} value={form.low_stock_threshold} onChange={e => set('low_stock_threshold', e.target.value)} placeholder="10" />
          <span style={{ fontSize: 12, color: 'var(--text3)', display: 'block', marginTop: 6 }}>
            Stok bu değerin altına veya eşitine düşünce kritik sayılır.
          </span>
        </div>

        {msg && <div className={msg.ok ? 'success-msg' : 'error-msg'}>{msg.text}</div>}

        <div className="form-row" style={{ marginTop: 8, marginBottom: 0, justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-ghost" onClick={() => !loading && onClose()} disabled={loading}>
            Vazgeç
          </button>
          <button type="button" className="btn btn-primary" onClick={submit} disabled={loading}>
            {loading ? 'Kaydediliyor…' : 'Ekle'}
          </button>
        </div>
      </div>
    </div>
  )
}

function DeleteProductModal({ product, loading, onClose, onConfirm }) {
  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="del-product-title"
      onClick={e => e.target === e.currentTarget && !loading && onClose()}
    >
      <div className="modal-panel modal-panel--md">
        <div className="section-row" style={{ marginBottom: 8 }}>
          <div id="del-product-title" style={{ fontWeight: 700, fontSize: 16 }}>Ürünü pasife al</div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => !loading && onClose()} disabled={loading}>
            ✕
          </button>
        </div>
        <p style={{ fontSize: 14, color: 'var(--text2)', lineHeight: 1.55, marginBottom: 16 }}>
          <strong style={{ color: 'var(--text)' }}>{product.name}</strong> listeden kaldırılır (yumuşak silme).
          İsterseniz daha sonra aynı isimle yeni kayıt ekleyebilirsiniz.
        </p>
        <div className="form-row" style={{ marginBottom: 0, justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={loading}>
            Vazgeç
          </button>
          <button type="button" className="btn btn-danger" onClick={onConfirm} disabled={loading}>
            {loading ? 'Siliniyor…' : 'Pasife al'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Inventory() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState('all')
  const [sortKey, setSortKey] = useState('id')
  const [sortDir, setSortDir] = useState('asc')
  const [savingId, setSavingId] = useState(null)
  const [addOpen, setAddOpen] = useState(false)
  /** Çift tıklanan hücre: yalnızca bu alan düzenleme modunda */
  const [editCell, setEditCell] = useState(null)
  /** Uzun basış sonrası silme onayı */
  const [deleteAsk, setDeleteAsk] = useState(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [holdRowId, setHoldRowId] = useState(null)
  const longPressTimerRef = useRef(null)
  const longPressProductRef = useRef(null)

  const isEditing = (productId, field) => editCell?.id === productId && editCell?.field === field

  const cellClass = (p, field, editable) => {
    const dis = loading || savingId === p.id
    const active = isEditing(p.id, field)
    return [
      'inventory-dblcell',
      editable && !active && !dis ? 'inventory-dblcell--editable' : '',
      dis && editable ? 'inventory-dblcell--disabled' : '',
    ]
      .filter(Boolean)
      .join(' ')
  }

  const onSort = (key) => {
    if (key === sortKey) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const cancelRowLongPress = () => {
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current)
      longPressTimerRef.current = null
    }
    longPressProductRef.current = null
    setHoldRowId(null)
  }

  useEffect(() => () => cancelRowLongPress(), [])

  const load = () => {
    setEditCell(null)
    setDeleteAsk(null)
    cancelRowLongPress()
    setLoading(true)
    getProducts()
      .then(d => { setProducts(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const updateRow = (id, patch) => {
    setSavingId(id)
    return patchProduct(id, patch)
      .then(updated => {
        setProducts(prev => prev.map(p => (p.id === id ? updated : p)))
        setError(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setSavingId(null))
  }

  const byTab = tab === 'critical'
    ? products.filter(p => p.is_low_stock)
    : tab === 'ok'
    ? products.filter(p => !p.is_low_stock)
    : products

  const filtered = search
    ? byTab.filter(p => p.name.toLowerCase().includes(search.toLowerCase()) || (p.category || '').toLowerCase().includes(search.toLowerCase()))
    : byTab

  const sorted = useMemo(() => {
    const rows = [...filtered]
    const mult = sortDir === 'asc' ? 1 : -1
    rows.sort((a, b) => {
      let cmp = 0
      switch (sortKey) {
        case 'id':
          cmp = cmpNum(a.id, b.id)
          break
        case 'name':
          cmp = cmpNullableStr(a.name, b.name)
          break
        case 'category':
          cmp = cmpNullableStr(a.category, b.category)
          break
        case 'price':
          cmp = cmpNum(a.price, b.price)
          break
        case 'stock_quantity':
          cmp = cmpNum(a.stock_quantity, b.stock_quantity)
          break
        case 'low_stock_threshold':
          cmp = cmpNum(a.low_stock_threshold, b.low_stock_threshold)
          break
        case 'status':
          cmp = cmpNum(stockStatusRank(a), stockStatusRank(b))
          break
        default:
          cmp = cmpNum(a.id, b.id)
      }
      return mult * cmp
    })
    return rows
  }, [filtered, sortKey, sortDir])

  const criticalCount = products.filter(p => p.is_low_stock).length

  const rowPointerDown = (p) => (e) => {
    if (loading || savingId === p.id) return
    if (e.pointerType === 'mouse' && e.button !== 0) return
    if (e.target?.closest?.('input, textarea, select, button, a')) return

    cancelRowLongPress()
    longPressProductRef.current = p
    setHoldRowId(p.id)
    longPressTimerRef.current = setTimeout(() => {
      longPressTimerRef.current = null
      const prod = longPressProductRef.current
      longPressProductRef.current = null
      setHoldRowId(null)
      if (prod) {
        setEditCell(null)
        setDeleteAsk(prod)
        try {
          if (typeof navigator !== 'undefined' && navigator.vibrate) navigator.vibrate(42)
        } catch { /* ignore */ }
      }
    }, LONG_PRESS_DELETE_MS)
  }

  const rowPointerEnd = () => {
    cancelRowLongPress()
  }

  const confirmDelete = () => {
    if (!deleteAsk) return
    setDeleteLoading(true)
    deleteProduct(deleteAsk.id)
      .then(() => {
        setDeleteAsk(null)
        setError(null)
        load()
      })
      .catch(err => setError(err.message))
      .finally(() => setDeleteLoading(false))
  }

  return (
    <>
      {deleteAsk && (
        <DeleteProductModal
          product={deleteAsk}
          loading={deleteLoading}
          onClose={() => !deleteLoading && setDeleteAsk(null)}
          onConfirm={confirmDelete}
        />
      )}

      {addOpen && (
        <AddProductModal
          onClose={() => setAddOpen(false)}
          onCreated={() => load()}
        />
      )}

      <div className="card">
        <div className="form-row" style={{ alignItems: 'flex-end', marginBottom: 0, gap: 12 }}>
          <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
            <label>Ürün Ara</label>
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Ürün adı veya kategori…" />
          </div>
          <button type="button" className="btn btn-primary" onClick={() => setAddOpen(true)}>
            + Yeni stok ekle
          </button>
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
        ) : sorted.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🗂️</div>
            Ürün bulunamadı
          </div>
        ) : (
          <div className="table-wrap">
            <p className="inventory-longpress-hint" style={{ fontSize: 12, color: 'var(--text3)', marginBottom: 10 }}>
              Satıra {(LONG_PRESS_DELETE_MS / 1000).toLocaleString('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} sn basılı tutarak ürünü pasife alabilirsiniz.
            </p>
            <table className="inventory-table">
              <thead>
                <tr>
                  <SortableTh columnKey="id" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>#</SortableTh>
                  <SortableTh columnKey="name" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>Ürün</SortableTh>
                  <SortableTh columnKey="category" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>Kategori</SortableTh>
                  <SortableTh columnKey="price" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right">Fiyat</SortableTh>
                  <SortableTh columnKey="stock_quantity" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right">Stok Seviyesi</SortableTh>
                  <SortableTh columnKey="low_stock_threshold" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right">Eşik</SortableTh>
                  <SortableTh columnKey="status" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>Durum</SortableTh>
                </tr>
              </thead>
              <tbody>
                {sorted.map(p => (
                  <tr
                    key={p.id}
                    className={[
                      savingId === p.id ? 'row-saving' : '',
                      holdRowId === p.id ? 'inventory-row-holding' : '',
                    ].filter(Boolean).join(' ')}
                    title="Düzenleme: hücreye çift tıklayın · Pasife alma: satıra basılı tutun"
                    onPointerDown={rowPointerDown(p)}
                    onPointerUp={rowPointerEnd}
                    onPointerCancel={rowPointerEnd}
                    onPointerLeave={rowPointerEnd}
                  >
                    <td style={{ color: 'var(--text3)' }}>{p.id}</td>
                    <td
                      className={cellClass(p, 'name', true)}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === p.id || isEditing(p.id, 'name')) return
                        setEditCell({ id: p.id, field: 'name' })
                      }}
                    >
                      {isEditing(p.id, 'name') ? (
                        <InlineTextEditor
                          initialValue={p.name}
                          disabled={loading || savingId === p.id}
                          onSubmit={(name) => {
                            setEditCell(null)
                            updateRow(p.id, { name })
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        <span style={{ fontWeight: 500 }}>{p.name}</span>
                      )}
                    </td>
                    <td
                      className={cellClass(p, 'category', true)}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === p.id || isEditing(p.id, 'category')) return
                        setEditCell({ id: p.id, field: 'category' })
                      }}
                    >
                      {isEditing(p.id, 'category') ? (
                        <InlineTextEditor
                          initialValue={p.category || ''}
                          disabled={loading || savingId === p.id}
                          onSubmit={(category) => {
                            setEditCell(null)
                            updateRow(p.id, { category: category || null })
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        <span style={{ color: 'var(--text2)' }}>{p.category || '—'}</span>
                      )}
                    </td>
                    <td
                      className={cellClass(p, 'price', true)}
                      style={{ textAlign: 'right' }}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === p.id || isEditing(p.id, 'price')) return
                        setEditCell({ id: p.id, field: 'price' })
                      }}
                    >
                      {isEditing(p.id, 'price') ? (
                        <InlineNumberEditor
                          initialValue={p.price}
                          step={0.01}
                          min={0}
                          alignNum
                          disabled={loading || savingId === p.id}
                          onSubmit={(price) => {
                            setEditCell(null)
                            updateRow(p.id, { price })
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        `₺${p.price?.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}`
                      )}
                    </td>
                    <td
                      className={cellClass(p, 'stock_quantity', true)}
                      style={{ minWidth: 140 }}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === p.id || isEditing(p.id, 'stock_quantity')) return
                        setEditCell({ id: p.id, field: 'stock_quantity' })
                      }}
                    >
                      {isEditing(p.id, 'stock_quantity') ? (
                        <InlineNumberEditor
                          initialValue={p.stock_quantity}
                          min={0}
                          step={1}
                          alignNum
                          disabled={loading || savingId === p.id}
                          onSubmit={(stock_quantity) => {
                            setEditCell(null)
                            updateRow(p.id, { stock_quantity })
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        <StockBar qty={p.stock_quantity} threshold={p.low_stock_threshold} />
                      )}
                    </td>
                    <td
                      className={cellClass(p, 'low_stock_threshold', true)}
                      style={{ color: 'var(--text3)', textAlign: 'right' }}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === p.id || isEditing(p.id, 'low_stock_threshold')) return
                        setEditCell({ id: p.id, field: 'low_stock_threshold' })
                      }}
                    >
                      {isEditing(p.id, 'low_stock_threshold') ? (
                        <InlineNumberEditor
                          initialValue={p.low_stock_threshold}
                          min={0}
                          step={1}
                          alignNum
                          disabled={loading || savingId === p.id}
                          onSubmit={(low_stock_threshold) => {
                            setEditCell(null)
                            updateRow(p.id, { low_stock_threshold })
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        p.low_stock_threshold
                      )}
                    </td>
                    <td>
                      {p.stock_quantity === 0 ? (
                        <span className="badge badge-red">Tükendi</span>
                      ) : p.is_low_stock ? (
                        <span className="badge badge-yellow">Kritik</span>
                      ) : (
                        <span className="badge badge-green">Yeterli</span>
                      )}
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
