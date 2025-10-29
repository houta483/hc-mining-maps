import React, { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import axios from 'axios'
import './Map.css'

function Map({ onLogout }) {
  const mapContainer = useRef(null)
  const map = useRef(null)
  const [loading, setLoading] = useState(true)
  const [holeCount, setHoleCount] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => {
    // Get Mapbox token from environment (injected by Docker at runtime)
    const mapboxToken = window.MAPBOX_TOKEN || ''

    if (!mapboxToken || mapboxToken.length < 30) {
      setError('Mapbox token not configured. Please set MAPBOX_TOKEN environment variable.')
      setLoading(false)
      return
    }

    // Initialize Mapbox
    mapboxgl.accessToken = mapboxToken
    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/satellite-streets-v12',
      center: [-96.432978, 32.484672],
      zoom: 15
    })

    // Load borehole data when map loads
    map.current.on('load', () => {
      loadBoreholeData()
    })

    // Cleanup
    return () => {
      if (map.current) {
        map.current.remove()
      }
    }
  }, [])

  const loadBoreholeData = async () => {
    try {
      const token = localStorage.getItem('token')
      const response = await axios.get('/api/geojson', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })

      const geojson = response.data

      if (geojson.features.length === 0) {
        setError('No borehole data available. The pipeline may still be processing.')
        setLoading(false)
        return
      }

      // Add GeoJSON source
      if (map.current.getSource('boreholes')) {
        map.current.getSource('boreholes').setData(geojson)
      } else {
        map.current.addSource('boreholes', {
          type: 'geojson',
          data: geojson
        })

        // Add circle layer
        map.current.addLayer({
          id: 'boreholes',
          type: 'circle',
          source: 'boreholes',
          paint: {
            'circle-radius': 10,
            'circle-color': '#1a73e8',
            'circle-stroke-width': 3,
            'circle-stroke-color': '#fff'
          }
        })

        // Add labels
        map.current.addLayer({
          id: 'borehole-labels',
          type: 'symbol',
          source: 'boreholes',
          layout: {
            'text-field': ['get', 'hole_id'],
            'text-size': 14,
            'text-offset': [0, -2]
          },
          paint: {
            'text-color': '#fff',
            'text-halo-color': '#000',
            'text-halo-width': 2
          }
        })

        // Add click handler
        map.current.on('click', 'boreholes', (e) => {
          const feature = e.features[0]
          const description = feature.properties.description || ''
          
          // Parse the HTML description from KML
          let formattedHTML = '<p>No data available</p>'
          
          if (description) {
            // Extract intervals from the description HTML
            // Pattern: "start–end ft → FM value <a href="...">Box Report</a><br>"
            const intervalPattern = /(\d+)[–-](\d+)\s*ft\s*→\s*FM\s*([\d.]+)\s*<a[^>]+href="([^"]+)"[^>]*>Box Report<\/a>/gi
            const matches = [...description.matchAll(intervalPattern)]
            
            if (matches.length > 0) {
              const intervalRows = matches.map(match => {
                const start = match[1]
                const end = match[2]
                const fm = parseFloat(match[3]).toFixed(2)
                const link = match[4]
                
                return `
                  <div style="padding: 10px 0; border-bottom: 1px solid #e8e8e8; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                      <strong style="color: #333; font-size: 1em;">${start}–${end} ft</strong>
                    </div>
                    <div style="color: #666; margin: 0 15px;">
                      FM: <strong style="color: #333;">${fm}</strong>
                    </div>
                    <div>
                      <a href="${link}" target="_blank" style="color: #1a73e8; text-decoration: none; font-size: 0.9em; padding: 4px 8px; border: 1px solid #1a73e8; border-radius: 4px;">Box Report →</a>
                    </div>
                  </div>
                `
              }).join('')
              
              formattedHTML = `
                <div style="width: 100%;">
                  ${intervalRows}
                </div>
              `
            } else {
              // Fallback: just show the description as-is
              formattedHTML = `<div>${description}</div>`
            }
          }
          
          new mapboxgl.Popup({ maxWidth: '450px', className: 'borehole-popup' })
            .setLngLat(e.lngLat)
            .setHTML(`
              <div style="padding: 12px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                <h3 style="margin: 0 0 16px 0; font-size: 1.3em; font-weight: 600; color: #1a1a1a; padding-bottom: 8px; border-bottom: 2px solid #e0e0e0;">
                  ${feature.properties.name}
                </h3>
                <div style="color: #555; font-size: 0.95em;">
                  ${formattedHTML}
                </div>
              </div>
            `)
            .addTo(map.current)
        })
      }

      // Fit to bounds
      const bounds = geojson.features.reduce((bounds, feature) => {
        return bounds.extend(feature.geometry.coordinates)
      }, new mapboxgl.LngLatBounds())

      map.current.fitBounds(bounds, { padding: 50 })

      setHoleCount(geojson.features.length)
      setLoading(false)
      setError('')
    } catch (err) {
      if (err.response?.status === 401) {
        // Token expired, logout
        onLogout()
      } else {
        setError(`Error loading data: ${err.response?.data?.error || err.message}`)
        setLoading(false)
      }
    }
  }

  return (
    <div className="map-container">
      <div className="sidebar">
        <h1>🏔️ HC Mining</h1>
        <p><strong>Borehole Analysis Map</strong></p>
        <div className="status">
          <div className="status-item">
            📊 <strong>Mine Area:</strong> <span>UP-B</span>
          </div>
          <div className="status-item">
            📍 <strong>Holes:</strong> <span>{holeCount}</span>
          </div>
          <div className="status-item">
            🔄 <strong>Auto-Update:</strong> Every 10 min
          </div>
        </div>
        {loading && <div className="loading">Loading map...</div>}
        {error && <div className="error">{error}</div>}
        <button onClick={onLogout} className="logout-button">
          Logout
        </button>
      </div>
      <div ref={mapContainer} className="map" />
    </div>
  )
}

export default Map

