import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  createOrder,
  deleteOrder,
  getOrder,
  getOrderStatusCounts,
  getOrders,
  getProducts,
  patchOrder,
  updateOrderStatus,
} from '../api.js'
import StatusBadge, { ORDER_STATUS } from '../components/StatusBadge.jsx'
import SortableTh from '../components/SortableTh.jsx'
import { cmpNullableStr, cmpNum, cmpTime } from '../utils/tableSort.js'

const STATUS_TABS = [
  { key: 'all', label: 'Tümü', emoji: '' },
  { key: 'hazırlanıyor', label: 'Hazırlanıyor', emoji: '📋' },
  { key: 'kargoda', label: 'Kargoda', emoji: '🚚' },
  { key: 'teslim_edildi', label: 'Teslim', emoji: '✅' },
  { key: 'iptal', label: 'İptal', emoji: '⛔' },
]

const STATUSES = STATUS_TABS.filter(t => t.key !== 'all').map(t => t.key)

function isTerminalCompletedStatus(status) {
  return status === 'tamamlandı' || status === 'tamamlandi'
}

function normalizeOrderStatusForSelect(status) {
  return status === 'tamamlandi' ? 'tamamlandı' : status
}

/** Durum select: yalnızca sekme durumları (tamamlandı seçilemez) */
function statusSelectValuesForRow(orderStatus) {
  const n = normalizeOrderStatusForSelect(orderStatus)
  const base = [...STATUSES]
  if (!base.includes(n)) base.push(orderStatus)
  return base
}

function sqliteDateToDatetimeLocal(s) {
  if (!s || !String(s).trim()) return ''
  const m = String(s).trim().match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/)
  if (!m) return ''
  return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}`
}

function datetimeLocalToSqlite(s) {
  if (!s || !String(s).trim()) return null
  const m = String(s).trim().match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/)
  if (!m) return null
  const sec = m[6] ? String(m[6]).padStart(2, '0').slice(0, 2) : '00'
  return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}:${sec}`
}

const PAGE_SIZE = 20
const LONG_PRESS_DELETE_MS = 620

/** Detay çekmecesinde kalem ekle/sil/kaydet yalnızca bu durumlarda */
const ORDER_ITEMS_EDIT_BLOCKED = new Set(['iptal', 'kargoda', 'teslim_edildi', 'tamamlandi', 'tamamlandı'])

