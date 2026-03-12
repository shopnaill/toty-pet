import { motion, useInView } from 'framer-motion'
import { useRef, useState } from 'react'
import { Mail, Send, CheckCircle } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './Newsletter.css'

export default function Newsletter() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = (e) => {
    e.preventDefault()
    setSubmitted(true)
    setTimeout(() => setSubmitted(false), 4000)
  }

  return (
    <section className="newsletter-section" ref={ref}>
      <div className="container">
        <motion.div
          className="newsletter-card"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
        >
          <div className="newsletter-icon">
            <Mail size={28} />
          </div>
          <h3 className="newsletter-title">{t.newsletter.title}</h3>
          <p className="newsletter-desc">{t.newsletter.desc}</p>
          {!submitted ? (
            <form className="newsletter-form" onSubmit={handleSubmit}>
              <input
                type="email"
                required
                placeholder={t.newsletter.placeholder}
                className="newsletter-input"
              />
              <button type="submit" className="newsletter-btn">
                <Send size={16} />
                {t.newsletter.btn}
              </button>
            </form>
          ) : (
            <motion.div
              className="newsletter-success"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
            >
              <CheckCircle size={20} />
              <span>{t.newsletter.success}</span>
            </motion.div>
          )}
          <p className="newsletter-note">{t.newsletter.note}</p>
        </motion.div>
      </div>
    </section>
  )
}
