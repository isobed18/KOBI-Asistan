import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router-dom'
import { adminChat, clearAdminSession, confirmAdminPending } from '../api.js'

function AssistantMarkdown({ text }) {
  if (!text?.trim()) return null
  return (
    <ReactMarkdown
      components={{
        a: ({ children, href, ...rest }) => {
          if (href?.startsWith('/')) {
            return (
              <Link to={href} {...rest}>
                {children}
              </Link>
            )
          }
          return (
            <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
              {children}
            </a>
          )
        },
      }}
    >
      {text}
    </ReactMarkdown>
  )
}

// ---------------------------------------------------------------------------
// Quick-action icons + definitions
// ---------------------------------------------------------------------------
function IconArrowUp(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  )
}

function IconQuickPackage(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M16.5 9.4 7.55 4.24" />
      <path d="m21 16-9.38-5.25M3.27 9.96 12 15l8.73-5.04" />
      <path d="M12 22V12" />
      <path d="M12 12 3.27 6.96 12 2l8.73 4.96L12 12Z" />
      <path d="M7.5 4.21v9.79M16.5 9.4v9.8" />
    </svg>
  )
}

function IconQuickChart(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M3 3v18h18" />
      <path d="M7 12v5" />
      <path d="M12 8v9" />
      <path d="M17 5v12" />
    </svg>
  )
}

function IconQuickHourglass(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M5 22h14" />
      <path d="M5 2h14" />
      <path d="M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22" />
      <path d="M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2" />
    </svg>
  )
}

function IconQuickTicket(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z" />
      <path d="M13 5v2" />
      <path d="M13 17v2" />
      <path d="M13 11v2" />
    </svg>
  )
}

const QUICK_ACTIONS = [
  { label: 'Kritik Stok', text: 'Kritik stokta olan ürünleri listele', Icon: IconQuickPackage },
  { label: 'Bekleyen Siparişler', text: 'Hazırlanıyor durumundaki siparişleri listele', Icon: IconQuickHourglass },
  { label: 'Günlük Özet', text: 'Bugünkü sipariş ve gelir özetini ver', Icon: IconQuickChart },
  { label: 'Açık Biletler', text: 'Çözülmemiş biletleri önceliğe göre listele', Icon: IconQuickTicket },
]

