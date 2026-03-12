import { createContext, useContext, useState, useEffect } from 'react'
import { translations } from './translations'

const LangContext = createContext()

export function LangProvider({ children }) {
  const [lang, setLang] = useState(() => {
    try { return localStorage.getItem('toty-lang') || 'en' } catch { return 'en' }
  })

  const t = translations[lang]

  useEffect(() => {
    try { localStorage.setItem('toty-lang', lang) } catch {}
    document.documentElement.lang = t.lang
    document.documentElement.dir = t.dir
  }, [lang, t])

  const toggle = () => setLang(prev => prev === 'en' ? 'ar' : 'en')

  return (
    <LangContext.Provider value={{ lang, t, toggle }}>
      {children}
    </LangContext.Provider>
  )
}

export const useLang = () => useContext(LangContext)
