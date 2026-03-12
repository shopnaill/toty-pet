import { motion, useInView } from 'framer-motion'
import { useRef, useState, useEffect } from 'react'
import { Zap, Brain, Shield, Gamepad2 } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './Stats.css'

function AnimatedCounter({ target, inView, suffix = '' }) {
  const [count, setCount] = useState(0)
  useEffect(() => {
    if (!inView) return
    const num = parseInt(target, 10)
    if (isNaN(num)) { setCount(target); return }
    let start = 0
    const duration = 1200
    const step = Math.max(1, Math.floor(num / (duration / 16)))
    const timer = setInterval(() => {
      start += step
      if (start >= num) { setCount(num); clearInterval(timer) }
      else setCount(start)
    }, 16)
    return () => clearInterval(timer)
  }, [inView, target])
  return <>{typeof count === 'number' ? count : target}{suffix}</>
}

export default function Stats() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-100px' })

  const stats = [
    { icon: <Zap size={22} />, value: 130, suffix: '+', label: t.stats.features, color: 'var(--teal)' },
    { icon: <Brain size={22} />, value: 3, suffix: '', label: t.stats.aiModels, color: 'var(--purple)' },
    { icon: <Shield size={22} />, value: 54, suffix: '+', label: t.stats.modules, color: 'var(--blue)' },
    { icon: <Gamepad2 size={22} />, value: 20, suffix: '+', label: t.stats.achievements, color: 'var(--peach)' },
  ]

  return (
    <section className="stats-section" ref={ref}>
      <div className="container">
        <div className="stats-grid">
          {stats.map((s, i) => (
            <motion.div
              key={i}
              className="stat-card"
              initial={{ opacity: 0, y: 30 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: i * 0.1 }}
            >
              <div className="stat-icon" style={{ color: s.color, background: `${s.color}15` }}>
                {s.icon}
              </div>
              <div className="stat-value">
                <AnimatedCounter target={s.value} inView={inView} suffix={s.suffix} />
              </div>
              <div className="stat-label">{s.label}</div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