function fmtMoney(n) {
  return n != null ? `₺${n.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}` : '—'
}
function fmtDate(s) {
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

function InlineDatetimeLocalEditor({ initialValue, disabled, onSubmit, onDismiss }) {
  const [v, setV] = useState(() => sqliteDateToDatetimeLocal(initialValue))
  const ref = useRef(null)
  const skipBlur = useRef(false)

  useEffect(() => {
    ref.current?.focus()
  }, [])

  const trySave = () => {
    const origInput = sqliteDateToDatetimeLocal(initialValue)
    if ((v || '').trim() === (origInput || '').trim()) {
      onDismiss()
      return
    }
    const next = datetimeLocalToSqlite(v)
    if (!next) onDismiss()
    else onSubmit(next)
  }

  return (
    <input
      ref={ref}
      type="datetime-local"
      className="inventory-inline-input orders-inline-datetime"
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

function DeleteOrderModal({ order, loading, onClose, onConfirm }) {
  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="del-order-title"
      onClick={e => e.target === e.currentTarget && !loading && onClose()}
    >
      <div className="modal-panel modal-panel--md">
        <div className="section-row" style={{ marginBottom: 8 }}>
          <div id="del-order-title" style={{ fontWeight: 700, fontSize: 16 }}>
            Siparişi sil
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => !loading && onClose()} disabled={loading}>
            ✕
          </button>
        </div>
        <p style={{ fontSize: 14, color: 'var(--text2)', lineHeight: 1.55, marginBottom: 16 }}>
          <strong style={{ color: 'var(--text)' }}>Sipariş #{order.id}</strong> ({order.customer_name}) kalıcı olarak silinir;
          ürün stokları bu siparişe göre iade edilir.
        </p>
        <div className="form-row" style={{ marginBottom: 0, justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={loading}>
            Vazgeç
          </button>
          <button type="button" className="btn btn-danger" onClick={onConfirm} disabled={loading}>
            {loading ? 'Siliniyor…' : 'Sil'}
          </button>
        </div>
      </div>
    </div>
  )
}

function emptyLine(products) {
  const p = products.find(x => x.is_active) || products[0]
  return {
    product_id: p?.id ?? '',
    quantity: 1,
    product_name: p?.name ?? '',
    unit_price: p?.price ?? 0,
  }
}

function AddOrderModal({ products, onClose, onCreated }) {
  const [customerName, setCustomerName] = useState('')
  const [customerPhone, setCustomerPhone] = useState('')
  const [lines, setLines] = useState(() => [emptyLine(products)])
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    if (lines.length === 1 && lines[0].product_id === '' && products.length) {
      setLines([emptyLine(products)])
    }
  }, [products])

  const setLine = (idx, patch) => {
    setLines(prev => prev.map((row, i) => (i === idx ? { ...row, ...patch } : row)))
    setMsg(null)
  }

  const addRow = () => setLines(prev => [...prev, emptyLine(products)])

  const removeRow = idx => {
    setLines(prev => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== idx)))
    setMsg(null)
  }

  const submit = async () => {
    const name = customerName.trim()
    if (!name) {
      setMsg({ ok: false, text: 'Müşteri adı zorunludur.' })
      return
    }
    const items = lines
      .filter(l => l.product_id !== '' && l.product_id != null)
      .map(l => ({ product_id: Number(l.product_id), quantity: Math.max(1, Number(l.quantity)) || 1 }))
    if (!items.length) {
      setMsg({ ok: false, text: 'En az bir ürün seçin.' })
      return
    }

    setLoading(true)
    setMsg(null)
    try {
      await createOrder({
        customer_name: name,
        customer_phone: customerPhone.trim() || null,
        items,
      })
      onCreated()
      onClose()
    } catch (e) {
      setMsg({ ok: false, text: e.message })
    } finally {
      setLoading(false)
    }
  }

  const activeProducts = products.filter(p => p.is_active)

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-order-title"
      onClick={e => e.target === e.currentTarget && !loading && onClose()}
    >
      <div className="modal-panel modal-panel--md" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
        <div className="section-row" style={{ marginBottom: 8 }}>
          <div id="add-order-title" style={{ fontWeight: 700, fontSize: 16 }}>
            Yeni sipariş
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => !loading && onClose()} disabled={loading}>
            ✕
          </button>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 12 }}>
          Ürünler stoktan düşer. Yetersiz stokta kayıt yapılmaz.
        </p>

        <div className="form-group">
          <label>Müşteri adı *</label>
          <input value={customerName} onChange={e => setCustomerName(e.target.value)} disabled={loading} />
        </div>
        <div className="form-group">
          <label>Telefon</label>
          <input value={customerPhone} onChange={e => setCustomerPhone(e.target.value)} disabled={loading} />
        </div>

        <div className="card-title" style={{ marginTop: 8 }}>
          Ürünler
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {lines.map((line, idx) => (
            <div key={idx} className="form-row" style={{ alignItems: 'flex-end', gap: 8, marginBottom: 0 }}>
              <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
                <label>Ürün</label>
                <select
                  value={line.product_id}
                  onChange={e => {
                    const id = e.target.value === '' ? '' : Number(e.target.value)
                    const p = activeProducts.find(x => x.id === id)
                    setLine(idx, {
                      product_id: id,
                      product_name: p?.name ?? '',
                      unit_price: p?.price ?? 0,
                    })
                  }}
                  disabled={loading}
                >
                  <option value="">Seçin…</option>
                  {activeProducts.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.name} (stok: {p.stock_quantity})
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group" style={{ width: 88, marginBottom: 0 }}>
                <label>Adet</label>
                <input
                  type="number"
                  min={1}
                  value={line.quantity}
                  onChange={e => setLine(idx, { quantity: e.target.value })}
                  disabled={loading}
                />
              </div>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => removeRow(idx)} disabled={loading || lines.length <= 1}>
                ✕
              </button>
            </div>
          ))}
        </div>
        <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={addRow} disabled={loading}>
          + Ürün ekle
        </button>

        {msg && <div className={msg.ok ? 'success-msg' : 'error-msg'} style={{ marginTop: 12 }}>{msg.text}</div>}

        <div className="form-row" style={{ marginTop: 16, marginBottom: 0, justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-ghost" onClick={() => !loading && onClose()} disabled={loading}>
            Vazgeç
          </button>
          <button type="button" className="btn btn-primary" onClick={submit} disabled={loading}>
            {loading ? 'Kaydediliyor…' : 'Oluştur'}
          </button>
        </div>
      </div>
    </div>
  )
}

