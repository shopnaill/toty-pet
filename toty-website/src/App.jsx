import { lazy, Suspense } from 'react'
import Navbar from './components/Navbar'
import Hero from './components/Hero'
import Stats from './components/Stats'
import Features from './components/Features'
import GazeGuard from './components/GazeGuard'
import AIChat from './components/AIChat'
import Showcase from './components/Showcase'
import FeatureGrid from './components/FeatureGrid'
import Download from './components/Download'
import Footer from './components/Footer'
import BackToTop from './components/BackToTop'
import FloatingPet from './components/FloatingPet'

const Testimonials = lazy(() => import('./components/Testimonials'))
const UseCases = lazy(() => import('./components/UseCases'))
const Comparison = lazy(() => import('./components/Comparison'))
const FeatureExplorer = lazy(() => import('./components/FeatureExplorer'))
const Privacy = lazy(() => import('./components/Privacy'))
const KeyboardShortcuts = lazy(() => import('./components/KeyboardShortcuts'))
const Changelog = lazy(() => import('./components/Changelog'))
const Community = lazy(() => import('./components/Community'))
const FAQ = lazy(() => import('./components/FAQ'))
const Newsletter = lazy(() => import('./components/Newsletter'))

function LazySection({ children }) {
  return <Suspense fallback={<div style={{ minHeight: 200 }} />}>{children}</Suspense>
}

export default function App() {
  return (
    <>
      <Navbar />
      <Hero />
      <Stats />
      <Features />
      <GazeGuard />
      <AIChat />
      <LazySection><Testimonials /></LazySection>
      <LazySection><UseCases /></LazySection>
      <Showcase />
      <FeatureGrid />
      <LazySection><FeatureExplorer /></LazySection>
      <LazySection><Comparison /></LazySection>
      <LazySection><Privacy /></LazySection>
      <LazySection><KeyboardShortcuts /></LazySection>
      <LazySection><Changelog /></LazySection>
      <LazySection><Community /></LazySection>
      <LazySection><FAQ /></LazySection>
      <LazySection><Newsletter /></LazySection>
      <Download />
      <Footer />
      <BackToTop />
      <FloatingPet />
    </>
  )
}
