import { motion, useInView } from 'framer-motion'
import { useRef } from 'react'
import {
  Brain, Timer, Heart, Mic, Monitor, Keyboard, Moon,
  Eye, Palette, Trophy, MessagesSquare, Folder,
} from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './Features.css'

const featureKeys = [
  { key: 'aiChat', icon: <Brain />, color: 'var(--purple)', bg: 'var(--purple-dim)' },
  { key: 'gazeGuard', icon: <Eye />, color: 'var(--teal)', bg: 'var(--teal-dim)' },
  { key: 'pomodoro', icon: <Timer />, color: 'var(--peach)', bg: 'var(--peach-dim)' },
  { key: 'health', icon: <Heart />, color: 'var(--pink)', bg: 'var(--pink-dim)' },
  { key: 'islamic', icon: <Moon />, color: 'var(--yellow)', bg: 'var(--yellow-dim)' },
  { key: 'voice', icon: <Mic />, color: 'var(--blue)', bg: 'var(--blue-dim)' },
  { key: 'media', icon: <Monitor />, color: 'var(--green)', bg: 'var(--green-dim)' },
  { key: 'productivity', icon: <Keyboard />, color: 'var(--red)', bg: 'var(--red-dim)' },
  { key: 'gaming', icon: <Trophy />, color: 'var(--yellow)', bg: 'var(--yellow-dim)' },
  { key: 'skins', icon: <Palette />, color: 'var(--pink)', bg: 'var(--pink-dim)' },
  { key: 'notifications', icon: <MessagesSquare />, color: 'var(--blue)', bg: 'var(--blue-dim)' },
  { key: 'utilities', icon: <Folder />, color: 'var(--peach)', bg: 'var(--peach-dim)' },
]

export default function Features() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })

  return (
    <section className="section" id="features" ref={ref}>
      <div className="container">
        <motion.div
          className="features-header"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <span className="section-label">{t.features.label}</span>
          <h2 className="section-title">
            {t.features.title}<br />
            <span className="gradient-text">{t.features.titleHighlight}</span>
          </h2>
          <p className="section-subtitle">{t.features.subtitle}</p>
        </motion.div>

        <div className="features-grid">
          {featureKeys.map((f, i) => (
            <motion.div
              key={f.key}
              className="feature-card"
              initial={{ opacity: 0, y: 30 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.06 }}
              whileHover={{ y: -6, transition: { duration: 0.2 } }}
            >
              <div className="feature-icon" style={{ color: f.color, background: f.bg }}>
                {f.icon}
              </div>
              <h3 className="feature-title">{t.features[f.key].title}</h3>
              <p className="feature-desc">{t.features[f.key].desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
