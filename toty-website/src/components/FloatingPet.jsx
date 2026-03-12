import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useLang } from '../i18n/LangContext'
import './FloatingPet.css'

const tips = {
  en: [
    'Hi there! 👋', 'Try Gaze Guard!', 'Chat with AI locally!',
    '130+ features!', 'Star us on GitHub ⭐', '100% private & local 🔐',
    'Voice commands: "Hey Toty!" 🎤', 'Track your focus time ⏱️',
    'Explore all features below 👇', 'Join our Discord community! 💬',
    'Free & open source forever ❤️', 'Prayer times built-in 🕌',
  ],
  ar: [
    'مرحباً! 👋', 'جرب حارس النظر!', 'دردش مع الذكاء المحلي!',
    '١٣٠+ ميزة!', 'قيّمنا على GitHub ⭐', '١٠٠% خاص ومحلي 🔐',
    'أوامر صوتية: "هاي توتي!" 🎤', 'تتبع وقت تركيزك ⏱️',
    'استكشف كل المميزات أدناه 👇', 'انضم لمجتمع Discord! 💬',
    'مجاني ومفتوح المصدر للأبد ❤️', 'أوقات الصلاة مدمجة 🕌',
  ],
}

export default function FloatingPet() {
  const { lang } = useLang()
  const [show, setShow] = useState(false)
  const [bubble, setBubble] = useState(null)

  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > 300)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const handleClick = () => {
    const pool = tips[lang] || tips.en
    setBubble(pool[Math.floor(Math.random() * pool.length)])
    setTimeout(() => setBubble(null), 3000)
  }

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          className="floating-pet"
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 40 }}
          onClick={handleClick}
        >
          <motion.img
            src="/toty-pet-animated.gif"
            alt="Toty"
            draggable={false}
            animate={{ y: [0, -6, 0] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
          />
          <AnimatePresence>
            {bubble && (
              <motion.div
                className="floating-pet-bubble"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
              >
                {bubble}
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
