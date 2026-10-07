import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

export default function UploadPage() {
  const [dragging, setDragging] = useState(false)
  const [file, setFile]         = useState(null)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress]  = useState('')
  const [error, setError]        = useState(null)
  const inputRef = useRef(null)
  const navigate = useNavigate()

  const accepted = ['text/csv', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']

  const validate = (f) => {
    if (!f) return 'No file selected'
    const ext = f.name.split('.').pop().toLowerCase()
    if (!['csv', 'xlsx'].includes(ext)) return 'Only CSV and XLSX files are supported'
    if (f.size > 50 * 1024 * 1024) return 'File exceeds 50 MB limit'
    return null
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    const err = validate(f)
    if (err) { setError(err); return }
    setFile(f); setError(null)
  }

  const handleSelect = (e) => {
    const f = e.target.files[0]
    const err = validate(f)
    if (err) { setError(err); return }
    setFile(f); setError(null)
  }

  const handleUpload = async () => {
    if (!file) return
    setUploading(true); setError(null)
    try {
      setProgress('Uploading…')
      const dataset = await api.uploadDataset(file)

      setProgress('Profiling dataset…')
      await api.runProfile(dataset.id)

      setProgress('Analysing quality…')
      await api.runQuality(dataset.id)

      setProgress('Done!')
      navigate(`/datasets/${dataset.id}`)
    } catch (e) {
      setError(e.message)
      setUploading(false)
      setProgress('')
    }
  }

  return (
    <div style={{ maxWidth: 600 }}>
      <div className="page-header">
        <div>
          <h1>Upload Dataset</h1>
          <div className="sub">CSV or XLSX — up to 50 MB</div>
        </div>
      </div>

      {/* Drop zone */}
      <div
        className={`upload-zone ${dragging ? 'drag-over' : ''}`}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <div className="upload-icon">⊞</div>
        {file ? (
          <>
            <div className="upload-title" style={{ color: 'var(--blue-light)' }}>{file.name}</div>
            <div className="upload-sub">{fmtBytes(file.size)} — ready to upload</div>
          </>
        ) : (
          <>
            <div className="upload-title">Drag & drop your file here</div>
            <div className="upload-sub">or click to browse — CSV, XLSX supported</div>
          </>
        )}
        <input ref={inputRef} type="file" accept=".csv,.xlsx" hidden onChange={handleSelect} />
      </div>

      {error && <div className="alert alert-error mt-sm">{error}</div>}

      {file && !uploading && (
        <div style={{ marginTop: '1rem', display: 'flex', gap: '.75rem', alignItems: 'center' }}>
          <button className="btn btn-primary" onClick={handleUpload}>
            ↑ Upload & Profile
          </button>
          <button className="btn btn-ghost" onClick={() => { setFile(null); setError(null) }}>
            Clear
          </button>
        </div>
      )}

      {uploading && (
        <div className="loading-row mt-sm">
          <div className="spinner" />
          {progress}
        </div>
      )}

      {/* Supported formats */}
      <div className="card mt-lg">
        <div className="card-header"><span className="card-title">Supported Formats</span></div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          {[
            { type: 'CSV', ext: '.csv', desc: 'Comma-separated values. UTF-8 encoding recommended.' },
            { type: 'XLSX', ext: '.xlsx', desc: 'Excel Workbook. First sheet is used.' },
          ].map(f => (
            <div key={f.type} style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '.85rem' }}>
              <div style={{ display: 'flex', gap: '.5rem', alignItems: 'center', marginBottom: '.3rem' }}>
                <span className="badge badge-blue">{f.type}</span>
                <span style={{ fontSize: '.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{f.ext}</span>
              </div>
              <div style={{ fontSize: '.775rem', color: 'var(--text-muted)' }}>{f.desc}</div>
            </div>
          ))}
        </div>
        <div className="divider" />
        <div style={{ fontSize: '.775rem', color: 'var(--text-muted)' }}>
          After upload, the system will automatically run data profiling and quality analysis.
          A full workflow (AI recommendations, pipeline, validation) can be triggered from the dataset page.
        </div>
      </div>
    </div>
  )
}

function fmtBytes(n) {
  if (!n) return ''
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1048576).toFixed(1)} MB`
}
