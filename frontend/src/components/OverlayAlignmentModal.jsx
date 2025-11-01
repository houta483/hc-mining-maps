import React from 'react'

const OverlayAlignmentModal = ({
  isOpen,
  imageName,
  onCancel,
  onReset,
  onSubmit,
  uploading,
  error,
  formValues,
  onFormValueChange,
  rotationDegrees,
  onRotationChange,
  canSubmit,
  mapCorners,
  imageCorners
}) => {
  if (!isOpen) {
    return null
  }

  const handleNameChange = (event) => {
    onFormValueChange('name', event.target.value)
  }

  const handleDateChange = (event) => {
    onFormValueChange('captureDate', event.target.value)
  }

  const handleOpacityChange = (event) => {
    onFormValueChange('opacity', Number(event.target.value))
  }

  const handleVisibleChange = (event) => {
    onFormValueChange('visible', event.target.checked)
  }

  const handleRotationChange = (event) => {
    onRotationChange(event.target.value)
  }

  return (
    <div className="overlay-alignment-modal" role="dialog" aria-modal="true">
      <div className="overlay-alignment-content">
        <header className="overlay-alignment-header">
          <div>
            <h3>Align Overlay on Map</h3>
            <p>Drag the on-map handles to position the image. Adjust rotation and metadata below.</p>
          </div>
          <button type="button" className="overlay-alignment-close" onClick={onCancel}>
            ✕
          </button>
        </header>

        {error && <div className="overlay-upload-error">{error}</div>}

        <section className="overlay-alignment-section">
          <h4>Alignment Tips</h4>
          <ul>
            <li>Drag the white circle to move the overlay.</li>
            <li>Drag the corner handle to resize while keeping the image rectangular.</li>
            <li>Use the rotation slider for fine adjustments.</li>
          </ul>
        </section>

        <section className="overlay-alignment-section">
          <label className="overlay-alignment-field">
            <span>Rotation ({Math.round(rotationDegrees)}°)</span>
            <input
              type="range"
              min="-180"
              max="180"
              step="1"
              value={rotationDegrees}
              onChange={handleRotationChange}
            />
          </label>
          <label className="overlay-alignment-field">
            <span>Default opacity ({Math.round(formValues.opacity * 100)}%)</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={formValues.opacity}
              onChange={handleOpacityChange}
            />
          </label>
          <label className="overlay-alignment-field">
            <span>Overlay name</span>
            <input type="text" value={formValues.name} onChange={handleNameChange} />
          </label>
          <label className="overlay-alignment-field">
            <span>Capture date</span>
            <input type="datetime-local" value={formValues.captureDate} onChange={handleDateChange} />
          </label>
          <label className="overlay-alignment-checkbox">
            <input type="checkbox" checked={formValues.visible} onChange={handleVisibleChange} />
            Start visible after upload
          </label>
        </section>

        <section className="overlay-alignment-section">
          <h4>Summary</h4>
          <div className="overlay-alignment-summary">
            <div><strong>Image:</strong> {imageName || 'Unnamed overlay'}</div>
            <div><strong>Image corners:</strong> {imageCorners ? imageCorners.length : 0}</div>
            <div><strong>Map corners captured:</strong> {mapCorners ? mapCorners.length : 0}</div>
          </div>
        </section>

        <footer className="overlay-alignment-footer">
          <button type="button" onClick={onCancel} className="overlay-upload-link-button">
            Cancel
          </button>
          <button type="button" onClick={onReset} className="overlay-upload-link-button">
            Reset alignment
          </button>
          <button
            type="button"
            onClick={onSubmit}
            className="overlay-upload-primary"
            disabled={uploading || !canSubmit || !formValues.name.trim()}
          >
            {uploading ? 'Uploading…' : 'Upload overlay'}
          </button>
        </footer>
      </div>
    </div>
  )
}

export default OverlayAlignmentModal
