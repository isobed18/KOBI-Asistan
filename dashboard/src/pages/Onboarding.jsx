import { motion } from 'framer-motion'
import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  approveVisualCandidate,
  duplicateVisualCandidate,
  loginUser,
  registerTenantSetup,
  rejectVisualCandidate,
  uploadVisualStockBatch,
} from '../api.js'
import { useAuth } from '../context/AuthContext.jsx'

const BUSINESS_TYPES = [
  { id: 'giyim', title: 'Giyim / butik', subtitle: 'FashionCLIP ile görsel ürün arama, beden rehberi ve stil odaklı müşteri cevapları.', active: true },
  { id: 'gida', title: 'Gıda / paketli ürün', subtitle: 'İçerik ve alerjen bilgisine göre güvenli ürün danışmanlığı.' },
  { id: 'cicek', title: 'Çiçek / hediye', subtitle: 'Özel gün önerileri ve görsel buket eşleştirme akışı.' },
]

const DEMO_FILES = [
  'pieces-leather-boot-102049118_4.jpg',
  'topshop-moto-vintage-boyfriend-jeans-100014086_2.jpg',
  'givenchy-leather-medium-antigona-duffel-black-100002074_3.jpg',
  'vintage-pearl-feather-earrings-100560058_7.jpg',
  'long-sleeve-simple-blouse-100445477_1.jpg',
  'red-tartan-check-skater-skirt-100361260_2.jpg',
  'classic-flat-shoes-100566397_3.jpg',
  'beige-crystal-sandals-100050716_2.jpg',
]

const DEMO_DIR = 'D:\\projects\\kobi_asistan\\demo_assets\\polyvore'

function uniqueDemoSuffix() {
  return String(Date.now()).slice(-5)
}

function seedDraft(candidate) {
  return {
    name: candidate.suggested_name || '',
    category: candidate.suggested_category || 'Giyim',
    price: '',
    stock_quantity: candidate.suggested_stock || 12,
    low_stock_threshold: 3,
    visual_keywords: candidate.visual_keywords || '',
    description: candidate.description || '',
    size_guide: '',
    ingredients: '',
    allergens: '',
    advisory_notes: '',
  }
}

