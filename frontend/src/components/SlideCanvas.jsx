import { useEffect, useRef } from 'react'
import SlideCard from './SlideCard'
import './SlideCanvas.css'

export default function SlideCanvas({ presentation, activeSlide, onSelect, slideRefsCallback }) {
  const refs = useRef([])
  const containerRef = useRef()

  useEffect(() => {
    const el = refs.current[activeSlide === -1 ? 0 : activeSlide + 1]
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [activeSlide])

  useEffect(() => {
    if (slideRefsCallback) slideRefsCallback(refs.current)
  })

  const allSlides = [
    { type: 'title', data: presentation },
    ...presentation.slides.map((s, i) => ({ type: 'content', data: s, index: i })),
  ]

  return (
    <main className="canvas" ref={containerRef}>
      <div className="canvas-inner">
        {allSlides.map((item, i) => (
          <div
            key={i}
            ref={el => refs.current[i] = el}
            className={`slide-wrapper ${(activeSlide === -1 && i === 0) || activeSlide === i - 1 ? 'slide-active' : ''}`}
            onClick={() => onSelect(i === 0 ? -1 : i - 1)}
          >
            <SlideCard item={item} fetchImages={presentation._fetch_images ?? true} />
          </div>
        ))}
      </div>
    </main>
  )
}
