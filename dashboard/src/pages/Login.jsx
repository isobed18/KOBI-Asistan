import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { loginUser } from '../api.js'
import { useAuth } from '../context/AuthContext'

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

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = location.state?.from?.pathname || '/'
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light')

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!username || !password) return
    setLoading(true)
    setError('')

    try {
      const data = await loginUser(username, password)
      login(data.access_token, data.user)
      navigate(from, { replace: true })
    } catch (e) {
      setError(e.message || 'Sunucuya bağlanılamadı.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page calm-login-page">
      <button
        type="button"
        className="theme-toggle login-theme-toggle"
        onClick={() => setTheme(t => (t === 'dark' ? 'light' : 'dark'))}
        title={theme === 'dark' ? 'Aydınlık temaya geç' : 'Karanlık temaya geç'}
        aria-label={theme === 'dark' ? 'Aydınlık temaya geç' : 'Karanlık temaya geç'}
      >
        <span className={`theme-toggle-slot${theme === 'light' ? ' active' : ''}`} aria-hidden>
          <IconSun />
        </span>
        <span className={`theme-toggle-slot${theme === 'dark' ? ' active' : ''}`} aria-hidden>
          <IconMoon />
        </span>
      </button>
      <motion.div
        className="login-card calm-login-card"
        initial={{ opacity: 0, scale: 0.97, y: 18 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.48, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="login-logo calm-login-logo">
          <span className="calm-login-orb" />
          <h1>İşiniz izleniyor.</h1>
          <p>Önemli kararlar için giriş yapın.</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label className="form-label">Kullanıcı adı</label>
            <input
              className="form-control"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="admin"
              autoFocus
              disabled={loading}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Şifre</label>
            <input
              className="form-control"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              disabled={loading}
            />
          </div>
          {error && <div className="login-error">{error}</div>}
          <button type="submit" className="btn btn-primary calm-login-button" disabled={loading || !username || !password}>
            {loading ? 'Hazırlanıyor...' : 'Devam et'}
          </button>
          <button type="button" className="btn calm-login-button" onClick={() => navigate('/register')} disabled={loading}>
            Yeni KOBİ hesabı oluştur
          </button>
        </form>
      </motion.div>
    </div>
  )
}