function Field({ label, children, hint }) {
  return (
    <label className="setup-field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  )
}

function WizardProgress({ steps, step }) {
  const index = Math.max(0, steps.findIndex(item => item.id === step))
  const width = steps.length <= 1 ? 100 : (index / (steps.length - 1)) * 100

  return (
    <div className="setup-wizard-progress" aria-label="Kurulum ilerlemesi">
      <div className="setup-progress-head">
        <strong>{steps[index]?.title}</strong>
        <span>{index + 1}/{steps.length}</span>
      </div>
      <div className="setup-progress-track">
        <div className="setup-progress-fill" style={{ width: `${width}%` }} />
      </div>
      <div className="setup-progress-steps">
        {steps.map((item, itemIndex) => (
          <span key={item.id} className={itemIndex <= index ? 'active' : ''}>{item.title}</span>
        ))}
      </div>
    </div>
  )
}

function RegisterStep({ businessType, setBusinessType, onCreated }) {
  const suffix = useMemo(uniqueDemoSuffix, [])
  const [form, setForm] = useState({
    business_name: `Yeni Butik ${suffix.slice(-2)}`,
    owner_name: 'Mina Yılmaz',
    username: `butik_${suffix}`,
    password: 'demo1234',
    owner_notes: 'Modern, sade ve güven veren bir butik. Genç profesyonellere rahat ama şık kombinler öneriyoruz.',
    communication_rules: 'Müşteriye her zaman nazik ve sakin hitap et.\nEmoji kullanma.\nBeden konusunda emin değilsen ölçü iste.\nStok yoksa alternatif ürün öner.',
  })
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState('')

  const set = (key, value) => setForm(prev => ({ ...prev, [key]: value }))

  const submit = async (event) => {
    event.preventDefault()
    setLoading(true)
    setMsg('')
    try {
      const res = await registerTenantSetup({ ...form, business_type: businessType })
      const auth = await loginUser(form.username.trim().toLowerCase(), form.password)
      onCreated?.(res, auth)
    } catch (e) {
      setMsg(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.section className="setup-screen" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.38 }}>
      <div className="setup-screen-intro">
        <span className="setup-eyebrow">KOBİ kurulumu</span>
        <h1>Önce işletme hesabını oluşturalım.</h1>
        <p>Bu adım admin hesabını, işletme tipini ve müşterilerle nasıl konuşulacağını belirleyen agent notlarını hazırlar.</p>
      </div>

      <form className="setup-screen-grid" onSubmit={submit}>
        <div className="setup-panel setup-panel-large">
          <h2>Hesap bilgileri</h2>
          <div className="setup-form-grid setup-form-grid--two">
            <Field label="İşletme adı">
              <input value={form.business_name} onChange={e => set('business_name', e.target.value)} required />
            </Field>
            <Field label="Yetkili adı">
              <input value={form.owner_name} onChange={e => set('owner_name', e.target.value)} required />
            </Field>
            <Field label="Kullanıcı adı">
              <input value={form.username} onChange={e => set('username', e.target.value)} required />
            </Field>
            <Field label="Şifre">
              <input type="password" value={form.password} onChange={e => set('password', e.target.value)} minLength={6} required />
            </Field>
          </div>

          <div className="business-type-grid">
            {BUSINESS_TYPES.map(type => (
              <button
                type="button"
                key={type.id}
                className={`business-type-card${businessType === type.id ? ' selected' : ''}`}
                onClick={() => setBusinessType(type.id)}
              >
                <strong>{type.title}</strong>
                <span>{type.subtitle}</span>
                {type.active && <em>Video için seçeceğiz</em>}
              </button>
            ))}
          </div>
        </div>

        <div className="setup-panel">
          <h2>Demo prompt burada dursun</h2>
          <Field label="KOBİ kendini nasıl tanımlar?" hint="Bu metin tenant config içine KOBİ notu olarak yazılır.">
            <textarea rows={6} value={form.owner_notes} onChange={e => set('owner_notes', e.target.value)} />
          </Field>
          <Field label="Müşteri iletişim kuralları" hint="Her satır agent prompt'una kural olarak eklenir.">
            <textarea rows={7} value={form.communication_rules} onChange={e => set('communication_rules', e.target.value)} />
          </Field>
          <button className="btn btn-primary setup-primary-action" type="submit" disabled={loading}>
            {loading ? 'Hesap oluşturuluyor...' : 'Hesabı oluştur ve ürün yüklemeye geç'}
          </button>
          {msg && <span className="setup-message setup-message-error">{msg}</span>}
        </div>
      </form>
    </motion.section>
  )
}

function DemoFileGuide() {
  return (
    <div className="setup-demo-files">
      <div>
        <h3>Demo için yüklenecek örnekler</h3>
        <p>Bu klasörden 6-8 temiz moda ürünü seçin, tek seferde sürükleyip bırakın.</p>
        <code>{DEMO_DIR}</code>
      </div>
      <div className="setup-file-list">
        {DEMO_FILES.map(name => <span key={name}>{name}</span>)}
      </div>
    </div>
  )
}

function UploadStep({ businessType, files, previews, dragging, setDragging, pickFiles, inputRef, upload, busy, message, onSkip }) {
  return (
    <motion.section className="setup-screen" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.38 }}>
      <div className="setup-screen-intro">
        <span className="setup-eyebrow">Ürün yükleme</span>
        <h1>Şimdi ürün fotoğraflarını tanıtalım.</h1>
        <p>Tüm fotoğrafları tek seferde bırakın. {businessType === 'giyim' ? 'Giyim için FashionCLIP kullanılır; ürün tipi, görsel anahtar kelime ve katalog adayı çıkarılır.' : 'Sistem işletme tipine göre görsel adayları hazırlar.'}</p>
      </div>

      <div className="setup-panel setup-upload-panel">
        <DemoFileGuide />
        <div
          className={`drop-zone${dragging ? ' dragging' : ''}`}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={e => { e.preventDefault(); setDragging(false); pickFiles(e.dataTransfer.files) }}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
        >
          <input ref={inputRef} type="file" multiple accept="image/*" onChange={e => pickFiles(e.target.files)} hidden />
          <strong>Ürün fotoğraflarını buraya bırakın</strong>
          <span>veya Polyvore demo klasöründen seçmek için tıklayın</span>
        </div>
        {previews.length > 0 && (
          <div className="upload-preview-grid">
            {previews.slice(0, 12).map(({ file, url }) => (
              <div className="upload-preview" key={`${file.name}-${file.size}`}><img src={url} alt={file.name} /><span>{file.name}</span></div>
            ))}
          </div>
        )}
        <div className="setup-actions-row">
          <button className="btn btn-primary" type="button" onClick={upload} disabled={busy || !files.length}>
            {busy ? 'Sınıflandırılıyor...' : 'Görselleri sınıflandır'}
          </button>
          <button className="btn" type="button" onClick={onSkip}>Bu adımı geç</button>
          {message && <span className="setup-message">{message}</span>}
        </div>
      </div>
    </motion.section>
  )
}

