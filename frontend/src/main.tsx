import React, { Suspense, lazy } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles.css'

// UI-10: the presentation globe is its own full-screen view and its own lazily loaded chunk.
const GlobeView = lazy(() => import('./Globe'))
const globe = new URLSearchParams(location.search).get('view') === 'globe'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{globe ? <Suspense fallback={<main className="globe-loading" role="status">Loading the globe…</main>}><GlobeView /></Suspense> : <App />}</React.StrictMode>,
)
