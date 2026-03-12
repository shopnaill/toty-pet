import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Menu, X, Github, Download, Globe } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './Navbar.css'

export default function Navbar() {
  const { t, toggle } = useLang()
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  const links = [
    { label: t.nav.features, href: '#features' },
    { label: t.nav.gazeGuard, href: '#gaze-guard' },
    { label: t.nav.aiChat, href: '#ai-chat' },
    { label: t.nav.allFeatures, href: '#all-features' },
    { label: t.nav.faq, href: '#faq' },
  ]

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 50)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <motion.nav
      className={`navbar ${scrolled ? 'scrolled' : ''}`}
      initial={{ y: -80 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.6, ease: 'easeOut' }}
    >
      <div className="navbar-inner container">
        <a href="#" className="navbar-brand">
          <img src="/toty-pet.png" alt="Toty" className="brand-icon-img" />
          <span className="brand-text">Toty</span>
          <span className="brand-badge">v15</span>
        </a>

        <div className="navbar-links">
          {links.map(l => (
            <a key={l.href} href={l.href} className="nav-link">{l.label}</a>
          ))}
        </div>

        <div className="navbar-actions">
          <button className="nav-lang-btn" onClick={toggle} aria-label="Switch language">
            <Globe size={16} />
            <span>{t.langSwitch.label}</span>
          </button>
          <a href="https://github.com/mfoud5391/toty" target="_blank" rel="noopener noreferrer" className="nav-icon-btn" aria-label="GitHub">
            <Github size={18} />
          </a>
          <a href="#download" className="nav-cta">
            <Download size={16} />
            {t.nav.download}
          </a>
        </div>

        <button className="mobile-toggle" onClick={() => setMobileOpen(!mobileOpen)}>
          {mobileOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>

      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            className="mobile-menu"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            {links.map(l => (
              <a key={l.href} href={l.href} className="mobile-link"
                onClick={() => setMobileOpen(false)}>{l.label}</a>
            ))}
            <button className="nav-lang-btn mobile-lang" onClick={() => { toggle(); setMobileOpen(false) }}>
              <Globe size={16} />
              <span>{t.langSwitch.label}</span>
            </button>
            <a href="#download" className="nav-cta mobile-cta"
              onClick={() => setMobileOpen(false)}>
              <Download size={16} /> {t.nav.download}
            </a>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  )
}
