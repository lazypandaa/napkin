import { Download, Plus, ArrowLeft, Share2, Play } from 'lucide-react'
import './Topbar.css'

export default function Topbar({ title, onExport, onNew, onBack, onPresent }) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="topbar-back" onClick={onBack} title="Back to home">
          <ArrowLeft size={16} />
        </button>
        <div className="topbar-logo">
          <span className="logo-icon">✦</span>
          <span className="logo-text">Napkin AI</span>
        </div>
        <span className="topbar-sep">›</span>
        <span className="topbar-title">{title}</span>
      </div>
      <div className="topbar-right">
        <button className="btn-ghost" onClick={onNew}>
          <Plus size={15} /> New
        </button>
        <button className="btn-ghost" onClick={onExport}>
          <Share2 size={15} /> Share
        </button>
        <button className="btn-primary" onClick={onExport}>
          <Download size={15} /> Export PPTX
        </button>
        <button className="btn-present" onClick={onPresent}>
          <Play size={13} fill="white" /> Present
        </button>
      </div>
    </header>
  )
}
