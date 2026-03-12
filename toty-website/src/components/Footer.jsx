import { Shield, Github, Heart } from 'lucide-react'
import { useLang } from '../i18n/LangContext'
import './Footer.css'

const footerLinks = {
  product: ['#features', '#gaze-guard', '#ai-chat', '#download'],
  resources: ['#feature-explorer', '#changelog', '#faq', '#faq'],
  community: ['https://github.com/mfoud5391/toty', '#community', '#community', '#community'],
}

export default function Footer() {
  const { t } = useLang()
  const groups = [
    { title: t.footer.product, items: t.footer.productItems, links: footerLinks.product },
    { title: t.footer.resources, items: t.footer.resourceItems, links: footerLinks.resources },
    { title: t.footer.community, items: t.footer.communityItems, links: footerLinks.community },
  ]

  return (
    <footer className="footer">
      <div className="container">
        <div className="footer-top">
          <div className="footer-brand">
            <div className="footer-logo">
              <div className="brand-icon"><Shield size={18} /></div>
              <span className="brand-text">Toty</span>
            </div>
            <p className="footer-tagline">{t.footer.tagline}</p>
          </div>

          {groups.map((group, i) => (
            <div key={i} className="footer-col">
              <h4 className="footer-col-title">{group.title}</h4>
              {group.items.map((item, j) => (
                <a key={j} href={group.links[j]} className="footer-link"
                  {...(group.links[j].startsWith('http') ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                >{item}</a>
              ))}
            </div>
          ))}
        </div>

        <div className="footer-bottom">
          <p className="footer-copy">
            &copy; {new Date().getFullYear()} {t.footer.copy}{' '}
            <Heart size={13} fill="var(--red)" color="var(--red)" style={{ verticalAlign: 'middle' }} />{' '}
            {t.footer.copyEnd}
          </p>
          <div className="footer-bottom-links">
            <a href="https://github.com/mfoud5391/toty" target="_blank" rel="noopener noreferrer" className="footer-bottom-link">
              <Github size={16} />
              <span>{t.footer.starGithub}</span>
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}
