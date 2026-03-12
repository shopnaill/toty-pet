import { motion, useInView } from 'framer-motion'
import { useRef } from 'react'
import { Download as DownloadIcon, Monitor, Cpu, HardDrive } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import TotyCat from './TotyCat'
import './Download.css'

const reqIcons = [
  <Monitor size={18} />,
  <Cpu size={18} />,
  <HardDrive size={18} />,
]
const reqKeys = ['reqWindows', 'reqPython', 'reqDisk']

export default function Download() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })

  return (
    <section className="section download-section" id="download" ref={ref}>
      <div className="bg-grid" />
      <div className="bg-radial dl-glow" />
      <div className="container">
        <motion.div
          className="dl-content"
          initial={{ opacity: 0, y: 40 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
        >
          <TotyCat size={80} className="dl-pet" />

          <span className="section-label">{t.download.label}</span>
          <h2 className="section-title" style={{ textAlign: 'center' }}>
            {t.download.title} <span className="gradient-text">{t.download.titleHighlight}</span> {t.download.titlePost}
          </h2>
          <p className="section-subtitle" style={{ textAlign: 'center', margin: '0 auto 32px' }}>
            {t.download.desc}
          </p>

          <div className="dl-buttons">
            <motion.a
              href="https://github.com/mfoud5391/toty/releases"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary btn-lg"
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.98 }}
            >
              <DownloadIcon size={20} />
              {t.download.btn}
            </motion.a>
          </div>

          <div className="dl-reqs">
            {reqKeys.map((key, i) => (
              <div key={key} className="dl-req">
                {reqIcons[i]}
                <span>{t.download[key]}</span>
              </div>
            ))}
          </div>

          <div className="dl-install">
            <code className="install-cmd">
              <span className="cmd-prompt">$</span> git clone https://github.com/mfoud5391/toty.git && cd toty && python animals.py
            </code>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
