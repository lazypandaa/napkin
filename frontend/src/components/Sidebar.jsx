import './Sidebar.css'

function SlideThumb({ slide, index, active, onClick, isTitle, titleText, subtitleText }) {
  let imgQuery = slide?.image_query

  if (isTitle) {
    imgQuery = slide?.cover_image_query || titleText
  } else {
    // Only 'bullets' layout actually renders images in SlideCard
    const layout = slide?.layout || 'bullets'
    if (layout !== 'bullets') {
      imgQuery = null
    }
  }

  const imgUrl = imgQuery
    ? `/image-proxy?query=${encodeURIComponent(imgQuery)}`
    : null

  return (
    <div className={`thumb-wrap ${active ? 'active' : ''}`} onClick={onClick}>
      <span className="thumb-num">{isTitle ? '1' : index + 2}</span>
      <div className="thumb-card">
        {imgUrl && <img src={imgUrl} alt="" className="thumb-img" />}
        <div className="thumb-overlay">
          <div className="thumb-slide-title">{isTitle ? titleText : slide?.title}</div>
          {!isTitle && slide?.bullets?.slice(0, 2).map((b, i) => (
            <div key={i} className="thumb-bullet">▸ {b.slice(0, 40)}{b.length > 40 ? '…' : ''}</div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function Sidebar({ slides, activeSlide, onSelect, title, subtitle, coverImageQuery }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-inner">
        <SlideThumb
          slide={{ cover_image_query: coverImageQuery }}
          index={-1}
          active={activeSlide === -1}
          onClick={() => onSelect(-1)}
          isTitle
          titleText={title}
          subtitleText={subtitle}
        />
        {slides.map((slide, i) => (
          <SlideThumb
            key={i}
            slide={slide}
            index={i}
            active={activeSlide === i}
            onClick={() => onSelect(i)}
          />
        ))}
      </div>
    </aside>
  )
}
