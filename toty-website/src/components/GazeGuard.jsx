import { motion, useInView } from 'framer-motion'
import { useRef, useState } from 'react'
import { Shield, Eye, EyeOff, Video, MonitorCheck, ScanFace, Lock } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './GazeGuard.css'

const capIcons = [
  <ScanFace size={20} />,
  <Shield size={20} />,
  <Video size={20} />,
  <Lock size={20} />,
  <MonitorCheck size={20} />,
  <Eye size={20} />,
]

export default function GazeGuard() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const [blurred, setBlurred] = useState(true)
  const capabilities = capIcons.map((icon, i) => ({ icon, text: t.gaze[`cap${i + 1}`] }))

  return (
    <section className="section gaze-section" id="gaze-guard" ref={ref}>
      <div className="bg-radial gaze-glow" />
      <div className="container">
        <div className="gaze-layout">
          <motion.div
            className="gaze-info"
            initial={{ opacity: 0, x: -40 }}
            animate={inView ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.6 }}
          >
            <span className="section-label">{t.gaze.label}</span>
            <h2 className="section-title">
              {t.gaze.title}<br />
              <span className="gradient-text">{t.gaze.titleHighlight}</span>
            </h2>
            <p className="section-subtitle">{t.gaze.desc}</p>

            <div className="gaze-caps">
              {capabilities.map((c, i) => (
                <motion.div
                  key={i}
                  className="gaze-cap"
                  initial={{ opacity: 0, x: -20 }}
                  animate={inView ? { opacity: 1, x: 0 } : {}}
                  transition={{ duration: 0.4, delay: 0.3 + i * 0.08 }}
                >
                  <div className="cap-icon">{c.icon}</div>
                  <span>{c.text}</span>
                </motion.div>
              ))}
            </div>
          </motion.div>

          <motion.div
            className="gaze-demo"
            initial={{ opacity: 0, x: 40 }}
            animate={inView ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.6, delay: 0.2 }}
          >
            <div className="demo-window">
              <div className="demo-titlebar">
                <div className="titlebar-dots">
                  <span className="dot red" /><span className="dot yellow" /><span className="dot green" />
                </div>
                <span className="demo-title-text">{t.gaze.demoTitle}</span>
                <div className="demo-status">
                  <span className="status-dot" />
                  {t.gaze.protected}
                </div>
              </div>

              <div className="demo-body">
                <div className="demo-screen">
                  <img
                    src="/screenshots/screenshot_20260308_031829.jpg"
                    alt="Gaze Guard demo"
                    className="demo-screenshot"
                    style={{ filter: blurred ? 'blur(12px)' : 'none', transition: 'filter 0.4s ease' }}
                    loading="lazy"
                  />

                  <div className="demo-overlay-badge">
                    <Shield size={14} />
                    <span>{t.gaze.regionsBlurred}</span>
                  </div>
                </div>

                <div className="demo-controls">
                  <button
                    className={`demo-toggle ${blurred ? 'active' : ''}`}
                    onClick={() => setBlurred(!blurred)}
                  >
                    {blurred ? <EyeOff size={16} /> : <Eye size={16} />}
                    {blurred ? t.gaze.protected : t.gaze.unprotected}
                  </button>
                  <div className="demo-stats">
                    <div className="demo-stat">
                      <span className="ds-value">7</span>
                      <span className="ds-label">{t.gaze.dayStreak}</span>
                    </div>
                    <div className="demo-stat">
                      <span className="ds-value">156</span>
                      <span className="ds-label">{t.gaze.blocked}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  )
}
