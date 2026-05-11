import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate  = useNavigate()
  const location  = useLocation()
  const from = location.state?.from?.pathname || '/'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!username || !password) return
    setLoading(true)
    setError('')

    try {
      // OAuth2PasswordRequestForm — application/x-www-form-urlencoded
      const body = new URLSearchParams({ username, password })
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString(),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Giriş başarısız' }))
        setError(err.detail || 'Giriş başarısız')
        return
      }
      const data = await res.json()
      login(data.access_token, data.user)
      navigate(from, { replace: true })
    } catch (e) {
      setError('Sunucuya bağlanılamadı.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <div className="login-logo-icon">📦</div>
          <h1>KOBİ Asistan</h1>
          <p>Yönetici Paneli</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label className="form-label">Kullanıcı Adı</label>
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

          {error && (
            <div className="login-error">
              ⚠️ {error}
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: '100%', marginTop: 8, padding: '10px 0', fontSize: 15 }}
            disabled={loading || !username || !password}
          >
            {loading ? '⏳ Giriş yapılıyor…' : '🔐 Giriş Yap'}
          </button>
        </form>

        <div style={{ marginTop: 20, fontSize: 12, color: 'var(--text3)', textAlign: 'center' }}>
          v4.2 · LangGraph + FastAPI
        </div>
      </div>
    </div>
  )
}
