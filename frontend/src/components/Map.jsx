import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
// Mapbox worker fix for CSP, Electron, ad blockers
// eslint-disable-next-line import/no-webpack-loader-syntax
import MapboxWorker from 'mapbox-gl/dist/mapbox-gl-csp-worker?worker'

mapboxgl.workerClass = MapboxWorker

import axios from 'axios'
import './Map.css'
import OverlayUploadPanel from './OverlayUploadPanel'

const MAX_UPLOAD_BYTES = 200 * 1024 * 1024
const ALIGNMENT_SOURCE_ID = 'overlay-alignment-preview'
const ALIGNMENT_LAYER_ID = 'overlay-alignment-preview-layer'
const HANDLE_TYPES = Object.freeze({
  CENTER: 'center',
  SCALE: 'scale',
  ANCHOR: 'anchor'
})
const MIN_SCALE = 0.05
const MAX_SCALE = 50

const clamp = (value, min, max) => Math.min(max, Math.max(min, value))

const getAxisVectors = (state) => {
  const cos = Math.cos(state.rotation)
  const sin = Math.sin(state.rotation)

  return {
    axisX: { x: cos * state.halfWidth, y: sin * state.halfWidth },
    axisY: { x: -sin * state.halfHeight, y: cos * state.halfHeight }
  }
}

const getCornerMercator = (state, anchorType) => {
  const { axisX, axisY } = getAxisVectors(state)
  const z = state.center.z ?? 0

  switch (anchorType) {
    case 'topLeft':
      return {
        x: state.center.x - axisX.x - axisY.x,
        y: state.center.y - axisX.y - axisY.y,
        z
      }
    case 'topRight':
      return {
        x: state.center.x + axisX.x - axisY.x,
        y: state.center.y + axisX.y - axisY.y,
        z
      }
    case 'bottomRight':
      return {
        x: state.center.x + axisX.x + axisY.x,
        y: state.center.y + axisX.y + axisY.y,
        z
      }
    case 'bottomLeft':
      return {
        x: state.center.x - axisX.x + axisY.x,
        y: state.center.y - axisX.y + axisY.y,
        z
      }
    default:
      return { x: state.center.x, y: state.center.y, z }
  }
}

const getCenterFromAnchor = (anchor, axisX, axisY, anchorType, baseZ) => {
  switch (anchorType) {
    case 'topLeft':
      return {
        x: anchor.x + axisX.x + axisY.x,
        y: anchor.y + axisX.y + axisY.y,
        z: baseZ
      }
    case 'topRight':
      return {
        x: anchor.x - axisX.x + axisY.x,
        y: anchor.y - axisX.y + axisY.y,
        z: baseZ
      }
    case 'bottomRight':
      return {
        x: anchor.x - axisX.x - axisY.x,
        y: anchor.y - axisX.y - axisY.y,
        z: baseZ
      }
    case 'bottomLeft':
      return {
        x: anchor.x + axisX.x - axisY.x,
        y: anchor.y + axisX.y - axisY.y,
        z: baseZ
      }
    default:
      return {
        x: anchor.x,
        y: anchor.y,
        z: baseZ
      }
  }
}

const toLocalDateTimeInputValue = (date) => {
  const pad = (value) => `${value}`.padStart(2, '0')
  const year = date.getFullYear()
  const month = pad(date.getMonth() + 1)
  const day = pad(date.getDate())
  const hours = pad(date.getHours())
  const minutes = pad(date.getMinutes())

  return `${year}-${month}-${day}T${hours}:${minutes}`
}

const toLocalInputValueFromIso = (value) => {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return toLocalDateTimeInputValue(date)
}

const createInitialOverlayFormValues = () => ({
  name: '',
  captureDate: toLocalDateTimeInputValue(new Date()),
  opacity: 0.85,
  visible: true
})

const degreesToRadians = (degrees) => (degrees * Math.PI) / 180
const radiansToDegrees = (radians) => (radians * 180) / Math.PI

const isValidLngLat = (value) => Array.isArray(value) && value.length === 2 && value.every((num) => Number.isFinite(num))

// Normalize various LngLatLike inputs to a clamped [lng, lat] array
const normalizeLngLat = (input) => {
  try {
    let lng, lat
    if (Array.isArray(input) && input.length >= 2) {
      ;[lng, lat] = input
    } else if (input && typeof input === 'object') {
      if (Number.isFinite(input.lng) && Number.isFinite(input.lat)) {
        lng = input.lng
        lat = input.lat
      } else if (Number.isFinite(input.lon) && Number.isFinite(input.lat)) {
        lng = input.lon
        lat = input.lat
      } else if (Number.isFinite(input.x) && Number.isFinite(input.y)) {
        // Some callers may pass objects with x,y as lng,lat
        lng = input.x
        lat = input.y
      }
    }
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null

    // Wrap longitude to [-180, 180)
    const wrappedLng = ((((lng + 180) % 360) + 360) % 360) - 180
    // Clamp latitude to WebMercator valid range
    const clampedLat = Math.max(-85.051129, Math.min(85.051129, lat))

    return [wrappedLng, clampedLat]
  } catch {
    return null
  }
}

