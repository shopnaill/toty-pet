import { motion, useInView } from 'framer-motion'
import { useRef, useState, useEffect } from 'react'
import { Star, ChevronLeft, ChevronRight, Quote } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './Testimonials.css'

export default function Testimonials() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const [current, setCurrent] = useState(0)
  const items = t.testimonials.items

  useEffect(() => {
    const timer = setInterval(() => setCurrent(p => (p + 1) % items.length), 6000)
    return () => clearInterval(timer)
  }, [items.length])

  const prev = () => setCurrent(p => (p - 1 + items.length) % items.length)
  const next = () => setCurrent(p => (p + 1) % items.length)

  return (
    <section className="section testimonials-section" id="testimonials" ref={ref}>
      <div className="container">
        <motion.div
          className="testimonials-header"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <span className="section-label">{t.testimonials.label}</span>
          <h2 className="section-title">
            {t.testimonials.title}{' '}
            <span className="gradient-text">{t.testimonials.titleHighlight}</span>
          </h2>
        </motion.div>

        <motion.div
          className="testimonial-carousel"
          initial={{ opacity: 0, y: 40 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.2 }}
        >
          <button className="carousel-btn carousel-prev" onClick={prev} aria-label="Previous">
            <ChevronLeft size={20} />
          </button>

          <div className="testimonial-card">
            <Quote size={32} className="testimonial-quote-icon" />
            <p className="testimonial-text">{items[current].text}</p>
            <div className="testimonial-stars">
              {[...Array(5)].map((_, i) => (
                <Star key={i} size={14} fill="var(--yellow)" color="var(--yellow)" />
              ))}
            </div>
            <div className="testimonial-author">
              <div className="author-avatar">{items[current].avatar}</div>
              <div>
                <div className="author-name">{items[current].name}</div>
                <div className="author-role">{items[current].role}</div>
              </div>
            </div>
          </div>

          <button className="carousel-btn carousel-next" onClick={next} aria-label="Next">
            <ChevronRight size={20} />
          </button>
        </motion.div>

        <div className="carousel-dots">
          {items.map((_, i) => (
            <button
              key={i}
              className={`carousel-dot ${i === current ? 'active' : ''}`}
              onClick={() => setCurrent(i)}
              aria-label={`Go to testimonial ${i + 1}`}
            />
          ))}
        </div>
      </div>
    </section>
  )
}
