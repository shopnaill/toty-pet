import { motion, useInView } from 'framer-motion'
import { useRef, useState, useMemo } from 'react'
import { Search, X } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './FeatureExplorer.css'

export default function FeatureExplorer() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const [query, setQuery] = useState('')
  const [activeTag, setActiveTag] = useState(null)

  const items = t.featureExplorer.items
  const tags = t.featureExplorer.tags

  const filtered = useMemo(() => {
    return items.filter(item => {
      const matchQuery = !query || item.name.toLowerCase().includes(query.toLowerCase())
      const matchTag = !activeTag || item.tag === activeTag
      return matchQuery && matchTag
    })
  }, [query, activeTag, items])

  return (
    <section className="section explorer-section" id="feature-explorer" ref={ref}>
      <div className="container">
        <motion.div
          className="explorer-header"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <span className="section-label">{t.featureExplorer.label}</span>
          <h2 className="section-title">
            {t.featureExplorer.title}{' '}
            <span className="gradient-text">{t.featureExplorer.titleHighlight}</span>
          </h2>
        </motion.div>

        <motion.div
          className="explorer-controls"
          initial={{ opacity: 0, y: 20 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5, delay: 0.15 }}
        >
          <div className="explorer-search">
            <Search size={16} />
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder={t.featureExplorer.searchPlaceholder}
            />
            {query && <button className="explorer-clear" onClick={() => setQuery('')}><X size={14} /></button>}
          </div>
          <div className="explorer-tags">
            <button
              className={`explorer-tag ${!activeTag ? 'active' : ''}`}
              onClick={() => setActiveTag(null)}
            >
              {t.featureExplorer.allTag}
            </button>
            {tags.map(tag => (
              <button
                key={tag.id}
                className={`explorer-tag ${activeTag === tag.id ? 'active' : ''}`}
                onClick={() => setActiveTag(prev => prev === tag.id ? null : tag.id)}
                style={activeTag === tag.id ? { borderColor: tag.color, color: tag.color } : {}}
              >
                {tag.icon} {tag.label}
              </button>
            ))}
          </div>
        </motion.div>

        <div className="explorer-grid">
          {filtered.map((item, i) => (
            <motion.div
              key={item.name}
              className="explorer-item"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3, delay: i * 0.02 }}
              layout
            >
              <span className="explorer-emoji">{item.icon}</span>
              <span className="explorer-name">{item.name}</span>
            </motion.div>
          ))}
          {filtered.length === 0 && (
            <div className="explorer-empty">{t.featureExplorer.noResults}</div>
          )}
        </div>

        <div className="explorer-count">
          {filtered.length} / {items.length} {t.featureExplorer.featuresLabel}
        </div>
      </div>
    </section>
  )
}
