import React, { useMemo } from 'react'

function OverlayUploadPanel({
  isOpen,
  file,
  onOpen,
  onClose,
  onFileSelected,
  imagePreviewUrl,
  overlayReady,
  onBeginAlignment,
  formValues,
  onFormValueChange,
  onSubmit,
  uploading,
  uploadError,
  onRemovePreview,
  alignmentActive,
}) {
  const steps = useMemo(
    () => [
      { title: 'Select Image', description: 'Choose the orthomosaic image exported from your drone processing software.' },
      { title: 'Align on Map', description: 'Use the on-map handles to move, scale, and rotate the overlay until it lines up.' },
      { title: 'Review & Submit', description: 'Confirm metadata and upload the aligned image.' },
    ],
    []
  )

  if (!isOpen) {
    return (
      <button className="overlay-upload-toggle" onClick={onOpen}>
        ➕ Upload New Drone Overlay
      </button>
    )
  }

  const currentStep = !file
    ? 0
    : overlayReady
      ? 2
      : 1

  return (
    <div className="overlay-upload-panel">
      <div className="overlay-upload-header">
        <div>
          <h3>Upload Drone Overlay</h3>
          <p>{steps[currentStep]?.description || ''}</p>
        </div>
        <button type="button" className="overlay-upload-close" onClick={onClose}>
          ✕
        </button>
      </div>

      <div className="overlay-upload-progress">
        {steps.map((item, index) => (
          <div
            key={item.title}
            className={`overlay-upload-progress-step ${
              index === currentStep ? 'active' : index < currentStep ? 'complete' : ''
            }`}
          >
            <span className="number">{index + 1}</span>
            <span className="label">{item.title}</span>
          </div>
        ))}
      </div>

      {uploadError && <div className="overlay-upload-error">{uploadError}</div>}

      {currentStep === 0 && (
        <div className="overlay-upload-step">
          <p>Select a PNG, JPEG, or WebP file (≤ 200 MB).</p>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={onFileSelected}
          />
          {file && (
            <div className="overlay-upload-file-preview">
              <div>
                <strong>Selected:</strong> {file.name}
              </div>
              <button type="button" onClick={onRemovePreview} className="overlay-upload-link-button">
                Remove image
              </button>
            </div>
          )}
        </div>
      )}

      {currentStep === 1 && (
        <div className="overlay-upload-step">
          <p>The image is displayed on the map. Drag the center handle to move it and the corner handle to scale. Use the on-map rotation slider if needed.</p>
          <p>
            {alignmentActive
              ? 'Alignment mode is active. Adjust the overlay on the map and click “Done aligning” in the map panel when finished.'
              : 'Click “Open Alignment Mode” below to start adjusting the overlay.'}
          </p>
        </div>
      )}

      {currentStep === 2 && (
        <div className="overlay-upload-step">
          <label className="overlay-upload-field">
            <span>Overlay name</span>
            <input
              type="text"
              value={formValues.name}
              onChange={(event) => onFormValueChange('name', event.target.value)}
            />
          </label>
          <label className="overlay-upload-field">
            <span>Capture date</span>
            <input
              type="datetime-local"
              value={formValues.captureDate}
              onChange={(event) => onFormValueChange('captureDate', event.target.value)}
            />
          </label>
          <label className="overlay-upload-field">
            <span>Default opacity ({Math.round(formValues.opacity * 100)}%)</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={formValues.opacity}
              onChange={(event) => onFormValueChange('opacity', Number(event.target.value))}
            />
          </label>
          <label className="overlay-upload-checkbox">
            <input
              type="checkbox"
              checked={formValues.visible}
              onChange={(event) => onFormValueChange('visible', event.target.checked)}
            />
            Start visible after upload
          </label>
          <div className="overlay-upload-summary">
            <h4>Summary</h4>
            <div>
              <strong>Image:</strong> {file?.name || 'n/a'}
            </div>
          </div>
          <button
            type="button"
            className="overlay-upload-link-button"
            onClick={onBeginAlignment}
            disabled={uploading}
          >
            Adjust alignment
          </button>
        </div>
      )}

      <div className="overlay-upload-footer">
        <button
          type="button"
          className="overlay-upload-link-button"
          onClick={onClose}
        >
          Cancel
        </button>

        {currentStep === 2 ? (
          <button
            type="button"
            className="overlay-upload-primary"
            onClick={onSubmit}
            disabled={uploading || !formValues.name.trim() || !overlayReady}
          >
            {uploading ? 'Uploading…' : 'Upload Overlay'}
          </button>
        ) : currentStep === 1 ? (
          <button
            type="button"
            className="overlay-upload-primary"
            onClick={!alignmentActive ? onBeginAlignment : undefined}
            disabled={!imagePreviewUrl || alignmentActive}
          >
            {alignmentActive ? 'Alignment in progress' : 'Open Alignment Mode'}
          </button>
        ) : (
          <button
            type="button"
            className="overlay-upload-primary"
            onClick={onBeginAlignment}
            disabled={!file || !imagePreviewUrl}
          >
            Continue to alignment
          </button>
        )}
      </div>
    </div>
  )
}

export default OverlayUploadPanel
