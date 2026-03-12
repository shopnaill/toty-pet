import { motion, useInView, AnimatePresence } from 'framer-motion'
import { useRef, useState } from 'react'
import { ChevronDown, HelpCircle } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './FAQ.css'

export default function FAQ() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const [openIndex, setOpenIndex] = useState(null)

  const toggle = (i) => setOpenIndex(prev => prev === i ? null : i)

  return (
    <section className="section faq-section" id="faq" ref={ref}>
      <div className="container">
        <motion.div
          className="faq-header"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <span className="section-label">{t.faq.label}</span>
          <h2 className="section-title">
            {t.faq.title}{' '}
            <span className="gradient-text">{t.faq.titleHighlight}</span>
          </h2>
          <p className="section-subtitle">{t.faq.subtitle}</p>
        </motion.div>

        <div className="faq-list">
          {t.faq.items.map((item, i) => (
            <motion.div
              key={i}
              className={`faq-item ${openIndex === i ? 'open' : ''}`}
              initial={{ opacity: 0, y: 20 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.05 }}
            >
              <button className="faq-question" onClick={() => toggle(i)}>
                <HelpCircle size={18} className="faq-icon" />
                <span>{item.q}</span>
                <ChevronDown size={18} className={`faq-chevron ${openIndex === i ? 'rotated' : ''}`} />
              </button>
              <AnimatePresence>
                {openIndex === i && (
                  <motion.div
                    className="faq-answer"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.3 }}
                  >
                    <p>{item.a}</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
