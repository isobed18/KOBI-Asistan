import { useEffect, useMemo, useRef, useState } from 'react'
import {
  createCargoShipment,
  createTicketManual,
  deleteCargoShipment,
  getCargoDashboard,
  markCargoDelayBildirildi,
  patchCargoShipment,
} from '../api.js'
import SortableTh from '../components/SortableTh.jsx'
import { cmpBool, cmpNullableStr, cmpNum, cmpTime } from '../utils/tableSort.js'

const LONG_PRESS_DELETE_MS = 620

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

function sqliteDateToDatetimeLocal(s) {
  if (!s || !String(s).trim()) return ''
  const t = String(s).trim()
  const m = t.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/)
  if (m) return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}`
  const dOnly = t.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (dOnly) return `${dOnly[1]}-${dOnly[2]}-${dOnly[3]}T00:00`
  return ''
}

function datetimeLocalToSqlite(s) {
  if (!s || !String(s).trim()) return null
  const m = String(s).trim().match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/)
  if (!m) return null
  const sec = m[6] ? String(m[6]).padStart(2, '0').slice(0, 2) : '00'
  return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}:${sec}`
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

function DeleteCargoModal({ shipment, loading, onClose, onConfirm }) {
  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="del-cargo-title"
      onClick={e => e.target === e.currentTarget && !loading && onClose()}
    >
      <div className="modal-panel modal-panel--md">
        <div className="section-row" style={{ marginBottom: 8 }}>
          <div id="del-cargo-title" style={{ fontWeight: 700, fontSize: 16 }}>
            Kargo kaydını sil
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => !loading && onClose()} disabled={loading}>
            ✕
          </button>
        </div>
        <p style={{ fontSize: 14, color: 'var(--text2)', lineHeight: 1.55, marginBottom: 16 }}>
          <strong style={{ color: 'var(--text)' }}>Sipariş #{shipment.order_id}</strong> ({shipment.customer_name}) kalıcı olarak silinir;
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

function AddCargoModal({ onClose, onCreated }) {
  const [customerName, setCustomerName] = useState('')
  const [customerPhone, setCustomerPhone] = useState('')
  const [cargoCode, setCargoCode] = useState('')
  const [cargoCompany, setCargoCompany] = useState('')
  const [estimatedDeliveryLocal, setEstimatedDeliveryLocal] = useState('')
  const [lastUpdateLocal, setLastUpdateLocal] = useState('')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState(null)

  const submit = async () => {
    const name = customerName.trim()
    if (!name) {
      setMsg({ ok: false, text: 'Müşteri adı zorunludur.' })
      return
    }
    const code = cargoCode.trim()
    const comp = cargoCompany.trim()
    if (!code || !comp) {
      setMsg({ ok: false, text: 'Kargo kodu ve firma zorunludur.' })
      return
    }

    const payload = {
      customer_name: name,
      customer_phone: customerPhone.trim() || null,
      cargo_tracking_code: code,
      cargo_company: comp,
      notes: 'Kargo paneli',
    }
    const estSql = datetimeLocalToSqlite(estimatedDeliveryLocal)
    if (estSql) payload.estimated_delivery = estSql.split(/[ T]/)[0]
    const lu = datetimeLocalToSqlite(lastUpdateLocal)
    if (lu) payload.last_update = lu

    setLoading(true)
    setMsg(null)
    try {
      await createCargoShipment(payload)
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
      aria-labelledby="add-cargo-title"
      onClick={e => e.target === e.currentTarget && !loading && onClose()}
    >
      <div className="modal-panel modal-panel--md" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
        <div className="section-row" style={{ marginBottom: 8 }}>
          <div id="add-cargo-title" style={{ fontWeight: 700, fontSize: 16 }}>
            Yeni kargo
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => !loading && onClose()} disabled={loading}>
            ✕
          </button>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 12 }}>
          Ürün kalemi gerekmez. Sipariş <strong>kargoda</strong> olarak açılır; takip satırına tahmini teslimat ve son güncelleme yazılır.
        </p>

        <div className="form-group">
          <label>Müşteri adı *</label>
          <input value={customerName} onChange={e => setCustomerName(e.target.value)} disabled={loading} />
        </div>
        <div className="form-group">
          <label>Telefon</label>
          <input value={customerPhone} onChange={e => setCustomerPhone(e.target.value)} disabled={loading} />
        </div>
        <div className="form-row" style={{ gap: 12, marginBottom: 0 }}>
          <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
            <label>Kargo kodu *</label>
            <input value={cargoCode} onChange={e => setCargoCode(e.target.value)} disabled={loading} placeholder="Örn. MNG-12345" />
          </div>
          <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
            <label>Kargo firması *</label>
            <input value={cargoCompany} onChange={e => setCargoCompany(e.target.value)} disabled={loading} placeholder="Örn. MNG" />
          </div>
        </div>

        <div className="form-row" style={{ gap: 12, marginTop: 12, marginBottom: 0 }}>
          <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
            <label>Tahmini teslimat</label>
            <input
              type="datetime-local"
              className="inventory-inline-input orders-inline-datetime"
              style={{ width: '100%', maxWidth: '100%', minWidth: '10.5rem' }}
              value={estimatedDeliveryLocal}
              onChange={e => setEstimatedDeliveryLocal(e.target.value)}
              disabled={loading}
            />
          </div>
          <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
            <label>Son güncelleme</label>
            <input
              type="datetime-local"
              className="inventory-inline-input orders-inline-datetime"
              style={{ width: '100%', maxWidth: '100%', minWidth: '10.5rem' }}
              value={lastUpdateLocal}
              onChange={e => setLastUpdateLocal(e.target.value)}
              disabled={loading}
            />
            <span style={{ fontSize: 11, color: 'var(--text3)', display: 'block', marginTop: 4 }}>
              Boş bırakılırsa şu anki zaman kullanılır.
            </span>
          </div>
        </div>

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

