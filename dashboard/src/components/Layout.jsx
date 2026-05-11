import { NavLink, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { getDashboardStats } from '../api.js'

const NAV = [
  { to: '/',          icon: '📊', label: 'Genel Bakış'  },
  { to: '/orders',    icon: '📦', label: 'Siparişler'   },
  { to: '/cargo',     icon: '🚚', label: 'Kargo'        },
  { to: '/inventory', icon: '🗂️', label: 'Stok'         },
  { to: '/tickets',   icon: '🎫', label: 'Biletler',  badge: 'openTickets' },
  { to: '/reports',   icon: '📄', label: 'AI Raporlar' },
]

const PAGE_TITLES = {
  '/':          { title: 'Genel Bakış',  sub: 'Günlük operasyonel özet' },
  '/orders':    { title: 'Siparişler',   sub: 'Tüm sipariş yönetimi'   },
  '/cargo':     { title: 'Kargo',        sub: 'Sevkiyat ve teslimat takibi' },
  '/inventory': { title: 'Stok',         sub: 'Ürün ve envanter yönetimi' },
  '/tickets':   { title: 'Biletler',     sub: 'İnsan incelemesi gerektiren durumlar' },
  '/reports':   { title: 'AI Raporlar',  sub: 'LLM destekli yönetici raporları' },
}

export default function Layout({ children }) {
  const location = useLocation()
  const page = PAGE_TITLES[location.pathname] || { title: '', sub: '' }
  const [openTickets, setOpenTickets] = useState(0)

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
          {NAV.map(item => (
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
        </nav>

        <div className="sidebar-footer">
          v3.0 · LangGraph + FastAPI
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <div>
            <div className="topbar-title">{page.title}</div>
            <div className="topbar-sub">{page.sub}</div>
          </div>
        </div>
        <div className="content">
          {children}
        </div>
      </div>
    </div>
  )
}
