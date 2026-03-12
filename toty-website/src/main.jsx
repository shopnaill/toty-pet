import React from 'react'
import ReactDOM from 'react-dom/client'
import { LangProvider } from './i18n/LangContext'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <LangProvider>
      <App />
    </LangProvider>
  </React.StrictMode>,
)