function StatusDot({ delayed }) {
  return delayed
    ? <><span className="dot dot-yellow" />Gecikmeli</>
    : <><span className="dot dot-green" />Aktif</>
}

export default function Cargo() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [ticketMsg, setTicketMsg] = useState({})
  const [tab, setTab] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortKey, setSortKey] = useState('order_id')
  const [sortDir, setSortDir] = useState('asc')
  const [editCell, setEditCell] = useState(null)
  const [savingId, setSavingId] = useState(null)
  const [deleteAsk, setDeleteAsk] = useState(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [holdRowId, setHoldRowId] = useState(null)
  const longPressTimerRef = useRef(null)
  const longPressShipmentRef = useRef(null)

  const isEditing = (orderId, field) => editCell?.id === orderId && editCell?.field === field

  const cellClass = (s, field, editable) => {
    const dis = loading || savingId === s.order_id
    const active = isEditing(s.order_id, field)
    return [
      'inventory-dblcell',
      editable && !active && !dis ? 'inventory-dblcell--editable' : '',
      dis && editable ? 'inventory-dblcell--disabled' : '',
    ]
      .filter(Boolean)
      .join(' ')
  }

  const cancelRowLongPress = () => {
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current)
      longPressTimerRef.current = null
    }
    longPressShipmentRef.current = null
    setHoldRowId(null)
  }

  useEffect(() => () => cancelRowLongPress(), [])

  const load = (opts = {}) => {
    const silent = Boolean(opts.silent)
    if (!silent) setLoading(true)
    return getCargoDashboard()
      .then(d => {
        setData(d)
        setError(null)
      })
      .catch(e => setError(e.message))
      .finally(() => {
        if (!silent) setLoading(false)
      })
  }

  useEffect(() => {
    load()
  }, [])

  const onSort = key => {
    if (key === sortKey) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const applyPatch = (orderId, patch) => {
    setSavingId(orderId)
    setError(null)
    return patchCargoShipment(orderId, patch)
      .then(() => load({ silent: true }))
      .catch(e => setError(e.message))
      .finally(() => setSavingId(null))
  }

  const openTicket = async shipment => {
    setTicketMsg(prev => ({ ...prev, [shipment.order_id]: 'loading' }))
    try {
      await createTicketManual({
        type: 'cargo_delay',
        title: `Kargo Gecikmesi — Sipariş #${shipment.order_id} (${shipment.customer_name})`,
        description: `Sipariş #${shipment.order_id} kargo durumu: '${shipment.cargo_status}'. Kargo kodu: ${shipment.cargo_tracking_code}. Müşteri: ${shipment.customer_name}`,
        priority: 'high',
        related_order_id: shipment.order_id,
      })
      await markCargoDelayBildirildi(shipment.order_id)
      await load({ silent: true })
      setTicketMsg(prev => {
        const next = { ...prev }
        delete next[shipment.order_id]
        return next
      })
    } catch (e) {
      setTicketMsg(prev => ({ ...prev, [shipment.order_id]: `hata: ${e.message}` }))
    }
  }

  const all = data?.shipments ?? []
  const delayed = all.filter(s => s.is_delayed)
  const active = all.filter(s => !s.is_delayed)
  const shown = tab === 'delayed' ? delayed : tab === 'active' ? active : all

  const searchFiltered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return shown
    return shown.filter(s => {
      const hay = [
        String(s.order_id ?? ''),
        s.customer_name ?? '',
        s.customer_phone ?? '',
        s.cargo_tracking_code ?? '',
        s.cargo_company ?? '',
        s.cargo_status ?? '',
        s.estimated_delivery ?? '',
      ]
        .join(' ')
        .toLowerCase()
      return hay.includes(q)
    })
  }, [shown, searchQuery])

  const sorted = useMemo(() => {
    const rows = [...searchFiltered]
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
        case 'customer_phone':
          cmp = cmpNullableStr(a.customer_phone, b.customer_phone)
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
  }, [searchFiltered, sortKey, sortDir])

  const rowPointerDown = s => e => {
    if (loading || savingId === s.order_id) return
    if (e.pointerType === 'mouse' && e.button !== 0) return
    if (e.target?.closest?.('input, textarea, select, button, a')) return

    cancelRowLongPress()
    longPressShipmentRef.current = s
    setHoldRowId(s.order_id)
    longPressTimerRef.current = setTimeout(() => {
      longPressTimerRef.current = null
      const row = longPressShipmentRef.current
      longPressShipmentRef.current = null
      setHoldRowId(null)
      if (row) {
        setEditCell(null)
        setDeleteAsk(row)
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
    deleteCargoShipment(deleteAsk.order_id)
      .then(() => {
        setDeleteAsk(null)
        setError(null)
        setEditCell(null)
        return load({ silent: true })
      })
      .catch(err => setError(err.message))
      .finally(() => setDeleteLoading(false))
  }

  if (!data && loading) return <div className="spinner" />
  if (!data && error) return <div className="error-msg">⚠️ {error}</div>
  if (!data) return <div className="spinner" />

  return (
    <>
      {deleteAsk && (
        <DeleteCargoModal
          shipment={deleteAsk}
          loading={deleteLoading}
          onClose={() => !deleteLoading && setDeleteAsk(null)}
          onConfirm={confirmDelete}
        />
      )}

      {addOpen && (
        <AddCargoModal onClose={() => setAddOpen(false)} onCreated={() => load({ silent: true })} />
      )}

      <div className="card">
        <div className="section-row" style={{ alignItems: 'flex-end', marginBottom: 0, gap: 12 }}>
          <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
            <div className="card-title" style={{ marginBottom: 8 }}>
              Kargo arama
            </div>
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Sipariş no, müşteri, telefon, kargo kodu, firma veya durum…"
              type="search"
              autoComplete="off"
            />
          </div>
          <button type="button" className="btn btn-primary" onClick={() => setAddOpen(true)}>
            + Yeni kargo
          </button>
        </div>
        <p className="inventory-longpress-hint" style={{ fontSize: 12, color: 'var(--text3)', marginTop: 10, marginBottom: 0 }}>
          Hücreye çift tıklayarak düzenleyin · Satıra{' '}
          {(LONG_PRESS_DELETE_MS / 1000).toLocaleString('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} sn basılı tutarak
          siparişi silebilirsiniz (stok iade edilir).
        </p>
      </div>

      <div className="card">
        {error && <div className="error-msg" style={{ marginBottom: 12 }}>⚠️ {error}</div>}
        <div className="tab-bar" style={{ marginBottom: 12 }}>
          <button type="button" className={`tab-btn${tab === 'all' ? ' active' : ''}`} onClick={() => setTab('all')}>
            Tümü ({all.length})
          </button>
          <button type="button" className={`tab-btn${tab === 'delayed' ? ' active' : ''}`} onClick={() => setTab('delayed')}>
            ⚠️ Gecikmeli ({delayed.length})
          </button>
          <button type="button" className={`tab-btn${tab === 'active' ? ' active' : ''}`} onClick={() => setTab('active')}>
            ✅ Sorunsuz ({active.length})
          </button>
        </div>

        {loading ? (
          <div className="spinner" />
        ) : shown.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🚚</div>
            {tab === 'delayed' ? 'Gecikmeli kargo yok' : 'Kargoda sipariş yok'}
            <button type="button" className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => setAddOpen(true)}>
              + Yeni kargo ekle
            </button>
          </div>
        ) : sorted.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🔎</div>
            Aramanızla eşleşen kargo kaydı yok
          </div>
        ) : (
          <div className="table-wrap">
            <table className="inventory-table">
              <thead>
                <tr>
                  <SortableTh columnKey="order_id" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Sipariş
                  </SortableTh>
                  <SortableTh columnKey="customer_name" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Müşteri
                  </SortableTh>
                  <SortableTh columnKey="customer_phone" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Telefon
                  </SortableTh>
                  <SortableTh columnKey="cargo_tracking_code" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Kargo Kodu
                  </SortableTh>
                  <SortableTh columnKey="cargo_company" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Firma
                  </SortableTh>
                  <SortableTh columnKey="cargo_status" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Kargo Durumu
                  </SortableTh>
                  <SortableTh columnKey="estimated_delivery" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Tahmini Teslimat
                  </SortableTh>
                  <SortableTh columnKey="cargo_last_update" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Son Güncelleme
                  </SortableTh>
                  <SortableTh columnKey="is_delayed" sortKey={sortKey} sortDir={sortDir} onSort={onSort}>
                    Durum
                  </SortableTh>
                  <th aria-label="İşlemler" />
                </tr>
              </thead>
              <tbody>
                {sorted.map(s => (
                  <tr
                    key={s.order_id}
                    className={[
                      holdRowId === s.order_id ? 'inventory-row-holding' : '',
                      savingId === s.order_id ? 'row-saving' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    style={s.is_delayed ? { background: 'rgba(239,68,68,.04)' } : {}}
                    title="Düzenleme: çift tıklayın · Silmek: satıra basılı tutun"
                    onPointerDown={rowPointerDown(s)}
                    onPointerUp={rowPointerEnd}
                    onPointerCancel={rowPointerEnd}
                    onPointerLeave={rowPointerEnd}
                  >
                    <td style={{ fontFamily: 'monospace', color: 'var(--text2)' }}>#{s.order_id}</td>
                    <td
                      className={cellClass(s, 'customer_name', true)}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === s.order_id || isEditing(s.order_id, 'customer_name')) return
                        setEditCell({ id: s.order_id, field: 'customer_name' })
                      }}
                    >
                      {isEditing(s.order_id, 'customer_name') ? (
                        <InlineTextEditor
                          initialValue={s.customer_name}
                          disabled={loading || savingId === s.order_id}
                          onSubmit={name => {
                            setEditCell(null)
                            applyPatch(s.order_id, { customer_name: name })
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        <span style={{ fontWeight: 500 }}>{s.customer_name}</span>
                      )}
                    </td>
                    <td
                      className={cellClass(s, 'customer_phone', true)}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === s.order_id || isEditing(s.order_id, 'customer_phone')) return
                        setEditCell({ id: s.order_id, field: 'customer_phone' })
                      }}
                    >
                      {isEditing(s.order_id, 'customer_phone') ? (
                        <InlineTextEditor
                          initialValue={s.customer_phone || ''}
                          disabled={loading || savingId === s.order_id}
                          onSubmit={phone => {
                            setEditCell(null)
                            applyPatch(s.order_id, { customer_phone: phone || null })
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        <span style={{ color: 'var(--text2)' }}>{s.customer_phone || '—'}</span>
                      )}
                    </td>
                    <td
                      className={cellClass(s, 'cargo_tracking_code', true)}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === s.order_id || isEditing(s.order_id, 'cargo_tracking_code')) return
                        setEditCell({ id: s.order_id, field: 'cargo_tracking_code' })
                      }}
                    >
                      {isEditing(s.order_id, 'cargo_tracking_code') ? (
                        <InlineTextEditor
                          initialValue={s.cargo_tracking_code || ''}
                          disabled={loading || savingId === s.order_id}
                          onSubmit={code => {
                            setEditCell(null)
                            applyPatch(s.order_id, { cargo_tracking_code: code || null })
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{s.cargo_tracking_code || '—'}</span>
                      )}
                    </td>
                    <td
                      className={cellClass(s, 'cargo_company', true)}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === s.order_id || isEditing(s.order_id, 'cargo_company')) return
                        setEditCell({ id: s.order_id, field: 'cargo_company' })
                      }}
                    >
                      {isEditing(s.order_id, 'cargo_company') ? (
                        <InlineTextEditor
                          initialValue={s.cargo_company || ''}
                          disabled={loading || savingId === s.order_id}
                          onSubmit={comp => {
                            setEditCell(null)
                            applyPatch(s.order_id, { cargo_company: comp || null })
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        <span style={{ color: 'var(--text2)' }}>{s.cargo_company || '—'}</span>
                      )}
                    </td>
                    <td
                      className={cellClass(s, 'cargo_status', true)}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === s.order_id || isEditing(s.order_id, 'cargo_status')) return
                        setEditCell({ id: s.order_id, field: 'cargo_status' })
                      }}
                    >
                      {isEditing(s.order_id, 'cargo_status') ? (
                        <InlineTextEditor
                          initialValue={s.cargo_status || ''}
                          disabled={loading || savingId === s.order_id}
                          onSubmit={st => {
                            setEditCell(null)
                            applyPatch(s.order_id, { cargo_status: st })
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        <span style={{ color: s.is_delayed ? 'var(--danger)' : 'var(--text2)', fontWeight: s.is_delayed ? 600 : 400 }}>
                          {s.cargo_status || '—'}
                        </span>
                      )}
                    </td>
                    <td
                      className={cellClass(s, 'estimated_delivery', true)}
                      style={{ color: 'var(--text3)', fontSize: 12 }}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === s.order_id || isEditing(s.order_id, 'estimated_delivery')) return
                        setEditCell({ id: s.order_id, field: 'estimated_delivery' })
                      }}
                    >
                      {isEditing(s.order_id, 'estimated_delivery') ? (
                        <InlineDatetimeLocalEditor
                          initialValue={s.estimated_delivery}
                          disabled={loading || savingId === s.order_id}
                          onSubmit={sqliteStr => {
                            setEditCell(null)
                            const day = sqliteStr ? sqliteStr.split(/[ T]/)[0] : null
                            applyPatch(s.order_id, { estimated_delivery: day })
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        fmtDate(s.estimated_delivery)
                      )}
                    </td>
                    <td
                      className={cellClass(s, 'cargo_last_update', true)}
                      style={{ color: 'var(--text3)', fontSize: 12 }}
                      title="Düzenlemek için çift tıklayın"
                      onDoubleClick={() => {
                        if (loading || savingId === s.order_id || isEditing(s.order_id, 'cargo_last_update')) return
                        setEditCell({ id: s.order_id, field: 'cargo_last_update' })
                      }}
                    >
                      {isEditing(s.order_id, 'cargo_last_update') ? (
                        <InlineDatetimeLocalEditor
                          initialValue={s.cargo_last_update}
                          disabled={loading || savingId === s.order_id}
                          onSubmit={sqliteStr => {
                            setEditCell(null)
                            applyPatch(s.order_id, { last_update: sqliteStr })
                          }}
                          onDismiss={() => setEditCell(null)}
                        />
                      ) : (
                        fmtDate(s.cargo_last_update)
                      )}
                    </td>
                    <td>
                      <span style={{ display: 'inline-flex', alignItems: 'center', fontSize: 12 }}>
                        <StatusDot delayed={s.is_delayed} />
                      </span>
                    </td>
                    <td>
                      {ticketMsg[s.order_id] === 'loading' ? (
                        <span className="badge badge-gray">…</span>
                      ) : s.delay_bildirildi_at ? (
                        <span className="badge badge-green">✓ Bildirildi</span>
                      ) : s.is_delayed ? (
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
                          {typeof ticketMsg[s.order_id] === 'string' && ticketMsg[s.order_id].startsWith('hata:') && (
                            <span style={{ fontSize: 11, color: 'var(--danger)', maxWidth: 180 }}>{ticketMsg[s.order_id]}</span>
                          )}
                          <button type="button" className="btn btn-danger btn-sm" onClick={() => openTicket(s)}>
                            Bildir
                          </button>
                        </div>
                      ) : null}
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
