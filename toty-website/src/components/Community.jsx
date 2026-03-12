import { motion, useInView } from 'framer-motion'
import { useRef, useState, useEffect } from 'react'
import { Github, MessageCircle, Users, Star, GitFork } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './Community.css'

export default function Community() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })

  const cards = [
    { icon: <Github size={24} />, color: 'var(--text-bright)', ...t.community.github },
    { icon: <MessageCircle size={24} />, color: '#5865F2', ...t.community.discord },
    { icon: <Users size={24} />, color: 'var(--teal)', ...t.community.contribute },
  ]

  return (
    <section className="section community-section" id="community" ref={ref}>
      <div className="container">
        <motion.div
          className="community-header"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <span className="section-label">{t.community.label}</span>
          <h2 className="section-title">
            {t.community.title}{' '}
            <span className="gradient-text">{t.community.titleHighlight}</span>
          </h2>
          <p className="section-subtitle">{t.community.subtitle}</p>
        </motion.div>

        <div className="community-grid">
          {cards.map((card, i) => (
            <motion.a
              key={i}
              href={card.link}
              target="_blank"
              rel="noopener noreferrer"
              className="community-card"
              initial={{ opacity: 0, y: 30 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.1 }}
              whileHover={{ y: -6, transition: { duration: 0.2 } }}
            >
              <div className="community-icon" style={{ color: card.color, background: `${card.color}15` }}>
                {card.icon}
              </div>
              <h3 className="community-title">{card.title}</h3>
              <p className="community-desc">{card.desc}</p>
              <span className="community-cta">{card.cta} →</span>
            </motion.a>
          ))}
        </div>

        <motion.div
          className="community-stats"
          initial={{ opacity: 0, y: 20 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          {t.community.stats.map((s, i) => (
            <div key={i} className="community-stat">
              <span className="community-stat-value">{s.value}</span>
              <span className="community-stat-label">{s.label}</span>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  )
}