function CandidateCard({ candidate, draft, onChange, onApprove, onReject, onDuplicate, busy }) {
  const confidence = Math.round((candidate.confidence || 0) * 100)
  return (
    <motion.div
      className={`setup-candidate${candidate.status === 'approved' ? ' approved' : ''}${candidate.status === 'rejected' ? ' rejected' : ''}`}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28 }}
    >
      <div className="setup-candidate-image">
        {candidate.image_url ? <img src={candidate.image_url} alt={draft.name || 'Ürün adayı'} /> : <span>Görsel</span>}
      </div>
      <div className="setup-candidate-body">
        <div className="setup-candidate-top">
          <div>
            <div className="setup-candidate-kicker">{candidate.classifier}</div>
            <h3>{draft.name || 'İsimsiz ürün'}</h3>
          </div>
          <span className="setup-confidence">{confidence}%</span>
        </div>
        <div className="setup-form-grid">
          <Field label="Ürün adı"><input value={draft.name} onChange={e => onChange('name', e.target.value)} /></Field>
          <Field label="Kategori"><input value={draft.category} onChange={e => onChange('category', e.target.value)} /></Field>
          <Field label="Fiyat"><input type="number" min="0" value={draft.price} onChange={e => onChange('price', e.target.value)} placeholder="899" /></Field>
          <Field label="Stok"><input type="number" min="0" value={draft.stock_quantity} onChange={e => onChange('stock_quantity', e.target.value)} /></Field>
        </div>
        <Field label="Ürün açıklaması" hint="Kumaş, kalıp, stil, sezon ve kullanım alanı. Müşteri sorularında bu bilgiler kullanılır.">
          <textarea value={draft.description} onChange={e => onChange('description', e.target.value)} rows={3} />
        </Field>
        <Field label="Beden rehberi" hint="Örnek: S 34-36, M 38-40, L 42-44. Müşteri beden sorduğunda buradan cevaplanır.">
          <textarea value={draft.size_guide} onChange={e => onChange('size_guide', e.target.value)} rows={2} placeholder="S: 34-36, M: 38-40, L: 42-44. Kalıp rahat; aradaysanız bir beden büyük seçin." />
        </Field>
        <Field label="Görsel anahtar kelimeler">
          <input value={draft.visual_keywords} onChange={e => onChange('visual_keywords', e.target.value)} />
        </Field>
        <div className="setup-candidate-actions">
          <button className="btn btn-sm" type="button" disabled={busy || candidate.status === 'rejected'} onClick={onReject}>Reddet</button>
          <button className="btn btn-sm" type="button" disabled={busy} onClick={onDuplicate}>Varyant oluştur</button>
          <button className="btn btn-primary btn-sm" type="button" disabled={busy || candidate.status === 'approved'} onClick={onApprove}>
            {candidate.status === 'approved' ? 'Onaylandı' : 'Ürünü onayla'}
          </button>
        </div>
      </div>
    </motion.div>
  )
}

