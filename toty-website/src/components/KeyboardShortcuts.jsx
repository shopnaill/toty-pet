import { motion, useInView } from 'framer-motion'
import { useRef } from 'react'
import { useLang } from '../i18n/LangContext'
import './KeyboardShortcuts.css'

export default function KeyboardShortcuts() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })

  return (
    <section className="section shortcuts-section" id="shortcuts" ref={ref}>
      <div className="container">
        <motion.div
          className="shortcuts-header"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <span className="section-label">{t.shortcuts.label}</span>
          <h2 className="section-title">
            {t.shortcuts.title}{' '}
            <span className="gradient-text">{t.shortcuts.titleHighlight}</span>
          </h2>
          <p className="section-subtitle">{t.shortcuts.subtitle}</p>
        </motion.div>

        <div className="shortcuts-grid">
          {t.shortcuts.groups.map((group, gi) => (
            <motion.div
              key={gi}
              className="shortcuts-group"
              initial={{ opacity: 0, y: 30 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: gi * 0.1 }}
            >
              <h3 className="shortcuts-group-title">{group.title}</h3>
              <div className="shortcuts-list">
                {group.keys.map((item, ki) => (
                  <div key={ki} className="shortcut-row">
                    <div className="shortcut-keys">
                      {item.combo.split('+').map((k, j) => (
                        <span key={j}>
                          <kbd className="key-cap">{k.trim()}</kbd>
                          {j < item.combo.split('+').length - 1 && <span className="key-plus">+</span>}
                        </span>
                      ))}
                    </div>
                    <span className="shortcut-desc">{item.desc}</span>
                  </div>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