function Map({ onLogout }) {
  const mapContainer = useRef(null)
  const map = useRef(null)
  const datasetBoundsRef = useRef(null)
  const autoFitEnabledRef = useRef(false)
  const overlayObjectUrlRef = useRef(null)
  const overlayPreviewImageRef = useRef(null)
  const alignmentHandlesRef = useRef({ center: null, scale: null, anchor: null })
  const alignmentDragStateRef = useRef(null)
  const overlayPanDragRef = useRef(null)
  const alignmentStateRef = useRef(null)
  const alignmentDraggingHandleRef = useRef(null)
  const overlayVisibilityBeforeAlignmentRef = useRef(null)
  const alignmentOriginalCoordinatesRef = useRef(null)
  const alignmentAnchorRef = useRef('center')
  const alignmentAutoStartRef = useRef(false)

  const [loading, setLoading] = useState(true)
  const [holeCount, setHoleCount] = useState(0)
  const [error, setError] = useState('')
  const [pipelineStatus, setPipelineStatus] = useState(null)
  const [triggeringRun, setTriggeringRun] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')
  const [refreshAfterManual, setRefreshAfterManual] = useState(false)

  const [overlayMetadata, setOverlayMetadata] = useState(null)
  const [overlayEnabled, setOverlayEnabled] = useState(true)
  const [overlayOpacity, setOverlayOpacity] = useState(0.85)

  const [isOverlayUploadOpen, setOverlayUploadOpen] = useState(false)
  const [overlayUploadFile, setOverlayUploadFile] = useState(null)
  const [overlayUploadPreviewUrl, setOverlayUploadPreviewUrl] = useState('')
  const [overlayImageSize, setOverlayImageSize] = useState({ width: 0, height: 0 })
  const [overlayFormValues, setOverlayFormValues] = useState(() => createInitialOverlayFormValues())
  const [overlayUploadError, setOverlayUploadError] = useState('')
  const [overlayUploading, setOverlayUploading] = useState(false)
  const [overlayUploadStep, setOverlayUploadStep] = useState(0)
  const [previewReadySignal, setPreviewReadySignal] = useState(0)

  const [autoFitEnabled, setAutoFitEnabled] = useState(false)

  const [isAlignmentActive, setAlignmentActive] = useState(false)
  const [alignmentState, setAlignmentState] = useState(null)
  const [overlayAlignment, setOverlayAlignment] = useState(null)
  const [alignmentMode, setAlignmentMode] = useState('idle')
  const [alignmentSaving, setAlignmentSaving] = useState(false)
  const handleAlignmentCompleteRef = useRef(() => {})
  const [alignmentAnchor, setAlignmentAnchor] = useState('center')
  const [alignmentPreviewOpacity, setAlignmentPreviewOpacity] = useState(0.85)

  const imageCorners = useMemo(() => {
    if (!overlayImageSize.width || !overlayImageSize.height) {
      return null
    }

    return [
      [0, 0],
      [overlayImageSize.width, 0],
      [overlayImageSize.width, overlayImageSize.height],
      [0, overlayImageSize.height]
    ]
  }, [overlayImageSize.width, overlayImageSize.height])

  const overlayReady = overlayUploadStep === 2 && Boolean(overlayAlignment?.mapCorners)

  const formatTimestamp = useCallback((timestamp) => {
    if (!timestamp) return '—'
    try {
      return new Date(timestamp).toLocaleString()
    } catch (err) {
      console.warn('Failed to format timestamp', err)
      return timestamp
    }
  }, [])

  const formatOverlayDate = useCallback((value) => {
    if (!value) {
      return null
    }

    const date = new Date(value)
    if (Number.isNaN(date.getTime())) {
      return value
    }

    return date.toLocaleString()
  }, [])

  const removeAlignmentHandles = useCallback(() => {
    Object.values(alignmentHandlesRef.current).forEach((marker) => marker?.remove())
    alignmentHandlesRef.current = { center: null, scale: null, anchor: null }
    alignmentDragStateRef.current = null
    alignmentDraggingHandleRef.current = null
  }, [])

  const clearAlignmentUI = useCallback(() => {
    removeAlignmentHandles()

    const mapInstance = map.current
    if (!mapInstance || !mapInstance.style) {
      return
    }

    if (mapInstance.getLayer(ALIGNMENT_LAYER_ID)) {
      mapInstance.removeLayer(ALIGNMENT_LAYER_ID)
    }

    if (mapInstance.getSource(ALIGNMENT_SOURCE_ID)) {
      mapInstance.removeSource(ALIGNMENT_SOURCE_ID)
    }
  }, [removeAlignmentHandles])

  const restoreOverlayVisibility = useCallback(() => {
    if (overlayVisibilityBeforeAlignmentRef.current !== null) {
      setOverlayEnabled(overlayVisibilityBeforeAlignmentRef.current)
      overlayVisibilityBeforeAlignmentRef.current = null
    }
  }, [])

  const handleAlignmentAnchorChange = useCallback((nextAnchor) => {
    alignmentAnchorRef.current = nextAnchor
    setAlignmentAnchor(nextAnchor)
  }, [])

  const resetOverlayUploadState = useCallback(() => {
    clearAlignmentUI()

    if (overlayObjectUrlRef.current) {
      URL.revokeObjectURL(overlayObjectUrlRef.current)
      overlayObjectUrlRef.current = null
    }

    overlayPreviewImageRef.current = null

    setOverlayUploadFile(null)
    setOverlayUploadPreviewUrl('')
    setOverlayImageSize({ width: 0, height: 0 })
    setOverlayFormValues(createInitialOverlayFormValues())
    setOverlayUploadError('')
    setOverlayUploading(false)
    setOverlayUploadStep(0)
    setAlignmentActive(false)
    setAlignmentState(null)
    setOverlayAlignment(null)
    setAlignmentMode('idle')
    setAlignmentSaving(false)
    alignmentOriginalCoordinatesRef.current = null
    overlayVisibilityBeforeAlignmentRef.current = null
    handleAlignmentAnchorChange('center')
    alignmentAutoStartRef.current = false
  }, [clearAlignmentUI, handleAlignmentAnchorChange])

const alignmentRotationDegrees = useMemo(() => {
    if (!alignmentState || typeof alignmentState.rotation !== 'number') {
      return 0
    }

    const degrees = radiansToDegrees(alignmentState.rotation)
    if (!Number.isFinite(degrees)) {
      return 0
    }

    return ((degrees + 540) % 360) - 180
  }, [alignmentState])

  const handleOpenOverlayUpload = useCallback(() => {
    resetOverlayUploadState()

    const initialValues = createInitialOverlayFormValues()

    if (overlayMetadata?.name) {
      initialValues.name = overlayMetadata.name
    }

    if (overlayMetadata?.captureDate) {
      initialValues.captureDate = toLocalInputValueFromIso(overlayMetadata.captureDate)
    }

    if (overlayMetadata?.opacity !== undefined && overlayMetadata.opacity !== null) {
      const parsedOpacity = Number(overlayMetadata.opacity)
      if (Number.isFinite(parsedOpacity)) {
        initialValues.opacity = clamp(parsedOpacity, 0, 1)
      }
    }

    if (overlayMetadata?.visible !== undefined) {
      initialValues.visible = overlayMetadata.visible !== false
    }

    setOverlayFormValues(initialValues)
    setOverlayUploadError('')
    setOverlayUploadOpen(true)
  }, [overlayMetadata, resetOverlayUploadState])

  const handleCloseOverlayUpload = useCallback(() => {
    resetOverlayUploadState()
    setOverlayUploadOpen(false)
  }, [resetOverlayUploadState])

  const handleOverlayFileSelected = useCallback(
    (event) => {
      const files = event.target.files
      if (!files || !files.length) {
        return
      }

      const file = files[0]

      if (file.size > MAX_UPLOAD_BYTES) {
        setOverlayUploadError('Image exceeds the 200 MB upload limit. Compress the file and try again.')
        event.target.value = ''
        return
      }

      if (!/^image\/(png|jpe?g|webp)$/i.test(file.type)) {
        setOverlayUploadError('Unsupported image type. Use PNG, JPEG, or WebP.')
        event.target.value = ''
        return
      }

      clearAlignmentUI()
      setAlignmentActive(false)
      setOverlayAlignment(null)
      setAlignmentState(null)
      alignmentOriginalCoordinatesRef.current = null
      overlayVisibilityBeforeAlignmentRef.current = null
      handleAlignmentAnchorChange('center')

      if (overlayObjectUrlRef.current) {
        URL.revokeObjectURL(overlayObjectUrlRef.current)
        overlayObjectUrlRef.current = null
      }

      overlayPreviewImageRef.current = null

      const previewUrl = URL.createObjectURL(file)
      overlayObjectUrlRef.current = previewUrl

      setOverlayUploadFile(file)
      setOverlayUploadPreviewUrl(previewUrl)
      setOverlayUploadError('')

      const image = new Image()
      image.onload = () => {
        overlayPreviewImageRef.current = image
        setOverlayImageSize({
          width: image.naturalWidth,
          height: image.naturalHeight
        })
        setPreviewReadySignal((prev) => prev + 1)
      }
      image.onerror = () => {
        overlayPreviewImageRef.current = null
        alignmentAutoStartRef.current = false
        setOverlayImageSize({ width: 0, height: 0 })
        setOverlayUploadError('Unable to read image dimensions. Try a different file.')
      }
      image.src = previewUrl

      setOverlayFormValues((prev) => ({
        ...prev,
        name: prev.name || file.name.replace(/\.[^.]+$/, '')
      }))

      setOverlayUploadStep(0)
      setAlignmentMode('upload')
      event.target.value = ''
    },
    [clearAlignmentUI, handleAlignmentAnchorChange]
  )

  const handleOverlayRemovePreview = useCallback(() => {
    clearAlignmentUI()

    if (overlayObjectUrlRef.current) {
      URL.revokeObjectURL(overlayObjectUrlRef.current)
      overlayObjectUrlRef.current = null
    }

    overlayPreviewImageRef.current = null

    setOverlayUploadFile(null)
    setOverlayUploadPreviewUrl('')
    setOverlayImageSize({ width: 0, height: 0 })
    setOverlayUploadStep(0)
    setAlignmentActive(false)
    setOverlayAlignment(null)
    setAlignmentState(null)
    setAlignmentMode('idle')
    setAlignmentSaving(false)
    alignmentOriginalCoordinatesRef.current = null
    overlayVisibilityBeforeAlignmentRef.current = null
    handleAlignmentAnchorChange('center')
    alignmentAutoStartRef.current = false
  }, [clearAlignmentUI, handleAlignmentAnchorChange])

  const handleOverlayFormValueChange = useCallback((key, value) => {
    setOverlayFormValues((prev) => ({
      ...prev,
      [key]: value
    }))
  }, [])

  const handleAlignmentRotationChange = useCallback((nextValue) => {
    const parsed = Number(nextValue)
    if (!Number.isFinite(parsed)) {
      return
    }

    setAlignmentState((prev) => {
      if (!prev) {
        return prev
      }

      return {
        ...prev,
        rotation: degreesToRadians(parsed)
      }
    })
  }, [])

  const alignmentAnchorOptions = useMemo(
    () => [
      { label: 'Center', value: 'center' },
      { label: 'Top-left', value: 'topLeft' },
      { label: 'Top-right', value: 'topRight' },
      { label: 'Bottom-right', value: 'bottomRight' },
      { label: 'Bottom-left', value: 'bottomLeft' }
    ],
    []
  )

  const computeInitialAlignmentState = useCallback(() => {
    if (!map.current || !overlayImageSize.width || !overlayImageSize.height) {
      return null
    }

    const centerLngLat = map.current.getCenter()
    const centerMerc = mapboxgl.MercatorCoordinate.fromLngLat(centerLngLat)

    const canvas = map.current.getCanvas()
    const shorterSide = Math.min(canvas.width, canvas.height)
    const baseWidthPx = clamp(shorterSide * 0.6, 200, shorterSide * 0.9)
    const aspect = overlayImageSize.width / overlayImageSize.height || 1
    const halfWidthPx = baseWidthPx / 2
    const halfHeightPx = halfWidthPx / aspect

    const centerPoint = map.current.project(centerLngLat)
    const rightLngLat = map.current.unproject([centerPoint.x + halfWidthPx, centerPoint.y])
    const topLngLat = map.current.unproject([centerPoint.x, centerPoint.y - halfHeightPx])

    const rightMerc = mapboxgl.MercatorCoordinate.fromLngLat(rightLngLat)
    const topMerc = mapboxgl.MercatorCoordinate.fromLngLat(topLngLat)

    const halfWidth = Math.abs(rightMerc.x - centerMerc.x)
    const halfHeight = Math.abs(topMerc.y - centerMerc.y)

    if (!halfWidth || !halfHeight) {
      return null
    }

    return {
      center: { x: centerMerc.x, y: centerMerc.y, z: centerMerc.z ?? 0 },
      halfWidth,
      halfHeight,
      rotation: 0
    }
  }, [overlayImageSize.height, overlayImageSize.width])

  const computeAlignmentGeometry = useCallback((state) => {
    if (!state) {
      return null
    }

    const { center, halfWidth, halfHeight, rotation } = state
    const cos = Math.cos(rotation)
    const sin = Math.sin(rotation)
    const axisX = { x: cos * halfWidth, y: sin * halfWidth }
    const axisY = { x: -sin * halfHeight, y: cos * halfHeight }

    const toLngLatArray = (point) => {
      const coord = new mapboxgl.MercatorCoordinate(point.x, point.y, center.z ?? 0)
      const { lng, lat } = coord.toLngLat()
      return [lng, lat]
    }

    const coordinates = [
      toLngLatArray({ x: center.x - axisX.x - axisY.x, y: center.y - axisX.y - axisY.y }),
      toLngLatArray({ x: center.x + axisX.x - axisY.x, y: center.y + axisX.y - axisY.y }),
      toLngLatArray({ x: center.x + axisX.x + axisY.x, y: center.y + axisX.y + axisY.y }),
      toLngLatArray({ x: center.x - axisX.x + axisY.x, y: center.y - axisX.y + axisY.y })
    ]

    return {
      coordinates,
      handles: {
        center: toLngLatArray(center),
        scale: toLngLatArray({ x: center.x + axisX.x + axisY.x, y: center.y + axisX.y + axisY.y })
      },
      anchors: {
        topLeft: toLngLatArray({ x: center.x - axisX.x - axisY.x, y: center.y - axisX.y - axisY.y }),
        topRight: toLngLatArray({ x: center.x + axisX.x - axisY.x, y: center.y + axisX.y - axisY.y }),
        bottomRight: toLngLatArray({ x: center.x + axisX.x + axisY.x, y: center.y + axisX.y + axisY.y }),
        bottomLeft: toLngLatArray({ x: center.x - axisX.x + axisY.x, y: center.y - axisX.y + axisY.y })
      }
    }
  }, [])

  const computeAlignmentStateFromCorners = useCallback((corners) => {
    if (!map.current || !Array.isArray(corners) || corners.length !== 4) {
      return null
    }

    try {
      const mercCorners = corners.map((corner) => {
        if (!isValidLngLat(corner)) {
          throw new Error('Invalid corner provided')
        }
        const [lng, lat] = corner
        return mapboxgl.MercatorCoordinate.fromLngLat({ lng, lat })
      })

      const center = mercCorners.reduce(
        (acc, coord) => {
          acc.x += coord.x
          acc.y += coord.y
          acc.z += coord.z ?? 0
          return acc
        },
        { x: 0, y: 0, z: 0 }
      )

      center.x /= mercCorners.length
      center.y /= mercCorners.length
      center.z /= mercCorners.length

      const avgRight = {
        x: (mercCorners[1].x + mercCorners[2].x) / 2,
        y: (mercCorners[1].y + mercCorners[2].y) / 2
      }

      const avgTop = {
        x: (mercCorners[0].x + mercCorners[1].x) / 2,
        y: (mercCorners[0].y + mercCorners[1].y) / 2
      }

      const axisX = {
        x: avgRight.x - center.x,
        y: avgRight.y - center.y
      }

      const axisY = {
        x: avgTop.x - center.x,
        y: avgTop.y - center.y
      }

      const halfWidth = Math.hypot(axisX.x, axisX.y)
      const halfHeight = Math.hypot(axisY.x, axisY.y)

      if (!halfWidth || !halfHeight) {
        return null
      }

      const rotation = Math.atan2(axisX.y, axisX.x)

      return {
        center: { x: center.x, y: center.y, z: center.z ?? 0 },
        halfWidth,
        halfHeight,
        rotation
      }
    } catch (error) {
      console.error('Failed to compute alignment state from corners', error)
      return null
    }
  }, [])

  const ensureAlignmentLayer = useCallback((coordinates) => {
    const mapInstance = map.current
    if (!mapInstance || !mapInstance.style || !mapInstance.isStyleLoaded() || !overlayUploadPreviewUrl) {
      return
    }

    const existingSource = mapInstance.getSource(ALIGNMENT_SOURCE_ID)
    if (!existingSource) {
      mapInstance.addSource(ALIGNMENT_SOURCE_ID, {
        type: 'image',
        url: overlayUploadPreviewUrl,
        coordinates
      })

      const beforeLayer = mapInstance.getLayer('boreholes') ? 'boreholes' : undefined

      mapInstance.addLayer(
        {
          id: ALIGNMENT_LAYER_ID,
          type: 'raster',
          source: ALIGNMENT_SOURCE_ID,
          paint: {
            'raster-opacity': alignmentPreviewOpacity,
            'raster-fade-duration': 0
          }
        },
        beforeLayer
      )
    } else {
      if (typeof existingSource.updateImage === 'function') {
        existingSource.updateImage({ url: overlayUploadPreviewUrl, coordinates })
      } else {
        if (typeof existingSource.setCoordinates === 'function') {
          existingSource.setCoordinates(coordinates)
        }
        if (overlayPreviewImageRef.current?.complete && typeof existingSource.setImage === 'function') {
          existingSource.setImage(overlayPreviewImageRef.current)
        }
      }
    }

    if (mapInstance.getLayer(ALIGNMENT_LAYER_ID)) {
      mapInstance.setPaintProperty(ALIGNMENT_LAYER_ID, 'raster-opacity', alignmentPreviewOpacity)
    }
  }, [alignmentPreviewOpacity, overlayUploadPreviewUrl])

  const handleAlignmentPreviewOpacityChange = useCallback(
    (nextValue) => {
      const parsed = Number(nextValue)
      if (!Number.isFinite(parsed)) {
        return
      }

      const clamped = clamp(parsed, 0, 1)
      setAlignmentPreviewOpacity(clamped)
      setOverlayFormValues((prev) => ({
        ...prev,
        opacity: clamped
      }))

      if (alignmentState) {
        const geometry = computeAlignmentGeometry(alignmentState)
        if (geometry) {
          ensureAlignmentLayer(geometry.coordinates)
        }
      }
    },
    [alignmentState, computeAlignmentGeometry, ensureAlignmentLayer]
  )

  const attachCenterHandle = useCallback(() => {
    if (!map.current) {
      return null
    }

    let marker = alignmentHandlesRef.current.center
    if (!marker) {
      const element = document.createElement('div')
      element.className = 'overlay-handle overlay-handle-center'

      marker = new mapboxgl.Marker({ element, draggable: true })
      const initialLngLat = map.current.getCenter()
      if (initialLngLat) {
        marker.setLngLat(initialLngLat)
      }
      marker.addTo(map.current)

      marker.on('dragstart', () => {
        alignmentDraggingHandleRef.current = HANDLE_TYPES.CENTER
      })

      marker.on('drag', () => {
        const lngLat = marker.getLngLat()
        const merc = mapboxgl.MercatorCoordinate.fromLngLat(lngLat)
        setAlignmentState((prev) => {
          if (!prev) {
            return prev
          }

          return {
            ...prev,
            center: { x: merc.x, y: merc.y, z: merc.z ?? 0 }
          }
        })
      })

      marker.on('dragend', () => {
        alignmentDraggingHandleRef.current = null
      })

      alignmentHandlesRef.current.center = marker
    }

    return marker
  }, [])

  const attachScaleHandle = useCallback(() => {
    if (!map.current) {
      return null
    }

    let marker = alignmentHandlesRef.current.scale
    if (!marker) {
      const element = document.createElement('div')
      element.className = 'overlay-handle overlay-handle-scale'

      marker = new mapboxgl.Marker({ element, draggable: true })
      const initialLngLat = map.current.getCenter()
      if (initialLngLat) {
        marker.setLngLat(initialLngLat)
      }
      marker.addTo(map.current)

      marker.on('dragstart', () => {
        alignmentDraggingHandleRef.current = HANDLE_TYPES.SCALE
        const snapshot = alignmentStateRef.current
        if (snapshot) {
          alignmentDragStateRef.current = {
            center: { ...snapshot.center },
            halfWidth: snapshot.halfWidth,
            halfHeight: snapshot.halfHeight,
            rotation: snapshot.rotation,
            anchorType: alignmentAnchorRef.current,
            anchorMerc: getCornerMercator(snapshot, alignmentAnchorRef.current)
          }
        }
      })

      marker.on('drag', () => {
        const snapshot = alignmentDragStateRef.current
        if (!snapshot) {
          return
        }

        const lngLat = marker.getLngLat()
        const merc = mapboxgl.MercatorCoordinate.fromLngLat(lngLat)

        const vector = {
          x: merc.x - snapshot.center.x,
          y: merc.y - snapshot.center.y
        }

        const cos = Math.cos(snapshot.rotation)
        const sin = Math.sin(snapshot.rotation)
        const axisXUnit = { x: cos, y: sin }
        const axisYUnit = { x: -sin, y: cos }

        const projectionX = vector.x * axisXUnit.x + vector.y * axisXUnit.y
        const projectionY = vector.x * axisYUnit.x + vector.y * axisYUnit.y

        const scaleX = Math.abs(projectionX) / (snapshot.halfWidth || 1e-6)
        const scaleY = Math.abs(projectionY) / (snapshot.halfHeight || 1e-6)
        const scale = clamp(Math.max(scaleX, scaleY), MIN_SCALE, MAX_SCALE)

        const nextHalfWidth = snapshot.halfWidth * scale
        const nextHalfHeight = snapshot.halfHeight * scale
        const axisX = { x: axisXUnit.x * nextHalfWidth, y: axisXUnit.y * nextHalfWidth }
        const axisY = { x: axisYUnit.x * nextHalfHeight, y: axisYUnit.y * nextHalfHeight }

        let nextCenter = { ...snapshot.center }
        if (snapshot.anchorType && snapshot.anchorType !== 'center' && snapshot.anchorMerc) {
          nextCenter = getCenterFromAnchor(
            snapshot.anchorMerc,
            axisX,
            axisY,
            snapshot.anchorType,
            snapshot.center.z ?? 0
          )
        }

        setAlignmentState({
          center: nextCenter,
          halfWidth: nextHalfWidth,
          halfHeight: nextHalfHeight,
          rotation: snapshot.rotation
        })
      })

      marker.on('dragend', () => {
        alignmentDraggingHandleRef.current = null
        alignmentDragStateRef.current = null
      })

      alignmentHandlesRef.current.scale = marker
    }

    return marker
  }, [])

  const attachAnchorHandle = useCallback((anchorLngLat) => {
    const normalizedAnchor = normalizeLngLat(anchorLngLat)
    if (!map.current || !normalizedAnchor) {
      return null
    }

    let marker = alignmentHandlesRef.current.anchor
    if (!marker) {
      const element = document.createElement('div')
      element.className = 'overlay-handle overlay-handle-anchor'

      marker = new mapboxgl.Marker({ element, draggable: true })
      marker.setLngLat(normalizedAnchor)
      marker.addTo(map.current)

      marker.on('dragstart', () => {
        alignmentDraggingHandleRef.current = HANDLE_TYPES.ANCHOR
      })

      marker.on('drag', () => {
        const snapshot = alignmentStateRef.current
        if (!snapshot) {
          return
        }

        const lngLat = marker.getLngLat()
        const merc = mapboxgl.MercatorCoordinate.fromLngLat(lngLat)
        const { axisX, axisY } = getAxisVectors(snapshot)
        const nextCenter = getCenterFromAnchor(
          { x: merc.x, y: merc.y, z: merc.z ?? snapshot.center.z ?? 0 },
          axisX,
          axisY,
          alignmentAnchorRef.current,
          snapshot.center.z ?? 0
        )

        setAlignmentState((prev) => {
          if (!prev) {
            return prev
          }

          return {
            ...prev,
            center: nextCenter
          }
        })
      })

      marker.on('dragend', () => {
        alignmentDraggingHandleRef.current = null
      })

      alignmentHandlesRef.current.anchor = marker
    } else {
      marker.setLngLat(normalizedAnchor)
      if (!marker._map) {
        marker.addTo(map.current)
      }
    }
    return marker
  }, [])

  const updateAlignmentHandles = useCallback((geometry) => {
    if (!geometry) {
      return
    }

    const centerMarker = attachCenterHandle()
    if (
      centerMarker &&
      alignmentDraggingHandleRef.current !== HANDLE_TYPES.CENTER &&
      isValidLngLat(geometry.handles.center)
    ) {
      const nextCenter = normalizeLngLat(geometry.handles.center)
      if (nextCenter) {
        centerMarker.setLngLat(nextCenter)
      }
    }

    const scaleMarker = attachScaleHandle()
    if (
      scaleMarker &&
      alignmentDraggingHandleRef.current !== HANDLE_TYPES.SCALE &&
      isValidLngLat(geometry.handles.scale)
    ) {
      const nextScale = normalizeLngLat(geometry.handles.scale)
      if (nextScale) {
        scaleMarker.setLngLat(nextScale)
      }
    }

    if (alignmentAnchor !== 'center' && geometry.anchors?.[alignmentAnchor]) {
      const anchorMarker = attachAnchorHandle(geometry.anchors[alignmentAnchor])
      if (
        anchorMarker &&
        alignmentDraggingHandleRef.current !== HANDLE_TYPES.ANCHOR &&
        isValidLngLat(geometry.anchors[alignmentAnchor])
      ) {
        const nextAnchor = normalizeLngLat(geometry.anchors[alignmentAnchor])
        if (nextAnchor) {
          anchorMarker.setLngLat(nextAnchor)
        }
      }
    } else if (alignmentHandlesRef.current.anchor) {
      alignmentHandlesRef.current.anchor.remove()
      alignmentHandlesRef.current.anchor = null
    }
  }, [alignmentAnchor, attachAnchorHandle, attachCenterHandle, attachScaleHandle])

  useEffect(() => {
    alignmentStateRef.current = alignmentState

    if (!isAlignmentActive || !alignmentState) {
      return
    }

    const geometry = computeAlignmentGeometry(alignmentState)
    if (geometry) {
      ensureAlignmentLayer(geometry.coordinates)
      updateAlignmentHandles(geometry)
    }
  }, [
    alignmentState,
    computeAlignmentGeometry,
    ensureAlignmentLayer,
    isAlignmentActive,
    updateAlignmentHandles
  ])

  const activateAlignment = useCallback(() => {
    const initialOpacity = Number.isFinite(Number(overlayFormValues.opacity))
      ? clamp(Number(overlayFormValues.opacity), 0, 1)
      : 0.85
    setAlignmentPreviewOpacity(initialOpacity)

    const existingState = alignmentStateRef.current
    if (existingState) {
      setAlignmentState({
        center: { ...existingState.center },
        halfWidth: existingState.halfWidth,
        halfHeight: existingState.halfHeight,
        rotation: existingState.rotation
      })
      setAlignmentActive(true)
      setOverlayUploadStep(1)
      setOverlayUploadError('')
      return
    }

    const nextState = computeInitialAlignmentState()
    if (!nextState) {
      setOverlayUploadError('Unable to prepare alignment. Adjust the map view and try again.')
      return
    }

    setAlignmentState(nextState)
    setAlignmentActive(true)
    setOverlayUploadStep(1)
    setOverlayUploadError('')
  }, [computeInitialAlignmentState, overlayFormValues.opacity])

  const handleBeginAlignment = useCallback(() => {
    if (!overlayUploadFile) {
      setOverlayUploadError('Select an image before continuing to alignment.')
      alignmentAutoStartRef.current = false
      return
    }

    if (!overlayImageSize.width || !overlayImageSize.height) {
      setOverlayUploadError('Image dimensions not ready yet. Wait a moment and try again.')
      alignmentAutoStartRef.current = true
      return
    }

    if (!overlayPreviewImageRef.current || !overlayPreviewImageRef.current.complete) {
      setOverlayUploadError('Image preview is still loading. Wait a moment and try again.')
      alignmentAutoStartRef.current = true
      return
    }

    if (!map.current) {
      setOverlayUploadError('Map is still loading. Try again in a moment.')
      alignmentAutoStartRef.current = true
      return
    }

    if (!map.current.isStyleLoaded()) {
      setOverlayUploadError('Map is still loading. Try again in a moment.')
      alignmentAutoStartRef.current = true
      map.current.once('load', () => {
        requestAnimationFrame(() => {
          if (alignmentAutoStartRef.current) {
            alignmentAutoStartRef.current = false
            activateAlignment()
          }
        })
      })
      return
    }

    alignmentOriginalCoordinatesRef.current = null
    handleAlignmentAnchorChange('center')
    setAlignmentMode('upload')
    alignmentAutoStartRef.current = false
    activateAlignment()
  }, [
    activateAlignment,
    handleAlignmentAnchorChange,
    overlayImageSize.height,
    overlayImageSize.width,
    overlayUploadFile
  ])

  const handleBeginExistingAlignment = useCallback(() => {
    if (
      !overlayMetadata?.imageUrl ||
      !Array.isArray(overlayMetadata.coordinates) ||
      overlayMetadata.coordinates.length !== 4
    ) {
      setStatusMessage('No overlay available to adjust yet.')
      return
    }

    const mapInstance = map.current
    if (!mapInstance) {
      setStatusMessage('Map is still loading. Try again in a moment.')
      return
    }

    const beginAlignment = () => {
      clearAlignmentUI()
      setAlignmentActive(false)
      setAlignmentState(null)
      setOverlayAlignment(null)
      alignmentAutoStartRef.current = false
      setAlignmentMode('existingOverlay')
      handleAlignmentAnchorChange('topLeft')
      setOverlayUploadError('')
      setStatusMessage('')

      overlayVisibilityBeforeAlignmentRef.current = overlayEnabled
      setOverlayEnabled(false)

      alignmentOriginalCoordinatesRef.current = overlayMetadata.coordinates.map((corner) =>
        Array.isArray(corner) ? [...corner] : corner
      )

      const metadataOpacity = Number.isFinite(Number(overlayMetadata?.opacity))
        ? clamp(Number(overlayMetadata.opacity), 0, 1)
        : overlayOpacity
      setAlignmentPreviewOpacity(metadataOpacity)
      setOverlayFormValues((prev) => ({ ...prev, opacity: metadataOpacity }))

      const imageUrl = overlayMetadata.imageUrl
      overlayPreviewImageRef.current = null
      setOverlayUploadPreviewUrl(imageUrl)

      const image = new Image()
      image.onload = () => {
        overlayPreviewImageRef.current = image
        setOverlayImageSize({
          width: image.naturalWidth,
          height: image.naturalHeight
        })
        setPreviewReadySignal((prev) => prev + 1)

        const nextState = computeAlignmentStateFromCorners(overlayMetadata.coordinates)
        if (!nextState) {
          setStatusMessage('Unable to prepare alignment for the existing overlay.')
          restoreOverlayVisibility()
          setAlignmentMode('idle')
          return
        }

        setAlignmentState(nextState)
        setOverlayAlignment({
          mapCorners: overlayMetadata.coordinates.map((corner) =>
            Array.isArray(corner) ? [...corner] : corner
          )
        })
        setAlignmentActive(true)
      }
      image.onerror = () => {
        overlayPreviewImageRef.current = null
        setStatusMessage('Unable to load overlay image for editing.')
        restoreOverlayVisibility()
        setAlignmentMode('idle')
      }
      image.src = imageUrl
    }

    if (!mapInstance.isStyleLoaded()) {
      mapInstance.once('load', beginAlignment)
      return
    }

    beginAlignment()
  }, [
    clearAlignmentUI,
    computeAlignmentStateFromCorners,
    handleAlignmentAnchorChange,
    overlayEnabled,
    overlayMetadata,
    overlayOpacity,
    restoreOverlayVisibility,
    setStatusMessage
  ])

  const handleAlignmentCancel = useCallback(() => {
    clearAlignmentUI()
    setAlignmentActive(false)
    setAlignmentState(null)
    setOverlayAlignment(null)
    setAlignmentSaving(false)
    alignmentAutoStartRef.current = false
    alignmentOriginalCoordinatesRef.current = null
    handleAlignmentAnchorChange('center')

    if (alignmentMode === 'existingOverlay') {
      restoreOverlayVisibility()
      setAlignmentMode('idle')
      setOverlayUploadError('')
      return
    }

    setAlignmentMode(overlayUploadFile ? 'upload' : 'idle')
    setOverlayUploadStep((prev) => (overlayUploadFile ? 1 : 0))
    setOverlayUploadOpen(true)
  }, [
    alignmentMode,
    clearAlignmentUI,
    handleAlignmentAnchorChange,
    overlayUploadFile,
    restoreOverlayVisibility
  ])

  useEffect(() => {
    if (!alignmentAutoStartRef.current) {
      return
    }

    if (
      !overlayUploadFile ||
      !overlayImageSize.width ||
      !overlayImageSize.height ||
      !overlayPreviewImageRef.current ||
      !overlayPreviewImageRef.current.complete
    ) {
      return
    }

    if (!map.current || !map.current.isStyleLoaded()) {
      return
    }

    alignmentAutoStartRef.current = false
    activateAlignment()
  }, [activateAlignment, overlayImageSize.height, overlayImageSize.width, overlayUploadFile, previewReadySignal])

  const handleAlignmentReset = useCallback(() => {
    if (alignmentMode === 'existingOverlay') {
      const originalCorners = alignmentOriginalCoordinatesRef.current
      if (originalCorners) {
        const nextState = computeAlignmentStateFromCorners(originalCorners)
        if (nextState) {
          setAlignmentState(nextState)
        }
      }
      return
    }

    const initialState = computeInitialAlignmentState()
    if (initialState) {
      setAlignmentState(initialState)
    }
  }, [alignmentMode, computeAlignmentStateFromCorners, computeInitialAlignmentState])

  const handleAlignmentComplete = useCallback(() => {
    // Only proceed if alignment UI is active and we have a state snapshot
    if (!isAlignmentActive || !alignmentStateRef.current) {
      return
    }

    // Compute the current geometry from the latest alignment state
    const geometry = computeAlignmentGeometry(alignmentStateRef.current)
    if (!geometry || !Array.isArray(geometry.coordinates) || geometry.coordinates.length !== 4) {
      setStatusMessage('Unable to finalize alignment, try nudging the handles and click again.')
      return
    }

    // Persist the corners for upload/save
    setOverlayAlignment({ mapCorners: geometry.coordinates })

    // Tear down the alignment UI and return to the upload panel / idle state
    clearAlignmentUI()
    setAlignmentActive(false)
    setAlignmentState(null)
    setAlignmentSaving(false)

    if (alignmentMode === 'existingOverlay') {
      // When adjusting an existing overlay, keep us in idle and restore visibility
      restoreOverlayVisibility()
      setAlignmentMode('idle')
      setStatusMessage('Alignment updated. Click "Save alignment" again if needed.')
    } else {
      // When aligning a new upload, return to the upload step with overlayReady=true
      setOverlayUploadOpen(true)
      setOverlayUploadStep(2)
      setStatusMessage('Alignment set. You can now submit the overlay.')
    }
  }, [
    alignmentMode,
    clearAlignmentUI,
    computeAlignmentGeometry,
    isAlignmentActive,
    restoreOverlayVisibility
  ])

  // Keep a stable onClick target to avoid stale or undefined symbol lookups in minified bundles / HMR
  useEffect(() => {
    handleAlignmentCompleteRef.current = handleAlignmentComplete
  }, [handleAlignmentComplete])

  const loadBoreholeData = useCallback(async () => {
    try {
      const token = localStorage.getItem('token')
      const response = await axios.get('/api/geojson', {
        headers: {
          Authorization: `Bearer ${token}`
        }
      })

      const geojson = response.data

      if (geojson.features.length === 0) {
        setError('No borehole data available. The pipeline may still be processing.')
        setLoading(false)
        return
      }

      if (map.current.getSource('boreholes')) {
        map.current.getSource('boreholes').setData(geojson)
      } else {
        map.current.addSource('boreholes', {
          type: 'geojson',
          data: geojson
        })

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

        map.current.on('click', 'boreholes', (e) => {
          const feature = e.features[0]
          const description = feature.properties.description || 'No data available'

          new mapboxgl.Popup({ maxWidth: '450px', className: 'borehole-popup' })
            .setLngLat(e.lngLat)
            .setHTML(`
              <div style="padding: 12px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                <h3 style="margin: 0 0 16px 0; font-size: 1.2em; font-weight: 600;">
                  ${feature.properties.name}
                </h3>
                <div style="color: #555; font-size: 0.95em;">
                  ${description}
                </div>
              </div>
            `)
            .addTo(map.current)
        })
      }

      const bounds = geojson.features.reduce((acc, feature) => {
        return acc.extend(feature.geometry.coordinates)
      }, new mapboxgl.LngLatBounds())

      if (!bounds.isEmpty()) {
        datasetBoundsRef.current = bounds
        if (autoFitEnabledRef.current && map.current) {
          map.current.fitBounds(bounds, { padding: 50, maxZoom: 17 })
        }
      }

      setHoleCount(geojson.features.length)
      setLoading(false)
      setError('')
    } catch (err) {
      if (err.response?.status === 401) {
        onLogout()
      } else {
        setError(`Error loading data: ${err.response?.data?.error || err.message}`)
        setLoading(false)
      }
    }
  }, [onLogout])

  const loadDroneOverlay = useCallback(async () => {
    const overlayLayerId = 'drone-overlay'

    if (!map.current) {
      return
    }

    try {
      const token = localStorage.getItem('token')
      if (!token) {
        return
      }

      const response = await axios.get('/api/overlay/latest', {
        headers: {
          Authorization: `Bearer ${token}`
        }
      })

      const metadata = response.data?.overlay || response.data

      if (
        !metadata ||
        !metadata.imageUrl ||
        !Array.isArray(metadata.coordinates) ||
        metadata.coordinates.length !== 4
      ) {
        setOverlayMetadata(null)
        return
      }

      if (map.current.getLayer(overlayLayerId)) {
        map.current.removeLayer(overlayLayerId)
      }
      if (map.current.getSource(overlayLayerId)) {
        map.current.removeSource(overlayLayerId)
      }

      let overlayImageUrl = metadata.imageUrl
      if (typeof metadata.imageUrl === 'string') {
        try {
          const resolved = new URL(metadata.imageUrl, window.location.origin)
          resolved.searchParams.set('token', token)
          overlayImageUrl = resolved.toString()
        } catch (err) {
          const separator = metadata.imageUrl.includes('?') ? '&' : '?'
          overlayImageUrl = `${metadata.imageUrl}${separator}token=${encodeURIComponent(token)}`
        }
      }

      map.current.addSource(overlayLayerId, {
        type: 'image',
        url: overlayImageUrl,
        coordinates: metadata.coordinates
      })

      const requestedOpacity = Number(metadata.opacity)
      const nextOpacity = Number.isFinite(requestedOpacity)
        ? clamp(requestedOpacity, 0, 1)
        : 0.85

      const beforeLayer = map.current.getLayer('boreholes') ? 'boreholes' : undefined

      map.current.addLayer(
        {
          id: overlayLayerId,
          type: 'raster',
          source: overlayLayerId,
          paint: {
            'raster-opacity': nextOpacity,
            'raster-fade-duration': Number.isFinite(Number(metadata.fadeDuration))
              ? Number(metadata.fadeDuration)
              : 0
          }
        },
        beforeLayer
      )

      const metadataWithToken = {
        ...metadata,
        imageUrl: overlayImageUrl
      }

      setOverlayMetadata(metadataWithToken)
      setOverlayOpacity(nextOpacity)

      const visible = metadataWithToken.visible !== false
      setOverlayEnabled(visible)

      if (!visible) {
        map.current.setLayoutProperty(overlayLayerId, 'visibility', 'none')
      }
    } catch (err) {
      if (err.response?.status === 404) {
        if (map.current.getLayer(overlayLayerId)) {
          map.current.removeLayer(overlayLayerId)
        }
        if (map.current.getSource(overlayLayerId)) {
          map.current.removeSource(overlayLayerId)
        }
        setOverlayMetadata(null)
        setOverlayEnabled(false)
        setOverlayOpacity(0.85)
      } else if (err.response?.status === 401) {
        onLogout()
      } else {
        console.error('Error loading drone overlay metadata:', err)
      }
    }
  }, [onLogout])

  useEffect(() => {
    const mapboxToken = window.MAPBOX_TOKEN || ''

    if (!mapboxToken || mapboxToken.length < 30) {
      setError('Mapbox token not configured. Please set MAPBOX_TOKEN environment variable.')
      setLoading(false)
      return
    }

    // Dev-only: silence Mapbox telemetry network calls that ad blockers flag, without affecting tiles
    try {
      if (!window.__suppressMapboxEventsPatched) {
        const origFetch = window.fetch?.bind(window)
        if (origFetch) {
          window.fetch = (...args) => {
            try {
              const url = String(args[0] || '')
              if (url.includes('events.mapbox.com/events')) {
                return Promise.resolve(new Response(null, { status: 204 }))
              }
            } catch (_) {}
            return origFetch(...args)
          }
        }
        const XO = XMLHttpRequest && XMLHttpRequest.prototype && XMLHttpRequest.prototype.open
        if (XO) {
          XMLHttpRequest.prototype.open = function(method, url, ...rest) {
            try {
              if (String(url || '').includes('events.mapbox.com/events')) {
                this.send = () => {} // no-op
              }
            } catch (_) {}
            return XO.call(this, method, url, ...rest)
          }
        }
        // Also silence sendBeacon which Mapbox uses for telemetry
        const origBeacon = typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function'
          ? navigator.sendBeacon.bind(navigator)
          : null
        if (origBeacon) {
          navigator.sendBeacon = (url, data) => {
            try {
              if (String(url || '').includes('events.mapbox.com/events')) {
                return true // pretend success, avoid console noise
              }
            } catch {}
            return origBeacon(url, data)
          }
        }
        window.__suppressMapboxEventsPatched = true
      }
    } catch (_) {}

    mapboxgl.accessToken = mapboxToken
    try { mapboxgl.setTelemetryEnabled(false) } catch (_) {}
    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/satellite-streets-v12',
      center: [-96.432978, 32.484672],
      zoom: 15
    })

    map.current.on('load', () => {
      loadBoreholeData()
      loadDroneOverlay()
    })

    return () => {
      if (map.current) {
        map.current.remove()
      }
    }
  }, [loadBoreholeData, loadDroneOverlay])

  useEffect(() => {
    const overlayLayerId = 'drone-overlay'
    const mapInstance = map.current

    if (!mapInstance || !mapInstance.style) {
      return
    }

    if (!mapInstance.getLayer(overlayLayerId)) {
      return
    }

    mapInstance.setLayoutProperty(
      overlayLayerId,
      'visibility',
      overlayEnabled ? 'visible' : 'none'
    )
  }, [overlayEnabled])

  useEffect(() => {
    const overlayLayerId = 'drone-overlay'
    const mapInstance = map.current

    if (!mapInstance || !mapInstance.style) {
      return
    }

    if (!mapInstance.getLayer(overlayLayerId)) {
      return
    }

    mapInstance.setPaintProperty(overlayLayerId, 'raster-opacity', overlayOpacity)
  }, [overlayOpacity])

  const handleOverlayToggle = useCallback((event) => {
    setOverlayEnabled(event.target.checked)
  }, [])

  const handleOverlayOpacityChange = useCallback((event) => {
    const nextOpacity = Number(event.target.value)
    setOverlayOpacity(nextOpacity)
  }, [])

  const fetchPipelineStatus = useCallback(async () => {
    try {
      const token = localStorage.getItem('token')
      if (!token) return

      const response = await axios.get('/api/status', {
        headers: {
          Authorization: `Bearer ${token}`
        }
      })

      setPipelineStatus(response.data)
      if (response.data?.pipeline?.state === 'running') {
        setStatusMessage((prev) => prev || 'Pipeline run in progress...')
      }
    } catch (err) {
      if (err.response?.status === 401) {
        onLogout()
        return
      }

      console.error('Failed to fetch pipeline status', err)
      setStatusMessage((prev) => prev || err.response?.data?.error || err.message)
    }
  }, [onLogout])

  useEffect(() => {
    fetchPipelineStatus()
    const interval = setInterval(fetchPipelineStatus, 10000)
    return () => clearInterval(interval)
  }, [fetchPipelineStatus])

  useEffect(() => {
    if (!refreshAfterManual || !pipelineStatus) {
      return
    }

    const state = pipelineStatus.pipeline?.state
    if (state === 'running') {
      return
    }

    setRefreshAfterManual(false)

    if (pipelineStatus.pipeline?.last_run_status === 'success') {
      setStatusMessage('Pipeline run completed successfully.')
      loadBoreholeData()
    } else if (pipelineStatus.pipeline?.last_run_status === 'error') {
      setStatusMessage(
        pipelineStatus.pipeline?.message || 'Pipeline run completed with errors.'
      )
    } else {
      setStatusMessage('Pipeline run finished.')
    }
  }, [pipelineStatus, refreshAfterManual, loadBoreholeData])

  const handleTriggerPipeline = useCallback(async () => {
    try {
      setTriggeringRun(true)
      setStatusMessage('')

      const token = localStorage.getItem('token')
      if (!token) {
        setStatusMessage('Authentication required to trigger the pipeline.')
        return
      }

      const response = await axios.post(
        '/api/pipeline/run',
        {},
        {
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      )

      const trigger = response.data?.trigger
      setStatusMessage('Pipeline run queued. This may take a few minutes to finish.')
      setRefreshAfterManual(true)

      if (trigger) {
        setPipelineStatus((prev) => ({
          ...(prev || {}),
          pipeline: {
            ...(prev?.pipeline || {}),
            pending_trigger: trigger
          }
        }))
      }

      fetchPipelineStatus()
    } catch (err) {
      if (err.response?.status === 401) {
        onLogout()
        return
      }

      const message =
        err.response?.data?.message ||
        err.response?.data?.error ||
        err.message ||
        'Failed to trigger pipeline run.'

      setStatusMessage(message)
    } finally {
      setTriggeringRun(false)
    }
  }, [fetchPipelineStatus, onLogout])

  const handleToggleAutoFit = useCallback(() => {
    setAutoFitEnabled((prev) => {
      const next = !prev
      autoFitEnabledRef.current = next
      if (next && datasetBoundsRef.current && map.current) {
        map.current.fitBounds(datasetBoundsRef.current, { padding: 50, maxZoom: 17 })
      }
      return next
    })
  }, [])

  const handleFitToData = useCallback(() => {
    if (datasetBoundsRef.current && map.current) {
      map.current.fitBounds(datasetBoundsRef.current, { padding: 50, maxZoom: 17 })
    }
  }, [])

  const handleAlignmentCleanup = useCallback(() => {
    clearAlignmentUI()
    setAlignmentActive(false)
    setAlignmentState(null)
    setOverlayAlignment(null)
    setAlignmentMode('idle')
    setAlignmentSaving(false)
    alignmentAutoStartRef.current = false
    alignmentOriginalCoordinatesRef.current = null
    handleAlignmentAnchorChange('center')
    restoreOverlayVisibility()
  }, [clearAlignmentUI, handleAlignmentAnchorChange, restoreOverlayVisibility])

  const handleOverlaySubmit = useCallback(async () => {
    if (!overlayUploadFile) {
      setOverlayUploadError('Select an image before uploading.')
      return
    }

    if (!imageCorners) {
      setOverlayUploadError('Unable to read image dimensions. Re-select the file and try again.')
      return
    }

    if (!overlayAlignment?.mapCorners || overlayAlignment.mapCorners.length !== 4) {
      setOverlayUploadError('Drag the overlay until it is positioned correctly before uploading.')
      return
    }

    try {
      setOverlayUploading(true)
      setOverlayUploadError('')

      const token = localStorage.getItem('token')
      if (!token) {
        setOverlayUploadError('Authentication required. Please sign in again.')
        onLogout()
        return
      }

      const formData = new FormData()
      formData.append('image', overlayUploadFile)
      formData.append('name', overlayFormValues.name.trim())
      if (overlayFormValues.captureDate) {
        formData.append('captureDate', overlayFormValues.captureDate)
      }
      formData.append('opacity', String(overlayFormValues.opacity))
      formData.append('visible', overlayFormValues.visible ? 'true' : 'false')
      formData.append('imageCorners', JSON.stringify(imageCorners))
      formData.append('mapCorners', JSON.stringify(overlayAlignment.mapCorners))

      const response = await axios.post('/api/overlay', formData, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      })

      const successMessage =
        response.data?.message ||
        'Overlay upload queued. Refresh in a moment to see the new imagery.'
      setStatusMessage(successMessage)

      await loadDroneOverlay()
      resetOverlayUploadState()
      setOverlayUploadOpen(false)
    } catch (err) {
      if (err.response?.status === 401) {
        onLogout()
      } else {
        setOverlayUploadError(err.response?.data?.error || err.message || 'Failed to upload overlay.')
      }
    } finally {
      setOverlayUploading(false)
    }
  }, [
    imageCorners,
    loadDroneOverlay,
    onLogout,
    overlayAlignment,
    overlayFormValues,
    overlayUploadFile,
    resetOverlayUploadState
  ])

  useEffect(() => {
    return () => {
      handleAlignmentCleanup()
      if (overlayObjectUrlRef.current) {
        URL.revokeObjectURL(overlayObjectUrlRef.current)
      }
    }
  }, [handleAlignmentCleanup])

  const pipelineState = pipelineStatus?.pipeline || {}
  const pipelineRunning = pipelineState.state === 'running'
  const lastRunFinishedAt = pipelineState.last_run_completed || pipelineState.last_run_started

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
          <div className="status-item">
            ⚙️ <strong>Pipeline:</strong>
            <div className="status-details">
              <span className={`status-badge ${pipelineRunning ? 'running' : 'idle'}`}>
                {pipelineRunning ? 'Running…' : 'Idle'}
              </span>
              <div className="status-subtext">
                Last run: {formatTimestamp(lastRunFinishedAt)}
              </div>
              {pipelineState.message && (
                <div className="status-subtext">{pipelineState.message}</div>
              )}
              {pipelineState.pending_trigger?.requested_at && (
                <div className="status-subtext">
                  Queued by {pipelineState.pending_trigger.requested_by || 'user'} at{' '}
                  {formatTimestamp(pipelineState.pending_trigger.requested_at)}
                </div>
              )}
            </div>
          </div>
          {overlayMetadata && (
            <div className="overlay-controls">
              <div className="overlay-title">
                <span>🛰️ <strong>Drone Overlay</strong></span>
                {overlayMetadata.captureDate && (
                  <span className="overlay-date">
                    {formatOverlayDate(overlayMetadata.captureDate)}
                  </span>
                )}
              </div>
              {overlayMetadata.name && (
                <div className="overlay-name">{overlayMetadata.name}</div>
              )}
              <label className="overlay-toggle">
                <span>Visibility</span>
                <div className="overlay-toggle-control">
                  <input
                    type="checkbox"
                    checked={overlayEnabled}
                    onChange={handleOverlayToggle}
                  />
                  <span className="overlay-toggle-label">
                    {overlayEnabled ? 'On' : 'Off'}
                  </span>
                </div>
              </label>
              <label className="overlay-opacity">
                <span>Opacity: {Math.round(overlayOpacity * 100)}%</span>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={overlayOpacity}
                  onChange={handleOverlayOpacityChange}
                />
              </label>
              {overlayMetadata.coordinates && (
                <details className="overlay-coordinates">
                  <summary>Boundary Coordinates</summary>
                  <ol>
                    {overlayMetadata.coordinates.map((coord, index) => (
                      <li key={`${coord[0]}-${coord[1]}-${index}`}>
                        [{coord[0]}, {coord[1]}]
                      </li>
                    ))}
                  </ol>
                </details>
              )}
              <button
                type="button"
                className="overlay-upload-link-button"
                onClick={handleBeginExistingAlignment}
                disabled={isAlignmentActive || alignmentSaving}
              >
                {alignmentSaving && alignmentMode === 'existingOverlay' ? 'Saving…' : 'Adjust alignment'}
              </button>
            </div>
          )}
        </div>
        {loading && <div className="loading">Loading map...</div>}
        {error && <div className="error">{error}</div>}
        <OverlayUploadPanel
          isOpen={isOverlayUploadOpen}
          file={overlayUploadFile}
          onOpen={handleOpenOverlayUpload}
          onClose={handleCloseOverlayUpload}
          onFileSelected={handleOverlayFileSelected}
          imagePreviewUrl={overlayUploadPreviewUrl}
          overlayReady={overlayReady}
          onBeginAlignment={handleBeginAlignment}
          formValues={overlayFormValues}
          onFormValueChange={handleOverlayFormValueChange}
          onSubmit={handleOverlaySubmit}
          uploading={overlayUploading}
          uploadError={overlayUploadError}
          onRemovePreview={handleOverlayRemovePreview}
          alignmentActive={isAlignmentActive}
        />
        <button
          onClick={handleTriggerPipeline}
          className="pipeline-button"
          disabled={pipelineRunning || triggeringRun}
        >
          {pipelineRunning || triggeringRun ? 'Pipeline Running…' : 'Run Pipeline Now'}
        </button>
        <div className="fit-controls">
          <button
            type="button"
            className="fit-button"
            onClick={handleFitToData}
            disabled={!datasetBoundsRef.current}
          >
            Fit view to data
          </button>
          <label className="fit-toggle">
            <input
              type="checkbox"
              checked={autoFitEnabled}
              onChange={handleToggleAutoFit}
            />
            Auto-fit when data refreshes
          </label>
        </div>
        {statusMessage && <div className="status-note">{statusMessage}</div>}
        <button onClick={onLogout} className="logout-button">
          Logout
        </button>
      </div>
      <div ref={mapContainer} className="map" />
      {isAlignmentActive && alignmentState && (
        <div className="overlay-alignment-hud">
          <div className="overlay-alignment-header">
            <h3>Overlay Alignment</h3>
            <button
              type="button"
              className="overlay-upload-link-button"
              onClick={handleAlignmentCancel}
              disabled={alignmentSaving}
            >
              Cancel
            </button>
          </div>
          <p>Drag the center handle to move the overlay and the corner handle to scale. Choose an anchor to keep a corner fixed while scaling, and adjust the rotation below if needed.</p>
          <label className="overlay-upload-field">
            <span>Rotation ({Math.round(alignmentRotationDegrees)}°)</span>
            <input
              type="range"
              min="-180"
              max="180"
              step="1"
              value={alignmentRotationDegrees}
              onChange={(event) => handleAlignmentRotationChange(event.target.value)}
              disabled={alignmentSaving}
            />
          </label>
          <label className="overlay-upload-field overlay-alignment-opacity">
            <span>Preview Opacity ({Math.round(alignmentPreviewOpacity * 100)}%)</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={alignmentPreviewOpacity}
              onChange={(event) => handleAlignmentPreviewOpacityChange(event.target.value)}
              disabled={alignmentSaving}
            />
          </label>
          <div className="overlay-alignment-anchor">
            <span>Anchor</span>
            <div className="overlay-alignment-anchor-buttons">
              {alignmentAnchorOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`overlay-align-anchor-button ${alignmentAnchor === option.value ? 'active' : ''}`}
                  onClick={() => handleAlignmentAnchorChange(option.value)}
                  disabled={alignmentSaving}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <div className="overlay-alignment-actions">
            <button type="button" className="overlay-upload-link-button" onClick={handleAlignmentReset}>
              Reset
            </button>
            <button
              type="button"
              className="overlay-upload-primary"
              onClick={() => handleAlignmentCompleteRef.current && handleAlignmentCompleteRef.current()}
              disabled={alignmentSaving}
            >
              {alignmentMode === 'existingOverlay'
                ? alignmentSaving
                  ? 'Saving…'
                  : 'Save alignment'
                : 'Done aligning'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default Map
