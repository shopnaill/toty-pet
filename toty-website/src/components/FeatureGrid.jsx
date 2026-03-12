import { motion, useInView } from 'framer-motion'
import { useRef } from 'react'
import {
  Notebook, ClipboardList, Palette, QrCode, HardDrive, FolderLock,
  Wifi, Cloud, BatteryCharging, Wallpaper, Bell, CalendarCheck,
  Coffee, Droplets, Eye, PackageSearch, Rocket, MonitorDown,
  GamepadIcon, Brush, FileDown, Camera,
} from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './FeatureGrid.css'

const featureDefs = [
  { icon: <Notebook size={18} />, key: 'dailyJournal', cat: 'journal' },
  { icon: <ClipboardList size={18} />, key: 'miniTodo', cat: 'productivity' },
  { icon: <Palette size={18} />, key: 'colorPicker', cat: 'tools' },
  { icon: <QrCode size={18} />, key: 'qrCode', cat: 'tools' },
  { icon: <HardDrive size={18} />, key: 'desktopOrganizer', cat: 'system' },
  { icon: <FolderLock size={18} />, key: 'folderLocker', cat: 'system' },
  { icon: <Wifi size={18} />, key: 'networkMonitor', cat: 'system' },
  { icon: <Cloud size={18} />, key: 'weatherReactor', cat: 'smart' },
  { icon: <BatteryCharging size={18} />, key: 'batterySaver', cat: 'system' },
  { icon: <Wallpaper size={18} />, key: 'autoWallpaper', cat: 'visual' },
  { icon: <Bell size={18} />, key: 'notificationReader', cat: 'smart' },
  { icon: <CalendarCheck size={18} />, key: 'habitTracker', cat: 'productivity' },
  { icon: <Coffee size={18} />, key: 'morningRoutine', cat: 'wellness' },
  { icon: <Droplets size={18} />, key: 'waterReminder', cat: 'wellness' },
  { icon: <Eye size={18} />, key: 'eyeCare', cat: 'wellness' },
  { icon: <PackageSearch size={18} />, key: 'packageManager', cat: 'dev' },
  { icon: <Rocket size={18} />, key: 'startupOptimizer', cat: 'system' },
  { icon: <MonitorDown size={18} />, key: 'systemCleaner', cat: 'system' },
  { icon: <GamepadIcon size={18} />, key: 'dailyChallenges', cat: 'gaming' },
  { icon: <Brush size={18} />, key: 'textTools', cat: 'dev' },
  { icon: <FileDown size={18} />, key: 'fileCompressor', cat: 'system' },
  { icon: <Camera size={18} />, key: 'screenshotTool', cat: 'tools' },
  { icon: <Bell size={18} />, key: 'smartReminders', cat: 'smart' },
  { icon: <ClipboardList size={18} />, key: 'clipboardHistory', cat: 'tools' },
]

const catColors = {
  journal: 'var(--purple)',
  productivity: 'var(--peach)',
  tools: 'var(--blue)',
  system: 'var(--teal)',
  smart: 'var(--green)',
  visual: 'var(--pink)',
  wellness: 'var(--red)',
  dev: 'var(--yellow)',
  gaming: 'var(--peach)',
}

export default function FeatureGrid() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })

  return (
    <section className="section" id="all-features" ref={ref}>
      <div className="container">
        <motion.div
          className="fg-header"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <span className="section-label">{t.featureGrid.label}</span>
          <h2 className="section-title">
            {t.featureGrid.title} <span className="gradient-text">{t.featureGrid.titleHighlight}</span>
          </h2>
          <p className="section-subtitle">{t.featureGrid.subtitle}</p>
        </motion.div>

        <div className="fg-grid">
          {featureDefs.map((f, i) => (
            <motion.div
              key={f.key}
              className="fg-item"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={inView ? { opacity: 1, scale: 1 } : {}}
              transition={{ duration: 0.3, delay: i * 0.03 }}
              whileHover={{ scale: 1.04, transition: { duration: 0.15 } }}
            >
              <div className="fg-icon" style={{
                color: catColors[f.cat],
                background: `${catColors[f.cat]}15`,
              }}>
                {f.icon}
              </div>
              <span className="fg-name">{t.featureGrid.items[f.key]}</span>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
