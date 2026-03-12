import { motion } from 'framer-motion'
import { ArrowDown, Sparkles, Download, Star } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import TotyCat from './TotyCat'
import './Hero.css'

export default function Hero() {
  const { t } = useLang()

  return (
    <section className="hero">
      <div className="bg-grid" />
      <div className="bg-radial hero-glow-1" />
      <div className="bg-radial hero-glow-2" />

      {[...Array(6)].map((_, i) => (
        <motion.div
          key={i}
          className="hero-particle"
          style={{
            left: `${15 + i * 14}%`,
            top: `${20 + (i % 3) * 25}%`,
            width: 4 + (i % 3) * 3,
            height: 4 + (i % 3) * 3,
          }}
          animate={{ y: [0, -30, 0], opacity: [0.2, 0.6, 0.2] }}
          transition={{ duration: 3 + i * 0.5, repeat: Infinity, delay: i * 0.4 }}
        />
      ))}

      <div className="container hero-content">
        <motion.div className="hero-badge" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
          <Sparkles size={14} />
          <span>{t.hero.badge}</span>
        </motion.div>

        <motion.h1 className="hero-title" initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }}>
          {t.hero.titlePre} <span className="gradient-text">{t.hero.titleHighlight}</span> {t.hero.titlePost}
          <br />{t.hero.titleLine2}
        </motion.h1>

        <motion.p className="hero-desc" initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.2 }}>
          {t.hero.desc}
        </motion.p>

        <motion.div className="hero-actions" initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.3 }}>
          <a href="#download" className="btn-primary">
            <Download size={18} />
            {t.hero.downloadBtn}
          </a>
          <a href="#features" className="btn-secondary">
            {t.hero.exploreBtn}
            <ArrowDown size={16} />
          </a>
        </motion.div>

        <motion.div className="hero-social-proof" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6, delay: 0.5 }}>
          <div className="hero-stars">
            {[...Array(5)].map((_, i) => <Star key={i} size={14} fill="var(--yellow)" color="var(--yellow)" />)}
          </div>
          <span className="hero-proof-text">{t.hero.socialProof}</span>
        </motion.div>

        <motion.div className="hero-preview" initial={{ opacity: 0, scale: 0.9, y: 40 }} animate={{ opacity: 1, scale: 1, y: 0 }} transition={{ duration: 0.8, delay: 0.4 }}>
          <div className="preview-window">
            <div className="preview-titlebar">
              <div className="titlebar-dots">
                <span className="dot red" /><span className="dot yellow" /><span className="dot green" />
              </div>
              <span className="titlebar-text">{t.hero.previewTitle}</span>
            </div>
            <div className="preview-body">
              <TotyCat size={160} />
              <div className="preview-bubble">
                <span>{t.hero.bubble}</span>
                <div className="bubble-tail" />
              </div>
              <div className="preview-widgets">
                <div className="widget-chip"><span className="chip-dot teal" />{t.hero.widgetFocus}</div>
                <div className="widget-chip"><span className="chip-dot purple" />{t.hero.widgetLevel}</div>
                <div className="widget-chip"><span className="chip-dot green" />{t.hero.widgetStreak}</div>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
