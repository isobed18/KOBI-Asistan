import { useEffect, useRef, useState } from 'react'
import { adminChat, clearAdminSession } from '../api.js'

// ---------------------------------------------------------------------------
// Quick-action chip definitions
// ---------------------------------------------------------------------------
const QUICK_ACTIONS = [
  { label: '📦 Kritik stoklar',        text: 'Kritik stokta olan ürünleri listele' },
  { label: '📊 Günlük özet',           text: 'Bugünkü sipariş ve gelir özetini ver' },
  { label: '⏳ Bekleyen siparişler',   text: 'Hazırlanıyor durumundaki siparişleri listele' },
  { label: '🎫 Açık biletler',         text: 'Çözülmemiş biletleri önceliğe göre listele' },
  { label: '🚚 Kargodaki siparişler',  text: 'Kargoda olan tüm siparişleri listele' },
]

// ---------------------------------------------------------------------------
// Tool card — collapsiable action result
// ---------------------------------------------------------------------------
const TOOL_META = {
  admin_stok_guncelle:       { icon: '📦', label: 'Stok Güncellendi',    color: 'var(--success)' },
  admin_toplu_stok_guncelle: { icon: '📦', label: 'Toplu Stok Güncelle', color: 'var(--success)' },
  admin_siparis_guncelle:        { icon: '🚚', label: 'Sipariş Güncellendi',    color: 'var(--accent)' },
  admin_toplu_siparis_guncelle:  { icon: '🚚', label: 'Toplu Sipariş Güncelle', color: 'var(--accent)' },
  admin_urun_ekle:           { icon: '➕', label: 'Ürün Eklendi',        color: 'var(--accent)' },
  admin_bilet_guncelle:      { icon: '🎫', label: 'Bilet Güncellendi',   color: 'var(--warning)' },
  create_ticket:             { icon: '🎫', label: 'Bilet Oluşturuldu',   color: 'var(--warning)' },
  urun_stok_kontrol:         { icon: '🔍', label: 'Stok Sorgulandı',     color: 'var(--text3)' },
  kritik_stok_listesi:       { icon: '⚠️', label: 'Kritik Stok',         color: 'var(--danger)' },
  gunluk_ozet:               { icon: '📊', label: 'Günlük Özet',         color: 'var(--accent)' },
  siparis_sorgula:           { icon: '📋', label: 'Sipariş Sorgulandı',  color: 'var(--text3)' },
  kargo_takip:               { icon: '🚚', label: 'Kargo Sorgulandı',    color: 'var(--text3)' },
}

