import { motion } from 'framer-motion'
import { useMemo, useRef, useState } from 'react'
import {
  approveVisualCandidate,
  rejectVisualCandidate,
  uploadVisualStockBatch,
} from '../api.js'

const BUSINESS_TYPES = [
  {
    id: 'giyim',
    title: 'Clothing / boutique',
    subtitle: 'FashionCLIP image search, size guidance, outfit-style answers.',
    active: true,
  },
  {
    id: 'gida',
    title: 'Food / packaged goods',
    subtitle: 'Allergen-aware product answers and ingredient guidance.',
  },
  {
    id: 'cicek',
    title: 'Flowers / gifts',
    subtitle: 'Occasion suggestions and visual bouquet matching.',
  },
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

function DemoFileGuide() {
  return (
    <div className="setup-demo-files">
      <div>
        <h3>Demo icin yuklenecek ornekler</h3>
        <p>Bu klasorden 6-8 temiz moda urunu secin, tek seferde surukleyip birakin.</p>
        <code>{DEMO_DIR}</code>
      </div>
      <div className="setup-file-list">
        {DEMO_FILES.map(name => <span key={name}>{name}</span>)}
      </div>
    </div>
  )
}

function CandidateCard({ candidate, draft, onChange, onApprove, onReject, busy }) {
  const confidence = Math.round((candidate.confidence || 0) * 100)
  const imageSrc = candidate.image_url
  return (
    <motion.div
      className={`setup-candidate${candidate.status === 'approved' ? ' approved' : ''}${candidate.status === 'rejected' ? ' rejected' : ''}`}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28 }}
    >
      <div className="setup-candidate-image">
        {imageSrc ? <img src={imageSrc} alt={draft.name || 'Product candidate'} /> : <span>Image</span>}
      </div>
      <div className="setup-candidate-body">
        <div className="setup-candidate-top">
          <div>
            <div className="setup-candidate-kicker">{candidate.classifier}</div>
            <h3>{draft.name || 'Unnamed product'}</h3>
          </div>
          <span className="setup-confidence">{confidence}%</span>
        </div>
        <div className="setup-form-grid">
          <Field label="Product name">
            <input value={draft.name} onChange={e => onChange('name', e.target.value)} />
          </Field>
          <Field label="Category">
            <input value={draft.category} onChange={e => onChange('category', e.target.value)} />
          </Field>
          <Field label="Price">
            <input type="number" min="0" value={draft.price} onChange={e => onChange('price', e.target.value)} placeholder="899" />
          </Field>
          <Field label="Stock">
            <input type="number" min="0" value={draft.stock_quantity} onChange={e => onChange('stock_quantity', e.target.value)} />
          </Field>
        </div>
        <Field label="Description" hint="Demo: fabric, fit, style, suitable season. Customer questions will use this context.">
          <textarea value={draft.description} onChange={e => onChange('description', e.target.value)} rows={3} />
        </Field>
        <Field label="Size guide" hint="Example: S 34-36, M 38-40, L 42-44. This powers 'which size fits me?' answers.">
          <textarea value={draft.size_guide} onChange={e => onChange('size_guide', e.target.value)} rows={2} placeholder="S: 34-36, M: 38-40, L: 42-44. Oversize fit." />
        </Field>
        <Field label="Visual keywords">
          <input value={draft.visual_keywords} onChange={e => onChange('visual_keywords', e.target.value)} />
        </Field>
        <div className="setup-candidate-actions">
          <button className="btn btn-sm" type="button" disabled={busy || candidate.status === 'rejected'} onClick={onReject}>
            Reject
          </button>
          <button className="btn btn-primary btn-sm" type="button" disabled={busy || candidate.status === 'approved'} onClick={onApprove}>
            {candidate.status === 'approved' ? 'Approved' : 'Approve product'}
          </button>
        </div>
      </div>
    </motion.div>
  )
}

