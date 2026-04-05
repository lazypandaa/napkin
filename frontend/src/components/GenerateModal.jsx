import { useState } from 'react'
import { X, Sparkles } from 'lucide-react'
import './GenerateModal.css'

export default function GenerateModal({ onClose, onGenerate, loading }) {
  const [topic, setTopic] = useState('')
  const [requirements, setRequirements] = useState('')
  const [numSlides, setNumSlides] = useState(6)
  const [fetchImages, setFetchImages] = useState(true)

  const handleSubmit = e => {
    e.preventDefault()
    if (!topic.trim()) return
    onGenerate({ topic, requirements, num_slides: numSlides, fetch_images: fetchImages })
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            <Sparkles size={18} color="#6c47ff" />
            <span>Create new presentation</span>
          </div>
          <button className="modal-close" onClick={onClose}><X size={18} /></button>
        </div>

        <form className="modal-body" onSubmit={handleSubmit}>
          <div className="field">
            <label>Topic *</label>
            <input
              autoFocus
              value={topic}
              onChange={e => setTopic(e.target.value)}
              placeholder="e.g. The Future of Renewable Energy"
              disabled={loading}
            />
          </div>

          <div className="field">
            <label>Additional requirements</label>
            <textarea
              value={requirements}
              onChange={e => setRequirements(e.target.value)}
              placeholder="e.g. Target audience: executives. Include market data."
              rows={3}
              disabled={loading}
            />
          </div>

          <div className="field-row">
            <div className="field field-sm">
              <label>Number of slides</label>
              <select value={numSlides} onChange={e => setNumSlides(+e.target.value)} disabled={loading}>
                {[4,5,6,7,8,10,12].map(n => <option key={n} value={n}>{n} slides</option>)}
              </select>
            </div>
            <div className="field field-sm toggle-field">
              <label>Include images</label>
              <div
                className={`toggle ${fetchImages ? 'on' : ''}`}
                onClick={() => setFetchImages(v => !v)}
              >
                <div className="toggle-knob" />
              </div>
            </div>
          </div>

          <button className="btn-generate" type="submit" disabled={loading || !topic.trim()}>
            {loading ? (
              <><span className="spinner" /> Generating…</>
            ) : (
              <><Sparkles size={15} /> Generate Presentation</>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