function ReviewStep({ batch, drafts, setCandidateDraft, approve, reject, duplicate, busy, message, onDone }) {
  return (
    <motion.section className="setup-screen setup-screen-review" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.38 }}>
      <div className="setup-screen-intro setup-screen-intro-row">
        <div>
          <span className="setup-eyebrow">Katalog onayı</span>
          <h1>Bulunan ürünleri tek tek netleştirin.</h1>
          <p>Fiyat, stok ve beden rehberini doldurun. Varyant oluştur butonu aynı görselden farklı beden/renk kayıtlarını hızlıca açar.</p>
        </div>
        <button className="btn btn-primary" type="button" onClick={onDone}>Kurulumu bitir</button>
      </div>
      {message && <span className="setup-message">{message}</span>}
      <div className="setup-candidates">
        {(batch?.candidates || []).map(candidate => (
          <CandidateCard
            key={candidate.id}
            candidate={candidate}
            draft={drafts[candidate.id] || seedDraft(candidate)}
            onChange={(key, value) => setCandidateDraft(candidate.id, key, value)}
            onApprove={() => approve(candidate)}
            onReject={() => reject(candidate)}
            onDuplicate={() => duplicate(candidate)}
            busy={busy}
          />
        ))}
      </div>
    </motion.section>
  )
}

function DoneStep({ createdTenant }) {
  const navigate = useNavigate()
  return (
    <motion.section className="setup-screen setup-screen-done" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.42 }}>
      <div className="setup-done-card">
        <span className="setup-eyebrow">Kurulum hazır</span>
        <h1>{createdTenant?.business_name || 'İşletmeniz'} için asistan çalışmaya hazır.</h1>
        <p>Şimdi günün özetine geçebilirsiniz. Demo videosunda buradan dolu demo hesaba geçip sipariş, stok, kargo, rapor ve müdahale akışlarını göstereceğiz.</p>
        <div className="telegram-script-grid">
          <div><strong>Görsel arama</strong><p>Müşteri ürün fotoğrafı gönderir, sistem katalogdan benzeri bulur.</p></div>
          <div><strong>Beden sorusu</strong><p>Ürün beden rehberi varsa LLM ürüne göre cevap verir.</p></div>
          <div><strong>Sipariş akışı</strong><p>Butonlu intent akışı LLM olmadan siparişe ilerler.</p></div>
          <div><strong>İptal talebi</strong><p>OTP sonrası yönetici müdahalesine ticket düşer.</p></div>
        </div>
        <button className="btn btn-primary setup-primary-action" type="button" onClick={() => navigate('/')}>Günün özetine geç</button>
      </div>
    </motion.section>
  )
}

