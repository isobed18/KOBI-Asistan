import { useEffect, useState } from 'react'
import { getReports, getReport, generateReport } from '../api.js'

function fmtDate(s) {
  return s ? new Date(s).toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
}

function MarkdownText({ text }) {
  if (!text) return null
  const lines = text.split('\n')
  return (
    <div className="report-text">
      {lines.map((line, i) => {
        if (line.startsWith('## ')) {
          return <h2 key={i}>{line.slice(3)}</h2>
        }
        if (line.startsWith('# ')) {
          return <h2 key={i} style={{ fontSize: 17 }}>{line.slice(2)}</h2>
        }
        if (line.startsWith('- ') || line.startsWith('* ')) {
          return <div key={i} style={{ paddingLeft: 16, color: 'var(--text)' }}>• {line.slice(2)}</div>
        }
        if (line.startsWith('**') && line.endsWith('**')) {
          return <div key={i} style={{ fontWeight: 600 }}>{line.slice(2, -2)}</div>
        }
        if (!line.trim()) return <div key={i} style={{ height: 8 }} />
        return <div key={i}>{line}</div>
      })}
    </div>
  )
}

export default function Reports() {
  const [reports, setReports]       = useState([])
  const [selected, setSelected]     = useState(null)
  const [selectedFull, setSelectedFull] = useState(null)
  const [loading, setLoading]       = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError]           = useState(null)
  const [genResult, setGenResult]   = useState(null)

  const load = () => {
    setLoading(true)
    getReports()
      .then(d => { setReports(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const openReport = async (id) => {
    setSelected(id)
    setSelectedFull(null)
    try {
      const r = await getReport(id)
      setSelectedFull(r)
    } catch (e) {
      setSelectedFull({ error: e.message })
    }
  }

  const generate = async () => {
    setGenerating(true)
    setGenResult(null)
    try {
      const r = await generateReport()
      setGenResult({ ok: true, text: `Rapor #${r.report_id} oluşturuldu.` })
      load()
      setSelected(r.report_id)
      setSelectedFull(r)
    } catch (e) {
      setGenResult({ ok: false, text: e.message })
    } finally {
      setGenerating(false)
    }
  }

  return (
    <>
      <div className="card">
        <div className="section-row">
          <div>
            <div style={{ fontWeight: 600, fontSize: 15 }}>AI Destekli Günlük Raporlar</div>
            <div style={{ fontSize: 12, color: 'var(--text2)', marginTop: 2 }}>
              LLM, günlük sipariş + stok + kargo verilerini analiz ederek kapsamlı Türkçe rapor üretir.
              Sabah 08:00'de otomatik oluşturulur veya manuel tetiklenebilir.
            </div>
          </div>
          <button
            className="btn btn-primary"
            onClick={generate}
            disabled={generating}
          >
            {generating ? '⏳ Oluşturuluyor…' : '🤖 Şimdi Oluştur'}
          </button>
        </div>
        {genResult && (
          <div className={genResult.ok ? 'success-msg' : 'error-msg'} style={{ marginTop: 12 }}>
            {genResult.text}
          </div>
        )}
        {generating && (
          <div style={{ marginTop: 12, fontSize: 13, color: 'var(--text2)' }}>
            ⏳ LLM raporu hazırlıyor... Bu işlem 10-30 saniye sürebilir.
          </div>
        )}
      </div>

      <div className="grid-2" style={{ alignItems: 'flex-start' }}>
        {/* Report list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
            Geçmiş Raporlar
          </div>

          {error && <div className="error-msg">⚠️ {error}</div>}

          {loading ? (
            <div className="spinner" />
          ) : reports.length === 0 ? (
            <div className="empty-state" style={{ padding: '24px' }}>
              <div className="empty-icon" style={{ fontSize: 28 }}>📄</div>
              Henüz rapor yok. "Şimdi Oluştur"a tıklayın.
            </div>
          ) : (
            reports.map(r => (
              <div
                key={r.id}
                className="report-preview-card"
                style={selected === r.id ? { borderColor: 'var(--accent)', background: 'rgba(59,130,246,.06)' } : {}}
                onClick={() => openReport(r.id)}
              >
                <div className="report-date">
                  📅 {r.date} · {fmtDate(r.created_at)}
                </div>
                <div className="report-preview">{r.preview}…</div>
              </div>
            ))
          )}
        </div>

        {/* Report detail */}
        <div>
          {selected == null ? (
            <div className="card" style={{ textAlign: 'center', padding: 48 }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>📄</div>
              <div style={{ color: 'var(--text3)', fontSize: 13 }}>Soldaki listeden bir rapor seçin</div>
            </div>
          ) : !selectedFull ? (
            <div className="spinner" />
          ) : selectedFull.error ? (
            <div className="error-msg">⚠️ {selectedFull.error}</div>
          ) : (
            <div className="card">
              <div className="section-row" style={{ marginBottom: 16 }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15 }}>Rapor #{selectedFull.id}</div>
                  <div style={{ fontSize: 12, color: 'var(--text2)' }}>{selectedFull.date} · {fmtDate(selectedFull.created_at)}</div>
                </div>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => navigator.clipboard.writeText(selectedFull.report_text)}
                >
                  📋 Kopyala
                </button>
              </div>
              <MarkdownText text={selectedFull.report_text} />
            </div>
          )}
        </div>
      </div>

      {/* Info card */}
      <div className="card" style={{ background: 'rgba(59,130,246,.05)', borderColor: 'rgba(59,130,246,.2)' }}>
        <div className="card-title" style={{ color: 'var(--accent)' }}>🤖 LLM Rapor Mimarisi</div>
        <p style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.6 }}>
          Rapor oluşturma akışı: <strong>(1)</strong> Gerçek zamanlı veri toplama — sipariş özeti, kritik stok,
          geciken kargolar. <strong>(2)</strong> Veri LLM'e yapılandırılmış prompt ile gönderilir.
          <strong> (3)</strong> LLM (Ollama/OpenAI/Claude/Gemini — <code>LLM_PROVIDER</code> ile seçilir)
          Türkçe markdown rapor üretir. <strong>(4)</strong> Rapor veritabanına kaydedilir, sonraki günlerde
          geçmiş analizler için erişilebilir olur.
        </p>
      </div>
    </>
  )
}
