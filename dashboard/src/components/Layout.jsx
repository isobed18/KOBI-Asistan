import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState, useRef } from 'react'
import { getDashboardStats, getNotifications, markNotificationRead } from '../api.js'
import { useAuth } from '../context/AuthContext.jsx'

const NAV = [
  { to: '/',           icon: '📊', label: 'Genel Bakış'  },
  { to: '/orders',     icon: '📦', label: 'Siparişler'   },
  { to: '/cargo',      icon: '🚚', label: 'Kargo'        },
  { to: '/inventory',  icon: '🗂️', label: 'Stok'         },
  { to: '/tickets',    icon: '🎫', label: 'Biletler',  badge: 'openTickets' },
  { to: '/reports',    icon: '📄', label: 'AI Raporlar' },
  { to: '/assistant',  icon: '🤖', label: 'AI Asistan',  highlight: true },
]

const PAGE_TITLES = {
  '/':           { title: 'Genel Bakış',  sub: 'Günlük operasyonel özet' },
  '/orders':     { title: 'Siparişler',   sub: 'Tüm sipariş yönetimi'   },
  '/cargo':      { title: 'Kargo',        sub: 'Sevkiyat ve teslimat takibi' },
  '/inventory':  { title: 'Stok',         sub: 'Ürün ve envanter yönetimi' },
  '/tickets':    { title: 'Biletler',     sub: 'İnsan incelemesi gerektiren durumlar' },
  '/reports':    { title: 'AI Raporlar',  sub: 'LLM destekli yönetici raporları' },
  '/assistant':  { title: 'AI Asistan',   sub: 'Doğal dil ile stok, sipariş ve bilet yönetimi' },
}

// ---------------------------------------------------------------------------
// Notification Bell
// ---------------------------------------------------------------------------
function NotificationBell() {
  const [notifs, setNotifs] = useState([])
  const [open, setOpen]     = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const load = () => getNotifications().then(setNotifs).catch(() => {})
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [])

  // Dışarı tıklayınca kapat
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const unread = notifs.filter(n => !n.read).length

  const handleClick = (n) => {
    if (!n.read) {
      markNotificationRead(n.id).catch(() => {})
      setNotifs(prev => prev.map(x => x.id === n.id ? { ...x, read: true } : x))
    }
  }

  return (
    <div className="notif-bell-wrap" ref={ref}>
      <button
        className={`notif-bell-btn${unread > 0 ? ' has-unread' : ''}`}
        onClick={() => setOpen(o => !o)}
        title="Bildirimler"
      >
        🔔
        {unread > 0 && <span className="notif-badge">{unread > 9 ? '9+' : unread}</span>}
      </button>

      {open && (
        <div className="notif-dropdown">
          <div className="notif-header">
            <span>Bildirimler</span>
            {unread > 0 && <span style={{ fontSize: 11, color: 'var(--accent)' }}>{unread} yeni</span>}
          </div>
          <div className="notif-list">
            {notifs.length === 0 ? (
              <div className="notif-empty">Henüz bildirim yok</div>
            ) : notifs.map(n => (
              <div
                key={n.id}
                className={`notif-item${n.read ? '' : ' notif-unread'}`}
                onClick={() => handleClick(n)}
              >
                <div className="notif-item-title">{n.title}</div>
                <div className="notif-item-body">{n.body}</div>
                <div className="notif-item-ts">{n.ts}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Layout
// ---------------------------------------------------------------------------

export default function Layout({ children }) {
  const location = useLocation()
  const navigate  = useNavigate()
  const { user, logout } = useAuth()
  const page = PAGE_TITLES[location.pathname] || { title: '', sub: '' }
  const [openTickets, setOpenTickets] = useState(0)
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')

  // Apply theme to <html>
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark')

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  useEffect(() => {
    getDashboardStats()
      .then(d => setOpenTickets(d.tickets?.open ?? 0))
      .catch(() => {})
  }, [location.pathname])

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <h1>📦 KOBİ Asistan</h1>
          <p>Yönetici Paneli</p>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-label">Yönetim</div>
          {NAV.filter(i => !i.highlight).map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            >
              <span className="icon">{item.icon}</span>
              <span>{item.label}</span>
              {item.badge === 'openTickets' && openTickets > 0 && (
                <span className="nav-badge">{openTickets}</span>
              )}
            </NavLink>
          ))}
          <div className="nav-section-label" style={{ marginTop: 8 }}>Asistan</div>
          {NAV.filter(i => i.highlight).map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-item nav-item-highlight${isActive ? ' active' : ''}`}
            >
              <span className="icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          v4.2 · LangGraph + FastAPI
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <div>
            <div className="topbar-title">{page.title}</div>
            <div className="topbar-sub">{page.sub}</div>
          </div>
          <div className="topbar-actions">
            <button
              className="btn btn-ghost btn-sm topbar-theme-btn"
              onClick={toggleTheme}
              title={theme === 'dark' ? 'Açık tema' : 'Koyu tema'}
            >
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
            <NotificationBell />
            {user && (
              <div className="topbar-user">
                <span className="topbar-user-name">👤 {user.full_name || user.username}</span>
                <button className="btn btn-ghost btn-sm" onClick={handleLogout} title="Çıkış yap">
                  ⏏ Çıkış
                </button>
              </div>
            )}
          </div>
        </div>
        <div className="content">
          {children}
        </div>
      </div>
    </div>
  )
}
