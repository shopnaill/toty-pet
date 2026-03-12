import { motion, useInView } from 'framer-motion'
import { useRef } from 'react'
import { Check, X, Minus } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './Comparison.css'

const StatusIcon = ({ val }) => {
  if (val === true) return <Check size={16} className="cmp-yes" />
  if (val === false) return <X size={16} className="cmp-no" />
  return <Minus size={16} className="cmp-partial" />
}

export default function Comparison() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })

  const rows = t.comparison.rows
  const cols = t.comparison.columns

  return (
    <section className="section comparison-section" id="comparison" ref={ref}>
      <div className="container">
        <motion.div
          className="comparison-header"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <span className="section-label">{t.comparison.label}</span>
          <h2 className="section-title">
            {t.comparison.title}{' '}
            <span className="gradient-text">{t.comparison.titleHighlight}</span>
          </h2>
        </motion.div>

        <motion.div
          className="comparison-table-wrap"
          initial={{ opacity: 0, y: 40 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.2 }}
        >
          <table className="comparison-table">
            <thead>
              <tr>
                <th className="cmp-feature-col">{t.comparison.featureLabel}</th>
                {cols.map((col, i) => (
                  <th key={i} className={i === 0 ? 'cmp-highlight-col' : ''}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri}>
                  <td className="cmp-feature-name">{row.feature}</td>
                  {row.values.map((val, vi) => (
                    <td key={vi} className={vi === 0 ? 'cmp-highlight-col' : ''}>
                      {typeof val === 'string' ? val : <StatusIcon val={val} />}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </motion.div>
      </div>
    </section>
  )
}
