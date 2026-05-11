export default function StatusBadge({ value, map }) {
  const cfg = map[value] || { label: value, cls: 'badge-gray' }
  return <span className={`badge ${cfg.cls}`}>{cfg.label}</span>
}

export const ORDER_STATUS = {
  'hazırlanıyor': { label: 'Hazırlanıyor', cls: 'badge-yellow' },
  'kargoda':      { label: 'Kargoda',      cls: 'badge-blue'   },
  'teslim_edildi':{ label: 'Teslim Edildi',cls: 'badge-green'  },
  'iptal':        { label: 'İptal',         cls: 'badge-red'   },
}

export const TICKET_STATUS = {
  'open':        { label: 'Açık',        cls: 'badge-red'    },
  'in_progress': { label: 'İşlemde',     cls: 'badge-yellow' },
  'resolved':    { label: 'Çözüldü',     cls: 'badge-green'  },
}

export const TICKET_TYPE = {
  'cargo_delay':          { label: '🚚 Kargo Gecikmesi',  cls: 'badge-yellow' },
  'stock_alert':          { label: '📦 Stok Uyarısı',     cls: 'badge-purple' },
  'cancellation_request': { label: '❌ İptal Talebi',      cls: 'badge-red'    },
  'complaint':            { label: '⚠️ Şikayet',           cls: 'badge-yellow' },
  'refund_request':       { label: '💰 İade Talebi',       cls: 'badge-blue'   },
  'anomaly':              { label: '🔍 Anomali',            cls: 'badge-purple' },
  'other':                { label: 'Diğer',                cls: 'badge-gray'   },
}

export const TICKET_PRIORITY = {
  'critical': { label: '🔴 Kritik',  cls: 'badge-red'    },
  'high':     { label: '🟠 Yüksek',  cls: 'badge-yellow' },
  'normal':   { label: '🔵 Normal',  cls: 'badge-blue'   },
  'low':      { label: '⚪ Düşük',   cls: 'badge-gray'   },
}
