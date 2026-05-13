import { motion } from 'framer-motion'
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { loginUser } from '../api.js'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = location.state?.from?.pathname || '/'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

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
