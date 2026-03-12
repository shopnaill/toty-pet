import { motion, useInView } from 'framer-motion'
import { useRef } from 'react'
import { Shield, Wifi, Eye, HardDrive, Lock, Server } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './Privacy.css'

const icons = [<Wifi size={22} />, <Eye size={22} />, <HardDrive size={22} />, <Lock size={22} />, <Server size={22} />, <Shield size={22} />]
const colors = ['var(--teal)', 'var(--purple)', 'var(--blue)', 'var(--pink)', 'var(--peach)', 'var(--green)']

export default function Privacy() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })

  return (
    <section className="section privacy-section" id="privacy" ref={ref}>
      <div className="container">
        <motion.div
          className="privacy-header"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <span className="section-label">{t.privacy.label}</span>
          <h2 className="section-title">
            {t.privacy.title}{' '}
            <span className="gradient-text">{t.privacy.titleHighlight}</span>
          </h2>
          <p className="section-subtitle">{t.privacy.subtitle}</p>
        </motion.div>

        <div className="privacy-grid">
          {t.privacy.items.map((item, i) => (
            <motion.div
              key={i}
              className="privacy-card"
              initial={{ opacity: 0, y: 24 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.08 }}
            >
              <div className="privacy-icon" style={{ color: colors[i], background: `${colors[i]}15` }}>
                {icons[i]}
              </div>
              <h3 className="privacy-title">{item.title}</h3>
              <p className="privacy-desc">{item.desc}</p>
            </motion.div>
          ))}
        </div>

        <motion.div
          className="privacy-badge-bar"
          initial={{ opacity: 0, y: 20 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5, delay: 0.5 }}
        >
          <div className="privacy-badge">
            <Shield size={16} />
            <span>{t.privacy.badge}</span>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