function ToolCard({ tc }) {
  const [open, setOpen] = useState(false)
  const meta = TOOL_META[tc.tool] || { icon: '🔧', label: tc.tool, color: 'var(--text3)' }
  const hasOutput = tc.output && Object.keys(tc.output).length > 0
  const isSuccess = tc.output?.basari === true
  const isError   = tc.output?.hata

  return (
    <div style={{
      border: `1px solid ${meta.color}33`,
      borderLeft: `3px solid ${meta.color}`,
      borderRadius: 'var(--radius)',
      background: `${meta.color}08`,
      padding: '8px 12px',
      fontSize: 12,
      marginTop: 4,
    }}>
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: hasOutput ? 'pointer' : 'default' }}
        onClick={() => hasOutput && setOpen(o => !o)}
      >
        <span>{meta.icon}</span>
        <span style={{ fontWeight: 600, color: meta.color }}>{meta.label}</span>
        {isSuccess && <span style={{ color: 'var(--success)', fontSize: 11 }}>✓ başarılı</span>}
        {isError   && <span style={{ color: 'var(--danger)',  fontSize: 11 }}>✗ {tc.output.hata}</span>}
        {hasOutput && (
          <span style={{ marginLeft: 'auto', color: 'var(--text3)', fontSize: 11 }}>
            {open ? '▲ gizle' : '▼ detay'}
          </span>
        )}
      </div>

      {open && hasOutput && (
        <pre style={{
          marginTop: 8, padding: 8, background: 'var(--bg)',
          borderRadius: 4, fontSize: 11, overflowX: 'auto',
          color: 'var(--text2)', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
        }}>
          {JSON.stringify(tc.output, null, 2)}
        </pre>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
const SESSION_KEY = 'admin_chat_session'

export default function AdminAssistant() {
  const [messages, setMessages]   = useState([])   // [{role, content, toolCalls}]
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [sessionId, setSessionId] = useState(() => {
    return sessionStorage.getItem(SESSION_KEY) || null
  })
  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  // Scroll to bottom on new message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Greet on first load
  useEffect(() => {
    if (messages.length === 0) {
      setMessages([{
        role: 'assistant',
        content: 'Merhaba! İşletme yönetim asistanınım. Stok girişi, sipariş güncelleme, ürün ekleme ve bilet yönetimi konularında yardımcı olabilirim.\n\nAşağıdaki hızlı işlemleri deneyebilir ya da doğrudan yazabilirsiniz.',
        toolCalls: [],
      }])
    }
  }, [])

  const send = async (text) => {
    const trimmed = (text || input).trim()
    if (!trimmed || loading) return
    setInput('')

    const userMsg = { role: 'user', content: trimmed, toolCalls: [] }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)

    try {
      const res = await adminChat(trimmed, sessionId)
      // Persist session id
      if (res.session_id && res.session_id !== sessionId) {
        setSessionId(res.session_id)
        sessionStorage.setItem(SESSION_KEY, res.session_id)
      }
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: res.yanit,
        toolCalls: res.tool_calls || [],
      }])
    } catch (e) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `⚠️ Bağlantı hatası: ${e.message}`,
        toolCalls: [],
      }])
    } finally {
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }

  const newChat = async () => {
    if (sessionId) {
      try { await clearAdminSession(sessionId) } catch (_) {}
    }
    const newId = null
    setSessionId(newId)
    sessionStorage.removeItem(SESSION_KEY)
    setMessages([{
      role: 'assistant',
      content: 'Yeni sohbet başlatıldı. Size nasıl yardımcı olabilirim?',
      toolCalls: [],
    }])
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <div className="admin-chat-layout">
      {/* ── Sol panel: Bilgi + hızlı işlemler ── */}
      <div className="admin-chat-sidebar">
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="card-title" style={{ marginBottom: 8 }}>🤖 Neler Yapabilirim?</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {[
              ['📦', 'Stok girişi (tek veya toplu)'],
              ['🚚', 'Sipariş & kargo güncelleme'],
              ['➕', 'Yeni ürün ekleme'],
              ['🎫', 'Bilet yönetimi'],
              ['📊', 'Raporlama & sorgulama'],
            ].map(([icon, text]) => (
              <div key={text} style={{ display: 'flex', gap: 8, fontSize: 13, alignItems: 'flex-start' }}>
                <span style={{ minWidth: 20 }}>{icon}</span>
                <span style={{ color: 'var(--text2)' }}>{text}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-title" style={{ marginBottom: 8 }}>⚡ Hızlı Sorgular</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {QUICK_ACTIONS.map(a => (
              <button
                key={a.label}
                className="btn btn-ghost btn-sm"
                style={{ justifyContent: 'flex-start', textAlign: 'left' }}
                onClick={() => send(a.text)}
                disabled={loading}
              >
                {a.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ marginTop: 12 }}>
          <button className="btn btn-ghost btn-sm" style={{ width: '100%' }} onClick={newChat}>
            🔄 Yeni Sohbet
          </button>
        </div>

        <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text3)', lineHeight: 1.5 }}>
          <strong>Toplu işlem örnekleri:</strong><br />
          "Zeytinyağı 50, domates 30, peynir 20 stok girişi yap"<br /><br />
          "5, 7, 12 numaralı siparişleri kargoya verdim, hepsi Aras kargo"<br /><br />
          "3 numaralı bileti çözdüm, müşteriye iade yapıldı"
        </div>
      </div>

      {/* ── Sağ panel: Chat alanı ── */}
      <div className="admin-chat-main">
        {/* Mesajlar */}
        <div className="admin-chat-messages">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`chat-msg chat-msg-${m.role}`}
            >
              {m.role === 'assistant' && (
                <div className="chat-avatar">🤖</div>
              )}
              <div className="chat-bubble">
                <div className="chat-content">{m.content}</div>
                {m.toolCalls?.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
                    {m.toolCalls.map((tc, j) => <ToolCard key={j} tc={tc} />)}
                  </div>
                )}
              </div>
              {m.role === 'user' && (
                <div className="chat-avatar chat-avatar-user">👤</div>
              )}
            </div>
          ))}

          {loading && (
            <div className="chat-msg chat-msg-assistant">
              <div className="chat-avatar">🤖</div>
              <div className="chat-bubble">
                <div className="chat-typing">
                  <span /><span /><span />
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input alanı */}
        <div className="admin-chat-input-area">
          <textarea
            ref={inputRef}
            className="admin-chat-input"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Mesajınızı yazın… (Enter gönderin, Shift+Enter yeni satır)"
            rows={2}
            disabled={loading}
          />
          <button
            className="btn btn-primary"
            onClick={() => send()}
            disabled={loading || !input.trim()}
            style={{ alignSelf: 'flex-end', minWidth: 80 }}
          >
            {loading ? '…' : '➤ Gönder'}
          </button>
        </div>
      </div>
    </div>
  )
}