function IconNewChat(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Tool card — collapsiable action result
// ---------------------------------------------------------------------------
const TOOL_META = {
  admin_urun_listesi:          { icon: '📋', label: 'Ürün Listesi',        color: 'var(--accent)' },
  admin_stok_onay_iste:        { icon: '📦', label: 'Stok — onay bekliyor', color: 'var(--warning)' },
  admin_stok_toplu_onay_iste:  { icon: '📦', label: 'Toplu stok — onay',   color: 'var(--warning)' },
  admin_siparis_onay_iste:     { icon: '🚚', label: 'Sipariş — onay bekliyor', color: 'var(--warning)' },
  admin_siparis_toplu_onay_iste: { icon: '🚚', label: 'Toplu sipariş — onay', color: 'var(--warning)' },
  admin_siparis_sil_onay_iste: { icon: '🗑️', label: 'Sipariş sil — onay',   color: 'var(--danger)' },
  admin_urun_ekle_onay_iste:   { icon: '➕', label: 'Ürün ekle — onay',    color: 'var(--warning)' },
  admin_urun_duzenle_onay_iste: { icon: '✏️', label: 'Ürün düzenle — onay', color: 'var(--warning)' },
  admin_urun_sil_onay_iste:    { icon: '🗑️', label: 'Ürün pasifle — onay', color: 'var(--danger)' },
  admin_pending_uygula:        { icon: '✓', label: 'İşlem uygulandı',     color: 'var(--success)' },
  admin_siparis_listesi:       { icon: '📋', label: 'Sipariş Listesi',     color: 'var(--accent)' },
  admin_bilet_listesi:         { icon: '🎫', label: 'Bilet Listesi',     color: 'var(--warning)' },
  admin_bilet_guncelle:      { icon: '🎫', label: 'Bilet Güncellendi',   color: 'var(--warning)' },
  create_ticket:             { icon: '🎫', label: 'Bilet Oluşturuldu',   color: 'var(--warning)' },
  urun_stok_kontrol:         { icon: '🔍', label: 'Stok Sorgulandı',     color: 'var(--text3)' },
  kritik_stok_listesi:       { icon: '⚠️', label: 'Kritik Stok',         color: 'var(--danger)' },
  gunluk_ozet:               { icon: '📊', label: 'Günlük Özet',         color: 'var(--accent)' },
  siparis_sorgula:           { icon: '📋', label: 'Sipariş Sorgulandı',  color: 'var(--text3)' },
  kargo_takip:               { icon: '🚚', label: 'Kargo Sorgulandı',    color: 'var(--text3)' },
}

function ToolCard({ tc, sessionId, loading, onConfirmPending }) {
  const [open, setOpen] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const meta = TOOL_META[tc.tool] || { icon: '🔧', label: tc.tool, color: 'var(--text3)' }
  const hasOutput = tc.output && Object.keys(tc.output).length > 0
  const isSuccess = tc.output?.basari === true
  const isError   = tc.output?.hata
  const pending = tc.output?.onay_bekliyor === true && tc.output?.onay_token

  const runConfirm = async () => {
    if (!pending || !onConfirmPending) return
    setConfirming(true)
    try {
      await onConfirmPending(tc.output.onay_token)
    } finally {
      setConfirming(false)
    }
  }

  return (
    <div
      className="assistant-tool-card"
      style={{ '--tool-accent': meta.color }}
    >
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

      {pending ? (
        <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          {tc.output.ozet ? (
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text2)', flex: '1 1 100%' }}>{tc.output.ozet}</p>
          ) : null}
          <button
            type="button"
            className="assistant-quick-pill"
            style={{ border: '1px solid var(--success)', color: 'var(--success)', background: 'transparent' }}
            disabled={loading || confirming}
            onClick={(e) => { e.stopPropagation(); runConfirm() }}
          >
            {confirming ? 'Uygulanıyor…' : 'Onayla'}
          </button>
        </div>
      ) : null}

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
        content:
          'Merhaba. İstediğinizi yazabilir veya soldaki **Hızlı sorgular** ile başlayabilirsiniz. Veritabanına yazan işlemler özetlenir; **Onayla** ile tamamlanırlar.',
        toolCalls: [],
      }])
    }
  }, [])

  const confirmPending = async (onayToken) => {
    setLoading(true)
    try {
      const res = await confirmAdminPending(onayToken, sessionId)
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: res.yanit,
        toolCalls: res.tool_calls || [],
      }])
    } catch (e) {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: `⚠️ Onay başarısız: ${e.message}`,
        toolCalls: [],
      }])
    } finally {
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }

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

  const typingInComposer = Boolean(input.trim())

  return (
    <div className="admin-chat-layout">
      <div className="admin-chat-sidebar">
        <section
          className={`assistant-panel assistant-panel--quick assistant-panel--quick-tall${
            typingInComposer ? ' is-faded' : ''
          }`}
        >
          <div className="assistant-quick-head">
            <h2 className="assistant-panel-eyebrow assistant-panel-eyebrow--tight">Hızlı sorgular</h2>
            <p className="assistant-quick-sub">Tek tıkla aynı isteği gönderir</p>
          </div>
          <div className="assistant-quick-pills assistant-quick-pills--sidebar">
            {QUICK_ACTIONS.map((a) => {
              const QIcon = a.Icon
              return (
                <button
                  key={a.label}
                  type="button"
                  className="assistant-quick-pill assistant-quick-pill--sidebar"
                  onClick={() => send(a.text)}
                  disabled={loading}
                >
                  <QIcon className="assistant-quick-pill-icon" aria-hidden />
                  <span>{a.label}</span>
                </button>
              )
            })}
          </div>
        </section>

        <section className="assistant-panel assistant-panel--capabilities">
          <div className="assistant-panel-cap-header">
            <h2 className="assistant-panel-eyebrow">İşletme asistanı</h2>
            <h3 className="assistant-panel-title">Neler yapabilirim?</h3>
          </div>
          <ul className="assistant-intro-list">
            <li>
              <strong>Stok, sipariş ve kargo</strong> için listeleme, ekleme, düzenleme ve silme işlemlerini
              doğal dil ile isteyebilirsiniz.
            </li>
            <li>
              Veritabanında kalıcı değişiklik öncesi işlem özeti gösterilir; yalnızca siz{' '}
              <strong className="assistant-lead-strong">onayladığınızda</strong> uygulanır.
            </li>
            <li>
              <strong>Açık biletler</strong> listelenebilir; <strong>günlük özet</strong> ve rapor sorularına
              yanıt verilir.
            </li>
          </ul>
        </section>
      </div>

      <div className="admin-chat-main admin-chat-main--minimal">
        <div className="admin-chat-thread-wrap">
          <button
            type="button"
            className="admin-chat-btn-new-session"
            onClick={newChat}
            aria-label="Yeni sohbet başlat"
          >
            <IconNewChat className="admin-chat-btn-new-session-icon" aria-hidden />
            <span>Yeni sohbet</span>
          </button>
          <div className="admin-chat-messages admin-chat-messages--minimal">
          {messages.map((m, i) => (
            <div key={i} className={`chat-msg chat-msg-${m.role}`}>
              <div className="chat-bubble">
                <div className={`chat-content${m.role === 'assistant' ? ' chat-content--md' : ''}`}>
                  {m.role === 'assistant'
                    ? <AssistantMarkdown text={m.content} />
                    : m.content}
                </div>
                {m.toolCalls?.length > 0 ? (
                  <div className="assistant-tool-stack">
                    {m.toolCalls.map((tc, j) => (
                      <ToolCard
                        key={j}
                        tc={tc}
                        sessionId={sessionId}
                        loading={loading}
                        onConfirmPending={confirmPending}
                      />
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          ))}

          {loading ? (
            <div className="chat-msg chat-msg-assistant chat-msg-typing-only">
              <div className="chat-typing" aria-live="polite" aria-busy="true">
                <span /><span /><span />
              </div>
            </div>
          ) : null}

          <div ref={bottomRef} />
        </div>
        </div>

        <div className="admin-chat-input-area admin-chat-input-area--pill">
          <div className="admin-chat-composer">
            <textarea
              ref={inputRef}
              className="admin-chat-composer-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Mesajınızı yazın…"
              rows={1}
              disabled={loading}
            />
            <button
              type="button"
              className="admin-chat-composer-send"
              onClick={() => send()}
              disabled={loading || !input.trim()}
              aria-label="Gönder"
            >
              {loading ? <span className="admin-chat-composer-dots">…</span> : <IconArrowUp />}
            </button>
          </div>
          <p className="admin-chat-composer-hint">Enter gönderir · Shift+Enter satır kırar</p>
        </div>
      </div>
    </div>
  )
}
