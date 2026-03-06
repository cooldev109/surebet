import { createContext, useContext, useState } from 'react'
import { translations } from './i18n'

const LanguageContext = createContext()

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState('es')
  const t = translations[lang]
  const toggle = () => setLang(l => l === 'es' ? 'en' : 'es')

  return (
    <LanguageContext.Provider value={{ lang, t, toggle }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLang() {
  return useContext(LanguageContext)
}
