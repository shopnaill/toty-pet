import { motion, useInView } from 'framer-motion'
import { useRef, useState } from 'react'
import { Play, Timer, Trophy, BarChart3, Moon, Mic } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './Showcase.css'

const tabDefs = [
  { id: 'productivity', icon: <Timer size={16} />, color: 'var(--peach)' },
  { id: 'gaming', icon: <Trophy size={16} />, color: 'var(--yellow)' },
  { id: 'islamic', icon: <Moon size={16} />, color: 'var(--green)' },
  { id: 'media', icon: <Play size={16} />, color: 'var(--blue)' },
  { id: 'voice', icon: <Mic size={16} />, color: 'var(--pink)' },
  { id: 'analytics', icon: <BarChart3 size={16} />, color: 'var(--purple)' },
]

export default function Showcase() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const [active, setActive] = useState('productivity')
  const tabs = tabDefs.map(d => ({ ...d, ...t.showcase.tabs[d.id] }))
  const tab = tabs.find(tb => tb.id === active)

  return (
    <section className="section showcase-section" ref={ref}>
      <div className="container">
        <motion.div
          className="showcase-header"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <span className="section-label">{t.showcase.label}</span>
          <h2 className="section-title">
            {t.showcase.title} <span className="gradient-text">{t.showcase.titleHighlight}</span>
          </h2>
        </motion.div>

        <motion.div
          className="showcase-tabs"
          initial={{ opacity: 0, y: 20 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          {tabs.map(tb => (
            <button
              key={tb.id}
              className={`showcase-tab ${active === tb.id ? 'active' : ''}`}
              onClick={() => setActive(tb.id)}
              style={active === tb.id ? { borderColor: tb.color, color: tb.color } : {}}
            >
              {tb.icon}
              {tb.label}
            </button>
          ))}
        </motion.div>

        <motion.div
          className="showcase-content"
          key={active}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <div className="showcase-info">
            <h3 className="showcase-title" style={{ color: tab.color }}>{tab.title}</h3>
            <p className="showcase-desc">{tab.desc}</p>
            <ul className="showcase-list">
              {tab.items.map((item, i) => (
                <motion.li
                  key={i}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.06 }}
                >
                  <span className="list-bullet" style={{ background: tab.color }} />
                  {item}
                </motion.li>
              ))}
            </ul>
          </div>

          <div className="showcase-visual">
            <div className="visual-card" style={{ borderColor: `${tab.color}30` }}>
              <div className="visual-header">
                <div className="visual-icon" style={{ background: `${tab.color}20`, color: tab.color }}>
                  {tab.icon}
                </div>
                <span className="visual-label">{tab.label}</span>
              </div>
              <div className="visual-bars">
                {[85, 62, 94, 48, 76, 90].map((v, i) => (
                  <motion.div
                    key={`${active}-${i}`}
                    className="visual-bar-row"
                    initial={{ opacity: 0, width: 0 }}
                    animate={{ opacity: 1, width: '100%' }}
                    transition={{ delay: i * 0.08 }}
                  >
                    <div className="bar-track">
                      <motion.div
                        className="bar-fill"
                        style={{ background: tab.color }}
                        initial={{ width: 0 }}
                        animate={{ width: `${v}%` }}
                        transition={{ duration: 0.8, delay: 0.2 + i * 0.08 }}
                      />
                    </div>
                    <span className="bar-value" style={{ color: tab.color }}>{v}%</span>
                  </motion.div>
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