function OrderDetailDrawer({ order, products, onClose, onUpdated }) {
  const [lines, setLines] = useState(() =>
    (order.items || []).map(it => ({
      product_id: it.product_id,
      quantity: it.quantity,
      product_name: it.product_name,
      unit_price: it.unit_price,
    })),
  )
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    let cancelled = false
    getOrder(order.id)
      .then(full => {
        if (cancelled) return
        setLines(
          (full.items || []).map(it => ({
            product_id: it.product_id,
            quantity: it.quantity,
            product_name: it.product_name,
            unit_price: it.unit_price,
          })),
        )
        setMsg(null)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [order.id, order.updated_at])

  const activeProducts = products.filter(p => p.is_active)
  const idsOnLines = useMemo(() => new Set(lines.map(l => l.product_id)), [lines])
  const productChoices = useMemo(() => {
    const inactiveKept = products.filter(p => !p.is_active && idsOnLines.has(p.id))
    return [...activeProducts, ...inactiveKept]
  }, [activeProducts, products, idsOnLines])
  const itemsEditable = !ORDER_ITEMS_EDIT_BLOCKED.has(order.status)

  const setLine = (idx, patch) => {
    setLines(prev => prev.map((row, i) => (i === idx ? { ...row, ...patch } : row)))
    setMsg(null)
  }

  const addRow = () => {
    const p = activeProducts[0]
    setLines(prev => [
      ...prev,
      {
        product_id: p?.id ?? '',
        quantity: 1,
        product_name: p?.name ?? '',
        unit_price: p?.price ?? 0,
      },
    ])
  }

  const removeRow = idx => {
    setLines(prev => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== idx)))
    setMsg(null)
  }

  const lineTotal = lines.reduce((acc, l) => acc + (Number(l.unit_price) || 0) * (Number(l.quantity) || 0), 0)

  const save = async () => {
    if (!itemsEditable) return
    const items = lines
      .filter(l => l.product_id !== '' && l.product_id != null)
      .map(l => ({ product_id: Number(l.product_id), quantity: Math.max(1, Number(l.quantity)) || 1 }))
    if (!items.length) {
      setMsg({ ok: false, text: 'En az bir ürün satırı gerekli.' })
      return
    }

    setLoading(true)
    setMsg(null)
    try {
      await patchOrder(order.id, { items })
      onUpdated()
      onClose()
    } catch (e) {
      setMsg({ ok: false, text: e.message })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="modal-overlay modal-overlay--drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="order-drawer-title"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-panel modal-panel--drawer" onClick={e => e.stopPropagation()}>
        <div className="section-row" style={{ marginBottom: 0 }}>
          <div id="order-drawer-title" style={{ fontWeight: 700, fontSize: 16 }}>
            Sipariş #{order.id}
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
            ✕
          </button>
        </div>
        <div style={{ marginBottom: 12 }}>
          <StatusBadge value={order.status} map={ORDER_STATUS} />
        </div>

        <div className="order-drawer-scroll">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {[
              ['Müşteri', order.customer_name],
              ['Telefon', order.customer_phone || '—'],
              ['Kargo kodu', order.cargo_tracking_code || '—'],
              ['Toplam (liste)', fmtMoney(lineTotal)],
              ['Kayıtlı tutar', fmtMoney(order.total_price)],
              ['Tarih', fmtDate(order.created_at)],
              ['Güncelleme', fmtDate(order.updated_at)],
            ].map(([k, v]) => (
              <div key={k}>
                <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 2 }}>{k}</div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>{v}</div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 16 }}>
            <div className="card-title">Ürünler</div>
            {!itemsEditable && (
              <p style={{ fontSize: 12, color: 'var(--text3)', marginBottom: 8 }}>
                Bu sipariş durumunda ürün kalemleri değiştirilemez.
              </p>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {lines.map((line, idx) => (
                <div key={idx} className="form-row" style={{ alignItems: 'flex-end', gap: 8, marginBottom: 0 }}>
                  <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
                    <label>Ürün</label>
                    <select
                      value={line.product_id}
                      onChange={e => {
                        const id = Number(e.target.value)
                        const p = productChoices.find(x => x.id === id)
                        setLine(idx, {
                          product_id: id,
                          product_name: p?.name ?? '',
                          unit_price: p?.price ?? 0,
                        })
                      }}
                      disabled={!itemsEditable || loading}
                    >
                      {productChoices.map(p => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                          {!p.is_active ? ' (pasif)' : ''} (stok: {p.stock_quantity})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group" style={{ width: 72, marginBottom: 0 }}>
                    <label>Adet</label>
                    <input
                      type="number"
                      min={1}
                      value={line.quantity}
                      onChange={e => setLine(idx, { quantity: e.target.value })}
                      disabled={!itemsEditable || loading}
                    />
                  </div>
                  <span style={{ fontSize: 12, color: 'var(--text2)', paddingBottom: 8 }}>{fmtMoney(line.unit_price)}</span>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => removeRow(idx)}
                    disabled={!itemsEditable || loading || lines.length <= 1}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
            {itemsEditable && (
              <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={addRow} disabled={loading}>
                + Ürün ekle
              </button>
            )}
          </div>

          {msg && <div className={msg.ok ? 'success-msg' : 'error-msg'}>{msg.text}</div>}
          {itemsEditable && (
            <button type="button" className="btn btn-primary" style={{ marginTop: 12 }} onClick={save} disabled={loading}>
              {loading ? 'Kaydediliyor…' : 'Kaydet'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default function Orders() {
  const [orders, setOrders] = useState([])
  const [total, setTotal] = useState(0)
  const [tabCounts, setTabCounts] = useState({ all: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('all')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState(null)
  const [editCell, setEditCell] = useState(null)
  const [savingId, setSavingId] = useState(null)
  const [sortKey, setSortKey] = useState('id')
  const [sortDir, setSortDir] = useState('asc')
  const [deleteAsk, setDeleteAsk] = useState(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [holdRowId, setHoldRowId] = useState(null)
  const [products, setProducts] = useState([])
  const longPressTimerRef = useRef(null)
  const longPressOrderRef = useRef(null)

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE) || 1)

  const onSort = key => {
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
    longPressOrderRef.current = null
    setHoldRowId(null)
  }

  useEffect(() => () => cancelRowLongPress(), [])

  const loadCounts = useCallback(() => {
    return getOrderStatusCounts()
      .then(d => {
        const next = { all: d.total ?? 0 }
        for (const s of STATUSES) {
          next[s] = d.by_status?.[s] ?? 0
        }
        setTabCounts(next)
      })
      .catch(() => {})
  }, [])

  const loadList = useCallback(() => {
    setEditCell(null)
    setLoading(true)
    const params = {
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
      search: search.trim() || undefined,
    }
    if (tab !== 'all') params.status = tab
    return getOrders(params)
      .then(d => {
        setOrders(d.items ?? [])
        setTotal(typeof d.total === 'number' ? d.total : 0)
        setError(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [tab, page, search])

  useEffect(() => {
    loadList()
  }, [loadList])

  useEffect(() => {
    loadCounts()
  }, [loadCounts])

  useEffect(() => {
    getProducts()
      .then(setProducts)
      .catch(() => setProducts([]))
  }, [])

  useEffect(() => {
    setPage(0)
  }, [tab, search])

  const refreshAll = () => {
    loadCounts()
    loadList()
  }

  const mergeOrderRow = (id, partial) => {
    setOrders(prev => prev.map(r => (r.id === id ? { ...r, ...partial } : r)))
    setSelected(s => (s?.id === id ? { ...s, ...partial } : s))
  }

  const isEditing = (orderId, field) => editCell?.id === orderId && editCell?.field === field

  const cellClass = (o, field, editable) => {
    const dis = loading || savingId === o.id
    const active = isEditing(o.id, field)
    return [
      'inventory-dblcell',
      editable && !active && !dis ? 'inventory-dblcell--editable' : '',
      dis && editable ? 'inventory-dblcell--disabled' : '',
    ]
      .filter(Boolean)
      .join(' ')
  }

  const saveCustomerName = (o, name) => {
    setSavingId(o.id)
    setError(null)
    patchOrder(o.id, { customer_name: name })
      .then(() => {
        mergeOrderRow(o.id, { customer_name: name })
        setEditCell(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setSavingId(null))
  }

  const saveCustomerPhone = (o, phone) => {
    const v = phone || null
    setSavingId(o.id)
    setError(null)
    patchOrder(o.id, { customer_phone: v })
      .then(() => {
        mergeOrderRow(o.id, { customer_phone: v })
        setEditCell(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setSavingId(null))
  }

  const saveCargoCode = (o, code) => {
    setSavingId(o.id)
    setError(null)
    updateOrderStatus(o.id, {
      status: o.status,
      cargo_tracking_code: code || null,
      cargo_company: o.cargo_company || null,
    })
      .then(() => {
        mergeOrderRow(o.id, { cargo_tracking_code: code || null })
        setEditCell(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setSavingId(null))
  }

  const saveCargoCompany = (o, company) => {
    setSavingId(o.id)
    setError(null)
    updateOrderStatus(o.id, {
      status: o.status,
      cargo_tracking_code: o.cargo_tracking_code || null,
      cargo_company: company || null,
    })
      .then(() => {
        mergeOrderRow(o.id, { cargo_company: company || null })
        setEditCell(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setSavingId(null))
  }

  const saveCreatedAt = (o, sqliteStr) => {
    setSavingId(o.id)
    setError(null)
    patchOrder(o.id, { created_at: sqliteStr })
      .then(() => {
        mergeOrderRow(o.id, { created_at: sqliteStr })
        setEditCell(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setSavingId(null))
  }

  const onOrderStatusChange = (o, e) => {
    const newStatus = e.target.value
    if (newStatus === o.status) return
    setSavingId(o.id)
    setError(null)
    updateOrderStatus(o.id, {
      status: newStatus,
      cargo_tracking_code: newStatus === 'kargoda' ? o.cargo_tracking_code || null : null,
      cargo_company: newStatus === 'kargoda' ? o.cargo_company || null : null,
    })
      .then(() => {
        mergeOrderRow(o.id, {
          status: newStatus,
          cargo_tracking_code: newStatus === 'kargoda' ? o.cargo_tracking_code : null,
          cargo_company: newStatus === 'kargoda' ? o.cargo_company : null,
        })
        loadCounts()
        loadList()
      })
      .catch(err => setError(err.message))
      .finally(() => setSavingId(null))
  }

  const sorted = useMemo(() => {
    const rows = [...orders]
    const mult = sortDir === 'asc' ? 1 : -1
    rows.sort((a, b) => {
      let cmp = 0
      switch (sortKey) {
        case 'id':
          cmp = cmpNum(a.id, b.id)
          break
        case 'customer_name':
          cmp = cmpNullableStr(a.customer_name, b.customer_name)
          break
        case 'customer_phone':
          cmp = cmpNullableStr(a.customer_phone, b.customer_phone)
          break
        case 'status':
          cmp = cmpNullableStr(a.status, b.status)
          break
        case 'cargo_code':
          cmp = cmpNullableStr(a.cargo_tracking_code, b.cargo_tracking_code)
          break
        case 'cargo_company':
          cmp = cmpNullableStr(a.cargo_company, b.cargo_company)
          break
        case 'total_price':
          cmp = cmpNum(a.total_price, b.total_price)
          break
        case 'created_at':
          cmp = cmpTime(a.created_at, b.created_at)
          break
        default:
          cmp = cmpNum(a.id, b.id)
      }
      return mult * cmp
    })
    return rows
  }, [orders, sortKey, sortDir])

  const rowPointerDown = o => e => {
    if (loading || savingId === o.id) return
    if (e.pointerType === 'mouse' && e.button !== 0) return
    if (e.target?.closest?.('input, textarea, select, button, a')) return

    cancelRowLongPress()
    longPressOrderRef.current = o
    setHoldRowId(o.id)
    longPressTimerRef.current = setTimeout(() => {
      longPressTimerRef.current = null
      const ord = longPressOrderRef.current
      longPressOrderRef.current = null
      setHoldRowId(null)
      if (ord) {
        setDeleteAsk(ord)
        try {
          if (typeof navigator !== 'undefined' && navigator.vibrate) navigator.vibrate(42)
        } catch {
          /* ignore */
        }
      }
    }, LONG_PRESS_DELETE_MS)
  }

  const rowPointerEnd = () => {
    cancelRowLongPress()
  }

  const confirmDelete = () => {
    if (!deleteAsk) return
    setDeleteLoading(true)
    deleteOrder(deleteAsk.id)
      .then(() => {
        setDeleteAsk(null)
        setSelected(s => (s?.id === deleteAsk.id ? null : s))
        setError(null)
        refreshAll()
      })
      .catch(err => setError(err.message))
      .finally(() => setDeleteLoading(false))
  }

  return (
    <>
      {deleteAsk && (
        <DeleteOrderModal
          order={deleteAsk}
          loading={deleteLoading}
          onClose={() => !deleteLoading && setDeleteAsk(null)}
          onConfirm={confirmDelete}
        />
      )}

      {addOpen && (
        <AddOrderModal products={products} onClose={() => setAddOpen(false)} onCreated={() => refreshAll()} />
      )}

      {selected && (
        <OrderDetailDrawer
          order={selected}
          products={products}
          onClose={() => setSelected(null)}
          onUpdated={() => {
            refreshAll()
          }}
        />
      )}

      <div className="card">
        <div className="form-row" style={{ alignItems: 'flex-end', marginBottom: 0, gap: 12 }}>
          <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
            <label>Sipariş ara</label>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Müşteri, takip kodu veya sipariş no…"
            />
          </div>
          <button type="button" className="btn btn-primary" onClick={() => setAddOpen(true)}>
            + Yeni sipariş
          </button>
        </div>
        <p className="inventory-longpress-hint" style={{ fontSize: 12, color: 'var(--text3)', marginTop: 10, marginBottom: 0 }}>
          Hücreye çift tıklayarak müşteri, telefon ve sipariş tarihini düzenleyin · Durum: listeden seçin · Satıra{' '}
          {(LONG_PRESS_DELETE_MS / 1000).toLocaleString('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} sn basılı tutarak
          siparişi silebilirsiniz.
        </p>
      </div>

      <div className="card">
        <div className="tab-bar">
          {STATUS_TABS.map(({ key, label, emoji }) => (
            <button
              key={key}
              type="button"
              className={`tab-btn${tab === key ? ' active' : ''}`}
              onClick={() => setTab(key)}
            >
              {emoji ? `${emoji} ${label}` : label} ({tabCounts[key] ?? 0})
            </button>
          ))}
        </div>

        <div className="orders-pagination-bar" role="navigation" aria-label="Sayfa gezgini">
          <button type="button" className="btn btn-ghost btn-sm" disabled={page <= 0 || loading} onClick={() => setPage(p => Math.max(0, p - 1))}>
            ← Önceki
          </button>
          <span className="orders-pagination-meta">
            Sayfa {page + 1} / {totalPages} · {total} kayıt
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={loading || (page + 1) * PAGE_SIZE >= total}
            onClick={() => setPage(p => p + 1)}
          >
            Sonraki →
          </button>
        </div>

        {loading ? (
          <div className="spinner" />
        ) : error ? (
          <div className="error-msg">⚠️ {error}</div>
        ) : sorted.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📦</div>
            Sipariş bulunamadı
          </div>
        ) : (
          <div className="table-wrap">
            <table className="inventory-table">
              <thead>
                <tr>
                  <SortableTh columnKey="id" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    #
                  </SortableTh>
                  <SortableTh columnKey="customer_name" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Müşteri
                  </SortableTh>
                  <SortableTh columnKey="customer_phone" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Telefon
                  </SortableTh>
                  <SortableTh columnKey="status" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Durum
                  </SortableTh>
                  <SortableTh columnKey="cargo_code" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Kargo kod
                  </SortableTh>
                  <SortableTh columnKey="cargo_company" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Kargo firma
                  </SortableTh>
                  <SortableTh columnKey="total_price" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right">
                    Tutar
                  </SortableTh>
                  <SortableTh columnKey="created_at" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Tarih
                  </SortableTh>
                  <th aria-label="İşlemler" />
                </tr>
              </thead>
              <tbody>
                {sorted.map(o => (
                  <tr
                    key={o.id}
                    className={[
                      holdRowId === o.id ? 'inventory-row-holding' : '',
                      savingId === o.id ? 'row-saving' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    title="Düzenleme: çift tıklayın · Durum: açılır liste · Silmek: satıra basılı tutun"
                    onPointerDown={rowPointerDown(o)}
                    onPointerUp={rowPointerEnd}
                    onPointerCancel={rowPointerEnd}
                    onPointerLeave={rowPointerEnd}
                  >
                    <td style={{ color: 'var(--text3)' }}>{o.id}</td>
                    <td
                      className={cellClass(o, 'customer_name', true)}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === o.id || isEditing(o.id, 'customer_name')) return
                        setEditCell({ id: o.id, field: 'customer_name' })
                      }}
                    >
                      {isEditing(o.id, 'customer_name') ? (
                        <InlineTextEditor
                          initialValue={o.customer_name}
                          disabled={loading || savingId === o.id}
                          onSubmit={name => {
                            setEditCell(null)
                            saveCustomerName(o, name)
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        <span style={{ fontWeight: 500 }}>{o.customer_name}</span>
                      )}
                    </td>
                    <td
                      className={cellClass(o, 'customer_phone', true)}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === o.id || isEditing(o.id, 'customer_phone')) return
                        setEditCell({ id: o.id, field: 'customer_phone' })
                      }}
                    >
                      {isEditing(o.id, 'customer_phone') ? (
                        <InlineTextEditor
                          initialValue={o.customer_phone || ''}
                          disabled={loading || savingId === o.id}
                          onSubmit={phone => {
                            setEditCell(null)
                            saveCustomerPhone(o, phone)
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        <span style={{ color: 'var(--text2)' }}>{o.customer_phone || '—'}</span>
                      )}
                    </td>
                    <td style={{ minWidth: 132 }}>
                      {isTerminalCompletedStatus(o.status) ? (
                        <>
                          <span className="sr-only">Durum</span>
                          <StatusBadge value={normalizeOrderStatusForSelect(o.status)} map={ORDER_STATUS} />
                        </>
                      ) : (
                        <>
                          <label className="sr-only" htmlFor={`order-status-${o.id}`}>
                            Durum
                          </label>
                          <select
                            id={`order-status-${o.id}`}
                            className="orders-status-select"
                            value={normalizeOrderStatusForSelect(o.status)}
                            disabled={loading || savingId === o.id}
                            onChange={e => onOrderStatusChange(o, e)}
                          >
                            {statusSelectValuesForRow(o.status).map(s => (
                              <option key={s} value={s}>
                                {ORDER_STATUS[s]?.label ?? s}
                              </option>
                            ))}
                          </select>
                        </>
                      )}
                    </td>
                    <td
                      className={cellClass(o, 'cargo_code', true)}
                      style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--text2)' }}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === o.id || isEditing(o.id, 'cargo_code')) return
                        setEditCell({ id: o.id, field: 'cargo_code' })
                      }}
                    >
                      {isEditing(o.id, 'cargo_code') ? (
                        <InlineTextEditor
                          initialValue={o.cargo_tracking_code || ''}
                          disabled={loading || savingId === o.id}
                          onSubmit={code => {
                            setEditCell(null)
                            saveCargoCode(o, code)
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : o.cargo_tracking_code ? (
                        o.cargo_tracking_code
                      ) : (
                        <span style={{ color: 'var(--text3)' }}>—</span>
                      )}
                    </td>
                    <td
                      className={cellClass(o, 'cargo_company', true)}
                      style={{ fontSize: 12, color: 'var(--text2)' }}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === o.id || isEditing(o.id, 'cargo_company')) return
                        setEditCell({ id: o.id, field: 'cargo_company' })
                      }}
                    >
                      {isEditing(o.id, 'cargo_company') ? (
                        <InlineTextEditor
                          initialValue={o.cargo_company || ''}
                          disabled={loading || savingId === o.id}
                          onSubmit={company => {
                            setEditCell(null)
                            saveCargoCompany(o, company)
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        o.cargo_company || <span style={{ color: 'var(--text3)' }}>—</span>
                      )}
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 500 }}>{fmtMoney(o.total_price)}</td>
                    <td
                      className={cellClass(o, 'created_at', true)}
                      style={{ color: 'var(--text3)', fontSize: 12 }}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === o.id || isEditing(o.id, 'created_at')) return
                        setEditCell({ id: o.id, field: 'created_at' })
                      }}
                    >
                      {isEditing(o.id, 'created_at') ? (
                        <InlineDatetimeLocalEditor
                          initialValue={o.created_at}
                          disabled={loading || savingId === o.id}
                          onSubmit={sqlStr => {
                            setEditCell(null)
                            saveCreatedAt(o, sqlStr)
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        fmtDate(o.created_at)
                      )}
                    </td>
                    <td>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSelected(o)}>
                        Detay
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!loading && sorted.length > 0 && (
          <div className="orders-pagination-bar orders-pagination-bar--footer" role="navigation" aria-label="Sayfa gezgini alt">
            <button type="button" className="btn btn-ghost btn-sm" disabled={page <= 0} onClick={() => setPage(p => Math.max(0, p - 1))}>
              ← Önceki
            </button>
            <span className="orders-pagination-meta">
              Sayfa {page + 1} / {totalPages}
            </span>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={(page + 1) * PAGE_SIZE >= total}
              onClick={() => setPage(p => p + 1)}
            >
              Sonraki →
            </button>
          </div>
        )}
      </div>
    </>
  )
}
