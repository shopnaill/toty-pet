import { motion, useInView } from 'framer-motion'
import { useRef } from 'react'
import { GraduationCap, Code2, Moon, Gamepad2 } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './UseCases.css'

const icons = [
  <GraduationCap size={28} />,
  <Code2 size={28} />,
  <Moon size={28} />,
  <Gamepad2 size={28} />,
]
const colors = ['var(--teal)', 'var(--purple)', 'var(--green)', 'var(--peach)']

export default function UseCases() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })

  return (
    <section className="section usecases-section" id="use-cases" ref={ref}>
      <div className="container">
        <motion.div
          className="usecases-header"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <span className="section-label">{t.useCases.label}</span>
          <h2 className="section-title">
            {t.useCases.title}{' '}
            <span className="gradient-text">{t.useCases.titleHighlight}</span>
          </h2>
        </motion.div>

        <div className="usecases-grid">
          {t.useCases.items.map((item, i) => (
            <motion.div
              key={i}
              className="usecase-card"
              initial={{ opacity: 0, y: 30 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.1 }}
              whileHover={{ y: -6, transition: { duration: 0.2 } }}
            >
              <div className="usecase-icon" style={{ color: colors[i], background: `${colors[i]}15` }}>
                {icons[i]}
              </div>
              <h3 className="usecase-title">{item.title}</h3>
              <p className="usecase-desc">{item.desc}</p>
              <ul className="usecase-features">
                {item.features.map((f, fi) => (
                  <li key={fi}>{f}</li>
                ))}
              </ul>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