export default function Onboarding({ publicMode = false }) {
  const inputRef = useRef(null)
  const { isAuthenticated, login } = useAuth()
  const [businessType, setBusinessType] = useState('giyim')
  const [files, setFiles] = useState([])
  const [dragging, setDragging] = useState(false)
  const [batch, setBatch] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [createdTenant, setCreatedTenant] = useState(null)
  const [step, setStep] = useState(publicMode ? 'account' : 'upload')

  const steps = publicMode
    ? [
        { id: 'account', title: 'Hesap' },
        { id: 'upload', title: 'Ürün yükle' },
        { id: 'review', title: 'Katalog' },
        { id: 'done', title: 'Hazır' },
      ]
    : [
        { id: 'upload', title: 'Ürün yükle' },
        { id: 'review', title: 'Katalog' },
        { id: 'done', title: 'Hazır' },
      ]

  const previews = useMemo(() => files.map(file => ({ file, url: URL.createObjectURL(file) })), [files])
  const canUpload = isAuthenticated

  const setCandidateDraft = (id, key, value) => setDrafts(prev => ({ ...prev, [id]: { ...prev[id], [key]: value } }))

  const pickFiles = (list) => {
    const imageFiles = Array.from(list || []).filter(file => file.type.startsWith('image/'))
    setFiles(imageFiles)
    setMessage(imageFiles.length ? `${imageFiles.length} görsel hazır.` : 'Sadece görsel dosyaları kabul edilir.')
  }

  const handleCreated = (tenant, auth) => {
    login(auth.access_token, auth.user)
    setCreatedTenant(tenant)
    setMessage(`${tenant.business_name} hesabı oluşturuldu. Şimdi ürün fotoğraflarını yükleyebilirsiniz.`)
    setStep('upload')
  }

  const upload = async () => {
    if (!canUpload) {
      setMessage('Ürün yüklemek için önce hesap oluşturun. Otomatik girişten sonra bu adım açılır.')
      return
    }
    if (!files.length) {
      setMessage('Önce ürün görsellerini ekleyin.')
      return
    }
    setBusy(true)
    setMessage('FashionCLIP görselleri sınıflandırıyor...')
    try {
      const res = await uploadVisualStockBatch({ businessType, files })
      setBatch(res)
      const nextDrafts = {}
      for (const c of res.candidates || []) nextDrafts[c.id] = seedDraft(c)
      setDrafts(nextDrafts)
      setMessage(`${res.candidate_count} ürün adayı oluşturuldu. Düzenleyip onaylayabilirsiniz.`)
      setStep('review')
    } catch (e) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }

  const payloadFor = (candidate) => {
    const draft = drafts[candidate.id]
    return {
      ...draft,
      price: Number(draft.price || 0),
      stock_quantity: Number(draft.stock_quantity || 0),
      low_stock_threshold: Number(draft.low_stock_threshold || 3),
    }
  }

  const approve = async (candidate) => {
    setBusy(true)
    try {
      await approveVisualCandidate(candidate.id, payloadFor(candidate))
      setBatch(prev => ({ ...prev, candidates: prev.candidates.map(c => c.id === candidate.id ? { ...c, status: 'approved' } : c) }))
      setMessage(`${drafts[candidate.id].name} kataloğa eklendi.`)
    } catch (e) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }

  const duplicate = async (candidate) => {
    const base = payloadFor(candidate)
    const suffix = window.prompt('Varyant adı / beden etiketi', 'M beden') || 'Varyant'
    setBusy(true)
    try {
      await duplicateVisualCandidate(candidate.id, { ...base, name: `${base.name} - ${suffix}` })
      setMessage(`${base.name} için ${suffix} varyantı kataloğa eklendi.`)
    } catch (e) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }

  const reject = async (candidate) => {
    setBusy(true)
    try {
      await rejectVisualCandidate(candidate.id, 'Kurulum incelemesinde reddedildi')
      setBatch(prev => ({ ...prev, candidates: prev.candidates.map(c => c.id === candidate.id ? { ...c, status: 'rejected' } : c) }))
      setMessage(`${drafts[candidate.id]?.name || 'Ürün adayı'} reddedildi.`)
    } catch (e) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`setup-page setup-page-wizard${publicMode ? ' setup-page-public' : ''}`}>
      <WizardProgress steps={steps} step={step} />

      {step === 'account' && (
        <RegisterStep
          businessType={businessType}
          setBusinessType={setBusinessType}
          onCreated={handleCreated}
        />
      )}

      {step === 'upload' && (
        <UploadStep
          businessType={businessType}
          files={files}
          previews={previews}
          dragging={dragging}
          setDragging={setDragging}
          pickFiles={pickFiles}
          inputRef={inputRef}
          upload={upload}
          busy={busy}
          message={message}
          onSkip={() => setStep('done')}
        />
      )}

      {step === 'review' && (
        <ReviewStep
          batch={batch}
          drafts={drafts}
          setCandidateDraft={setCandidateDraft}
          approve={approve}
          reject={reject}
          duplicate={duplicate}
          busy={busy}
          message={message}
          onDone={() => setStep('done')}
        />
      )}

      {step === 'done' && <DoneStep createdTenant={createdTenant} />}
    </div>
  )
}
