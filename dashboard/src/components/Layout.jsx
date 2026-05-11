import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import { getDashboardStats, getNotifications, markNotificationRead } from '../api.js'
import { useAuth } from '../context/AuthContext.jsx'

function IconSun(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  )
}

function IconMoon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  )
}

function IconBell(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  )
}

function IconLogOut(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  )
}

const NAV = [
  { to: '/',          icon: '◌', label: 'Bugun' },
  { to: '/assistant', icon: '✦', label: 'AI Asistan', highlight: true },
  { to: '/tickets',   icon: '!', label: 'Mudahale', badge: 'openTickets' },
  { to: '/orders',    icon: '□', label: 'Siparisler' },
  { to: '/inventory', icon: '▥', label: 'Stok' },
  { to: '/cargo',     icon: '→', label: 'Kargo' },
  { to: '/reports',   icon: '▤', label: 'Raporlar' },
]

const PAGE_TITLES = {
  '/':          { title: 'Bugun', sub: 'Sistem isletmenizi izliyor ve oncelikleri one cikariyor' },
  '/assistant': { title: 'AI Asistan', sub: 'Dogal dil ile stok, siparis ve bilet yonetimi' },
  '/tickets':   { title: 'Mudahale', sub: 'Insan onayi bekleyen konular' },
  '/orders':    { title: 'Siparisler', sub: 'Hazirlik, kargo ve teslim surecleri' },
  '/inventory': { title: 'Stok', sub: 'Kritik stok ve yenileme akislari' },
  '/cargo':     { title: 'Kargo', sub: 'Gecikme ve teslimat sinyalleri' },
  '/reports':   { title: 'Raporlar', sub: 'AI brifingleri ve icgoruler' },
}

function NotificationBell() {
  const [notifs, setNotifs] = useState([])
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const load = () => getNotifications().then(setNotifs).catch(() => {})
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const handler = (event) => {
      if (ref.current && !ref.current.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const unread = notifs.filter(n => !n.read).length

  const handleClick = (notification) => {
    if (!notification.read) {
      markNotificationRead(notification.id).catch(() => {})
      setNotifs(prev => prev.map(n => n.id === notification.id ? { ...n, read: true } : n))
    }
  }

  return (
    <div className="notif-bell-wrap" ref={ref}>
      <button type="button" className={`notif-bell-btn${unread > 0 ? ' has-unread' : ''}`} onClick={() => setOpen(v => !v)} title="Bildirimler" aria-label="Bildirimler">
        <IconBell />
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
              <div className="notif-empty">Henuz bildirim yok</div>
            ) : notifs.map(n => (
              <div key={n.id} className={`notif-item${n.read ? '' : ' notif-unread'}`} onClick={() => handleClick(n)}>
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

export default function Layout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const page = PAGE_TITLES[location.pathname] || { title: '', sub: '' }
  const [openTickets, setOpenTickets] = useState(0)
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  useEffect(() => {
    getDashboardStats().then(d => setOpenTickets(d.tickets?.open ?? 0)).catch(() => {})
  }, [location.pathname])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const business = user?.tenant?.business_name || 'KOBI Asistan'

  return (
    <div className="layout command-shell">
      <aside className="sidebar command-sidebar">
        <div className="sidebar-logo command-logo">
          <h1>{business}</h1>
          <p>Otomasyon merkezi</p>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-label">Akis</div>
          {NAV.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => `nav-item${item.highlight ? ' nav-item-highlight' : ''}${isActive ? ' active' : ''}`}
            >
              <span className="icon">{item.icon}</span>
              <span>{item.label}</span>
              {item.badge === 'openTickets' && openTickets > 0 && <span className="nav-badge">{openTickets}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">v4.3 · tenant-aware</div>
      </aside>

      <div className="main">
        <div className="topbar command-topbar">
          <div>
            <div className="topbar-title">{page.title}</div>
            <div className="topbar-sub">{page.sub}</div>
          </div>
          <div className="topbar-actions">
            <button
              type="button"
              className="theme-toggle"
              onClick={() => setTheme(t => (t === 'dark' ? 'light' : 'dark'))}
              title={theme === 'dark' ? 'Aydinlik temaya gec' : 'Karanlik temaya gec'}
              aria-label={theme === 'dark' ? 'Aydinlik temaya gec' : 'Karanlik temaya gec'}
            >
              <span className={`theme-toggle-slot${theme === 'light' ? ' active' : ''}`} aria-hidden>
                <IconSun />
              </span>
              <span className={`theme-toggle-slot${theme === 'dark' ? ' active' : ''}`} aria-hidden>
                <IconMoon />
              </span>
            </button>
            {user ? (
              <div className="topbar-user">
                <span className="topbar-user-name">{user.full_name || user.username}</span>
                <NotificationBell />
                <button type="button" className="btn btn-sm btn-logout" onClick={handleLogout} title="Oturumu kapat">
                  <IconLogOut />
                  Çıkış
                </button>
              </div>
            ) : (
              <NotificationBell />
            )}
          </div>
        </div>
        <div className="content command-content">{children}</div>
      </div>
    </div>
  )
}