export default function Onboarding() {
  const inputRef = useRef(null)
  const [businessType, setBusinessType] = useState('giyim')
  const [files, setFiles] = useState([])
  const [dragging, setDragging] = useState(false)
  const [batch, setBatch] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const previews = useMemo(() => files.map(file => ({
    file,
    url: URL.createObjectURL(file),
  })), [files])

  const setCandidateDraft = (id, key, value) => {
    setDrafts(prev => ({ ...prev, [id]: { ...prev[id], [key]: value } }))
  }

  const pickFiles = (list) => {
    const imageFiles = Array.from(list || []).filter(file => file.type.startsWith('image/'))
    setFiles(imageFiles)
    setMessage(imageFiles.length ? `${imageFiles.length} image ready.` : 'Only image files are accepted.')
  }

  const upload = async () => {
    if (!files.length) {
      setMessage('Add product images first.')
      return
    }
    setBusy(true)
    setMessage('FashionCLIP is classifying the images...')
    try {
      const res = await uploadVisualStockBatch({ businessType, files })
      setBatch(res)
      const nextDrafts = {}
      for (const c of res.candidates || []) nextDrafts[c.id] = seedDraft(c)
      setDrafts(nextDrafts)
      setMessage(`${res.candidate_count} candidates created. Review, edit, approve.`)
    } catch (e) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }

  const approve = async (candidate) => {
    const draft = drafts[candidate.id]
    setBusy(true)
    try {
      await approveVisualCandidate(candidate.id, {
        ...draft,
        price: Number(draft.price || 0),
        stock_quantity: Number(draft.stock_quantity || 0),
        low_stock_threshold: Number(draft.low_stock_threshold || 3),
      })
      setBatch(prev => ({
        ...prev,
        candidates: prev.candidates.map(c => c.id === candidate.id ? { ...c, status: 'approved' } : c),
      }))
      setMessage(`${draft.name} added to catalog.`)
    } catch (e) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }

  const reject = async (candidate) => {
    setBusy(true)
    try {
      await rejectVisualCandidate(candidate.id, 'Demo review rejected')
      setBatch(prev => ({
        ...prev,
        candidates: prev.candidates.map(c => c.id === candidate.id ? { ...c, status: 'rejected' } : c),
      }))
      setMessage(`${drafts[candidate.id]?.name || 'Candidate'} rejected.`)
    } catch (e) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="setup-page">
      <motion.section
        className="setup-hero"
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.42 }}
      >
        <div>
          <span className="setup-eyebrow">Demo onboarding</span>
          <h1>Your store learns the catalog before the first customer asks.</h1>
          <p>
            Choose the business type, upload product photos, let FashionCLIP draft the catalog,
            then approve products with size and product guidance for Telegram.
          </p>
        </div>
        <div className="setup-flow">
          <span>Login</span>
          <span>Business type</span>
          <span>Upload photos</span>
          <span>Review catalog</span>
          <span>Telegram search</span>
        </div>
      </motion.section>

      <section className="setup-section">
        <div className="setup-section-head">
          <div>
            <span className="setup-step">1</span>
            <h2>Select business type</h2>
          </div>
          <p>For the video we use clothing, because visual search and size guidance are immediately obvious.</p>
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
              {type.active && <em>Recommended for demo</em>}
            </button>
          ))}
        </div>
      </section>

      <section className="setup-section">
        <div className="setup-section-head">
          <div>
            <span className="setup-step">2</span>
            <h2>Upload product photos</h2>
          </div>
          <p>Drop all photos at once. The system creates product candidates with name, category, keywords and confidence.</p>
        </div>
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
          <input
            ref={inputRef}
            type="file"
            multiple
            accept="image/*"
            onChange={e => pickFiles(e.target.files)}
            hidden
          />
          <strong>Drop product photos here</strong>
          <span>or click to select from the Polyvore demo folder</span>
        </div>
        {previews.length > 0 && (
          <div className="upload-preview-grid">
            {previews.slice(0, 12).map(({ file, url }) => (
              <div className="upload-preview" key={`${file.name}-${file.size}`}>
                <img src={url} alt={file.name} />
                <span>{file.name}</span>
              </div>
            ))}
          </div>
        )}
        <div className="setup-actions-row">
          <button className="btn btn-primary" type="button" onClick={upload} disabled={busy || !files.length}>
            {busy ? 'Classifying...' : 'Classify images'}
          </button>
          {message && <span className="setup-message">{message}</span>}
        </div>
      </section>

      {batch?.candidates?.length > 0 && (
        <section className="setup-section">
          <div className="setup-section-head">
            <div>
              <span className="setup-step">3</span>
              <h2>Review generated catalog</h2>
            </div>
            <p>Fill price, stock and size guide. Customer visual search and size questions use this catalog data.</p>
          </div>
          <div className="setup-candidates">
            {batch.candidates.map(candidate => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                draft={drafts[candidate.id] || seedDraft(candidate)}
                onChange={(key, value) => setCandidateDraft(candidate.id, key, value)}
                onApprove={() => approve(candidate)}
                onReject={() => reject(candidate)}
                busy={busy}
              />
            ))}
          </div>
        </section>
      )}

      <section className="setup-section setup-telegram-demo">
        <div className="setup-section-head">
          <div>
            <span className="setup-step">4</span>
            <h2>Customer Telegram demo</h2>
          </div>
          <p>After approval, the customer sends a product image. CLIP finds the catalog item; ordering continues with buttons, without LLM cost.</p>
        </div>
        <div className="telegram-script-grid">
          <div>
            <strong>Customer sends</strong>
            <p>Photo of sandals / bag / jeans</p>
          </div>
          <div>
            <strong>Bot replies</strong>
            <p>“I found this product: Beige Crystal Sandals, 899 TL, stock 12. Is this the item you want?”</p>
          </div>
          <div>
            <strong>Buttons</strong>
            <p>Add to cart · Product list · Main menu</p>
          </div>
          <div>
            <strong>Size question</strong>
            <p>“Which size fits me?” uses the product size guide saved during review.</p>
          </div>
        </div>
      </section>
    </div>
  )
}
