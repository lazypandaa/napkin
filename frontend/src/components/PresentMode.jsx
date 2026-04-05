import { useEffect, useState } from 'react'
import SlideCard from './SlideCard'
import './PresentMode.css'

export default function PresentMode({ presentation, startSlide = -1, onClose }) {
  const [currentSlide, setCurrentSlide] = useState(startSlide)
  const [scale, setScale] = useState(1)

  const allSlides = [
    { type: 'title', data: presentation },
    ...(presentation.slides || []).map((s, i) => ({ type: 'content', data: s, index: i }))
  ]

  // Fullscreen & Scaling logic
  useEffect(() => {
    const handleResize = () => {
      const scaleX = window.innerWidth / 1333
      const scaleY = window.innerHeight / 750
      setScale(Math.min(scaleX, scaleY))
    }
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    if (document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(() => {})
    }
    
    const handleFullscreenChange = () => {
      if (!document.fullscreenElement) {
        onClose()
      }
    }
    document.addEventListener('fullscreenchange', handleFullscreenChange)
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange)
      if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => {})
      }
    }
  }, [onClose])

  // Key navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'ArrowDown' || e.key === 'Enter') {
        setCurrentSlide(curr => Math.min(curr + 1, allSlides.length - 2))
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp' || e.key === 'Backspace') {
        setCurrentSlide(curr => Math.max(curr - 1, -1))
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [allSlides.length])

  const activeItem = allSlides[currentSlide + 1]

  return (
    <div className="present-overlay" onClick={(e) => {
      if (e.clientX > window.innerWidth / 2) {
        setCurrentSlide(curr => Math.min(curr + 1, allSlides.length - 2))
      } else {
        setCurrentSlide(curr => Math.max(curr - 1, -1))
      }
    }}>
      <div className="present-container" style={{ transform: `scale(${scale})` }}>
        <SlideCard item={activeItem} />
      </div>
      <div className="present-controls" onClick={e => e.stopPropagation()}>
        <button onClick={() => setCurrentSlide(curr => Math.max(curr - 1, -1))}>Prev</button>
        <span>{currentSlide + 2} / {allSlides.length}</span>
        <button onClick={() => setCurrentSlide(curr => Math.min(curr + 1, allSlides.length - 2))}>Next</button>
        <div style={{ width: '1px', height: '16px', background: 'rgba(255,255,255,0.2)', margin: '0 8px' }} />
        <button onClick={onClose}>Exit Fullscreen</button>
      </div>
    </div>
  )
}
