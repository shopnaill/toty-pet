import { motion, useInView } from 'framer-motion'
import { useRef, useState, useEffect } from 'react'
import { Bot, User, Sparkles, Send } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './AIChat.css'

export default function AIChat() {
  const { t } = useLang()
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const [visibleMessages, setVisibleMessages] = useState(0)

  const chatMessages = [
    { role: 'user', text: t.ai.msg1 },
    { role: 'bot', text: t.ai.msg2 },
    { role: 'user', text: t.ai.msg3 },
    { role: 'bot', text: t.ai.msg4 },
    { role: 'user', text: t.ai.msg5 },
    { role: 'bot', text: t.ai.msg6 },
  ]

  useEffect(() => {
    if (!inView) return
    const timer = setInterval(() => {
      setVisibleMessages(prev => {
        if (prev >= chatMessages.length) {
          clearInterval(timer)
          return prev
        }
        return prev + 1
      })
    }, 600)
    return () => clearInterval(timer)
  }, [inView])

  return (
    <section className="section ai-section" id="ai-chat" ref={ref}>
      <div className="bg-radial ai-glow" />
      <div className="container">
        <div className="ai-layout">
          <motion.div
            className="ai-chat-window"
            initial={{ opacity: 0, x: -40 }}
            animate={inView ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.6 }}
          >
            <div className="chat-titlebar">
              <div className="titlebar-dots">
                <span className="dot red" /><span className="dot yellow" /><span className="dot green" />
              </div>
              <div className="chat-title-info">
                <Bot size={16} />
                <span>{t.ai.chatTitle}</span>
              </div>
              <div className="chat-model-badge">{t.ai.localLLM}</div>
            </div>

            <div className="chat-body">
              {chatMessages.slice(0, visibleMessages).map((msg, i) => (
                <motion.div
                  key={i}
                  className={`chat-msg ${msg.role}`}
                  initial={{ opacity: 0, y: 12, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ duration: 0.3 }}
                >
                  <div className="msg-avatar">
                    {msg.role === 'bot' ? <Bot size={16} /> : <User size={16} />}
                  </div>
                  <div className="msg-bubble">
                    {msg.text.split('\n').map((line, j) => (
                      <span key={j}>{line}<br /></span>
                    ))}
                  </div>
                </motion.div>
              ))}

              {visibleMessages < chatMessages.length && visibleMessages > 0 && (
                <div className="chat-typing">
                  <div className="typing-dots">
                    <span /><span /><span />
                  </div>
                </div>
              )}
            </div>

            <div className="chat-input-bar">
              <div className="chat-input-field">
                <span className="input-placeholder">{t.ai.inputPlaceholder}</span>
              </div>
              <button className="chat-send">
                <Send size={16} />
              </button>
            </div>
          </motion.div>

          <motion.div
            className="ai-info"
            initial={{ opacity: 0, x: 40 }}
            animate={inView ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.6, delay: 0.2 }}
          >
            <span className="section-label">{t.ai.label}</span>
            <h2 className="section-title">
              {t.ai.title}<br />
              <span className="gradient-text">{t.ai.titleHighlight}</span>
            </h2>
            <p className="section-subtitle">{t.ai.desc}</p>

            <div className="ai-features">
              <div className="ai-feat">
                <Sparkles size={18} className="ai-feat-icon" />
                <div>
                  <strong>{t.ai.slashTitle}</strong>
                  <span>{t.ai.slashDesc}</span>
                </div>
              </div>
              <div className="ai-feat">
                <Sparkles size={18} className="ai-feat-icon" />
                <div>
                  <strong>{t.ai.memoryTitle}</strong>
                  <span>{t.ai.memoryDesc}</span>
                </div>
              </div>
              <div className="ai-feat">
                <Sparkles size={18} className="ai-feat-icon" />
                <div>
                  <strong>{t.ai.briefingTitle}</strong>
                  <span>{t.ai.briefingDesc}</span>
                </div>
              </div>
              <div className="ai-feat">
                <Sparkles size={18} className="ai-feat-icon" />
                <div>
                  <strong>{t.ai.reminderTitle}</strong>
                  <span>{t.ai.reminderDesc}</span>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  )
}
