import { motion, useInView } from 'framer-motion'
import { useRef } from 'react'
import { Sparkles, Zap, Bug, Star } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './Changelog.css'

const typeIcons = { feature: <Sparkles size={14} />, improve: <Zap size={14} />, fix: <Bug size={14} /> }
const typeColors = { feature: 'var(--teal)', improve: 'var(--purple)', fix: 'var(--red)' }

export default function Changelog() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })

  return (
    <section className="section changelog-section" id="changelog" ref={ref}>
      <div className="container">
        <motion.div
          className="changelog-header"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <span className="section-label">{t.changelog.label}</span>
          <h2 className="section-title">
            {t.changelog.title}{' '}
            <span className="gradient-text">{t.changelog.titleHighlight}</span>
          </h2>
        </motion.div>

        <div className="changelog-timeline">
          {t.changelog.releases.map((rel, ri) => (
            <motion.div
              key={ri}
              className="changelog-release"
              initial={{ opacity: 0, x: -30 }}
              animate={inView ? { opacity: 1, x: 0 } : {}}
              transition={{ duration: 0.5, delay: ri * 0.15 }}
            >
              <div className="timeline-dot" />
              <div className="release-card">
                <div className="release-header">
                  <span className="release-version">{rel.version}</span>
                  <span className="release-date">{rel.date}</span>
                  {rel.latest && <span className="release-badge"><Star size={12} /> {t.changelog.latest}</span>}
                </div>
                <ul className="release-items">
                  {rel.items.map((item, ii) => (
                    <li key={ii} className="release-item">
                      <span className="item-type" style={{ color: typeColors[item.type], background: `${typeColors[item.type]}15` }}>
                        {typeIcons[item.type]} {item.type}
                      </span>
                      <span>{item.text}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
