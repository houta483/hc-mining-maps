import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

(function () {
  if (typeof window === 'undefined') return
  if (window.__suppressMapboxEventsPatched) return

  try {
    const origFetch = typeof window.fetch === 'function' ? window.fetch.bind(window) : null
    if (origFetch) {
      window.fetch = (...args) => {
        try {
          const url = String(args[0] || '')
          if (url.includes('events.mapbox.com/events')) {
            return Promise.resolve(new Response(null, { status: 204 }))
          }
        } catch {}
        return origFetch(...args)
      }
    }

    const XO = typeof XMLHttpRequest !== 'undefined' && XMLHttpRequest.prototype && XMLHttpRequest.prototype.open
    if (XO) {
      XMLHttpRequest.prototype.open = function (method, url, ...rest) {
        try {
          if (String(url || '').includes('events.mapbox.com/events')) {
            this.send = () => {}
          }
        } catch {}
        return XO.call(this, method, url, ...rest)
      }
    }

    const origBeacon = typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function'
      ? navigator.sendBeacon.bind(navigator)
      : null
    if (origBeacon) {
      navigator.sendBeacon = (url, data) => {
        try {
          if (String(url || '').includes('events.mapbox.com/events')) {
            return true
          }
        } catch {}
        return origBeacon(url, data)
      }
    }

    window.__suppressMapboxEventsPatched = true
  } catch {}
})()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

