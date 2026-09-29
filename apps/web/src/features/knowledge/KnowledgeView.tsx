import { useMemo, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, ArrowRight, BookOpenText, Check, Clock3, FileText, LoaderCircle, RefreshCcw, Search, Trash2, UploadCloud } from 'lucide-react'
import { api, type Document, type Session } from '../../lib/api'
import { relativeTime, shortDate, titleCase } from '../../lib/format'
import { EmptyState, LoadingState, PageHeading, QueryBlock, StatusPill } from '../../components/ui'

const ACCEPTED = '.pdf,.md,.markdown,.csv,text/markdown,text/csv,application/pdf'
const ACTIVE_STATES = new Set(['pending', 'queued', 'processing', 'extracting', 'indexing', 'running'])
const CANCELLABLE_STATES = new Set(['pending', 'running'])

export function KnowledgeView({ session }: { session: Session }) {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [category, setCategory] = useState('general')
  const [authority, setAuthority] = useState('uploaded')
  const [dragged, setDragged] = useState(false)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [actionId, setActionId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [cancelJobId, setCancelJobId] = useState<string | null>(null)
  const [cancelJobError, setCancelJobError] = useState<string | null>(null)
  const canManage = session.user.role === 'admin'
  const docs = useQuery({ queryKey: ['documents'], queryFn: api.documents, refetchInterval: (query) => query.state.data?.jobs?.some((job) => ACTIVE_STATES.has(job.status.toLowerCase())) ? 2500 : 20_000 })
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['documents'] })
  const upload = useMutation({ mutationFn: (selected: File) => api.uploadDocument(selected, category, authority), onSuccess: () => { setFile(null); if (inputRef.current) inputRef.current.value = ''; refresh() } })
  const publish = useMutation({ mutationFn: (id: string) => api.publishDocument(id), onMutate: (id) => { setActionId(id); setActionError(null) }, onSuccess: refresh, onError: (error) => setActionError(error.message) })
  const remove = useMutation({ mutationFn: (id: string) => api.deleteDocument(id), onMutate: (id) => { setActionId(id); setActionError(null) }, onSuccess: refresh, onError: (error) => setActionError(error.message) })
  const retry = useMutation({ mutationFn: (id: string) => api.retryDocument(id), onMutate: (id) => { setActionId(id); setActionError(null) }, onSuccess: refresh, onError: (error) => setActionError(error.message) })
  const cancelJob = useMutation({ mutationFn: (id: string) => api.cancelIngestionJob(id), onMutate: (id) => { setCancelJobId(id); setCancelJobError(null) }, onSuccess: refresh, onError: (error) => { setCancelJobError(error.message); refresh() } })
  const replace = useMutation({ mutationFn: ({ id, selected }: { id: string; selected: File }) => api.replaceDocument(id, selected), onMutate: ({ id }) => { setActionId(id); setActionError(null) }, onSuccess: refresh, onError: (error) => setActionError(error.message) })

  const allDocs = docs.data?.items || []
  const visible = useMemo(() => allDocs.filter((doc) => {
    const term = search.toLowerCase().trim()
    return (filter === 'all' || doc.status.toLowerCase() === filter) && (!term || [doc.title, doc.kind, doc.id].some((value) => value?.toLowerCase().includes(term)))
  }), [allDocs, filter, search])
  const published = allDocs.filter((doc) => doc.status.toLowerCase() === 'published').length
  const failed = allDocs.filter((doc) => doc.status.toLowerCase() === 'failed').length
  const runningJobs = docs.data?.jobs?.filter((job) => ACTIVE_STATES.has(job.status.toLowerCase())) || []
  const displayedJobs = [...runningJobs, ...(docs.data?.jobs || []).filter((job) => !ACTIVE_STATES.has(job.status.toLowerCase()))].slice(0, 6)
  const chooseFile = (selected?: File) => {
    if (!selected) return
    const ext = selected.name.split('.').pop()?.toLowerCase()
    if (!ext || !['pdf', 'md', 'markdown', 'csv'].includes(ext)) { setFile(null); setActionError('Choose a PDF, Markdown, or CSV file.'); return }
    setActionError(null)
    setFile(selected)
  }
  const replaceFile = (id: string, event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0]
    if (!selected) return
    if (window.confirm(`Replace the current version with ${selected.name}? The new version must be published before retrieval uses it.`)) replace.mutate({ id, selected })
    event.target.value = ''
  }

  return <div className="content-page knowledge-page"><PageHeading eyebrow="KNOWLEDGE BASE" title="Knowledge that holds up." description="Keep the published source of truth current, traceable, and ready for grounded answers." action={<div className="page-stats"><span><strong>{published}</strong> published</span><span className={failed ? 'stat-warning' : ''}><strong>{failed}</strong> need attention</span></div>} />
    <div className="knowledge-grid"><section className="knowledge-main"><div className="section-heading"><div><p className="eyebrow">DOCUMENT LIBRARY</p><h2>Source documents</h2></div><span className="section-count">{allDocs.length} total</span></div><div className="knowledge-filters"><label className="search-field"><Search size={16} /><span className="sr-only">Search documents</span><input placeholder="Search documents" value={search} onChange={(event) => setSearch(event.target.value)} /></label><label className="select-filter"><span className="sr-only">Filter by status</span><select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="all">All statuses</option><option value="published">Published</option><option value="draft">Draft</option><option value="failed">Failed</option><option value="processing">Processing</option></select></label><button className="icon-button refresh-button" type="button" onClick={() => void docs.refetch()} title="Refresh documents" aria-label="Refresh documents"><RefreshCcw size={17} /></button></div><QueryBlock title="Could not load documents" error={docs.error} retry={() => void docs.refetch()}>{docs.isPending ? <LoadingState label="Loading knowledge library…" /> : visible.length === 0 ? <EmptyState icon={<BookOpenText size={21} />} title={search || filter !== 'all' ? 'No documents match' : 'No documents yet'} description={search || filter !== 'all' ? 'Try another search or status filter.' : 'Upload a manual, policy, FAQ, or product CSV to begin.'} /> : <div className="document-list">{visible.map((doc) => <DocumentRow key={doc.id} doc={doc} canManage={canManage} busy={actionId === doc.id && (publish.isPending || remove.isPending || retry.isPending || replace.isPending)} error={actionId === doc.id ? actionError : null} onPublish={() => publish.mutate(doc.id)} onRetry={() => retry.mutate(doc.id)} onDelete={() => { if (window.confirm(`Delete ${doc.title} and remove its retrieval passages?`)) remove.mutate(doc.id) }} onReplace={(event) => replaceFile(doc.id, event)} />)}</div>}</QueryBlock></section>
      <aside className="knowledge-side"><section className="upload-panel"><span className="upload-panel-icon"><UploadCloud size={22} /></span><p className="eyebrow">ADD TO THE LIBRARY</p><h2>Upload a source</h2><p>Manuals, policy PDFs, Markdown FAQs, and product CSVs are validated and indexed before publishing.</p><div className={`dropzone${dragged ? ' drag-over' : ''}${!canManage ? ' disabled' : ''}`} onDragOver={(event: DragEvent<HTMLDivElement>) => { event.preventDefault(); if (canManage) setDragged(true) }} onDragLeave={() => setDragged(false)} onDrop={(event: DragEvent<HTMLDivElement>) => { event.preventDefault(); setDragged(false); if (canManage) chooseFile(event.dataTransfer.files[0]) }}><UploadCloud size={24} /><strong>{file?.name || 'Drop a file here'}</strong><small>{file ? `${(file.size / 1024).toFixed(1)} KB selected` : 'PDF, Markdown, or CSV'}</small><input ref={inputRef} id="knowledge-file" type="file" accept={ACCEPTED} onChange={(event) => chooseFile(event.target.files?.[0])} disabled={!canManage} /><label className="btn btn-secondary" htmlFor="knowledge-file">Browse files</label></div><div className="upload-classification"><label>Category<select value={category} onChange={(event) => setCategory(event.target.value)} disabled={!canManage || upload.isPending}><option value="general">General</option><option value="returns">Returns</option><option value="shipping">Shipping</option><option value="warranty">Warranty</option><option value="product_specs">Product specs</option></select></label><label>Authority<select value={authority} onChange={(event) => setAuthority(event.target.value)} disabled={!canManage || upload.isPending}><option value="uploaded">Uploaded</option><option value="official_policy">Official policy</option><option value="product_manual">Product manual</option><option value="faq">FAQ</option><option value="support_guide">Support guide</option></select></label></div>{!canManage && <p className="permission-note"><AlertCircle size={14} /> Admin access is required to change knowledge.</p>}{file && <div className="selected-upload"><span><FileText size={16} />{file.name}</span><button className="btn btn-primary" type="button" disabled={upload.isPending} onClick={() => upload.mutate(file)}>{upload.isPending ? <><LoaderCircle size={16} className="spin" /> Uploading…</> : <>Upload & index <ArrowRight size={15} /></>}</button></div>}{upload.isError && <p className="inline-error" role="alert">{upload.error.message}</p>}{upload.isSuccess && <p className="inline-success" role="status"><Check size={15} /> File accepted. Track indexing below.</p>}</section><section className="ingestion-panel"><div className="section-heading compact"><div><p className="eyebrow">INGESTION</p><h2>Processing activity</h2></div><Clock3 size={17} /></div>{!docs.data?.jobs?.length ? <p className="side-muted">No recent ingestion jobs were returned by the service.</p> : <div className="job-list">{displayedJobs.map((job) => <div className="job-row" key={job.id}><span className={`job-indicator job-${job.status.toLowerCase()}`} /> <div><strong>{job.document_id || `Job ${job.id}`}</strong><small>{titleCase(job.status)}{job.progress != null ? ` · ${Math.round(job.progress * (job.progress <= 1 ? 100 : 1))}%` : ''}</small>{job.status.toLowerCase() !== 'cancelled' && (job.error || job.failure_reason) && <p role='alert'>{job.error || job.failure_reason}</p>}{canManage && CANCELLABLE_STATES.has(job.status.toLowerCase()) && !job.cancel_requested && <button className="text-action job-cancel" type="button" disabled={cancelJob.isPending} onClick={() => cancelJob.mutate(job.id)} aria-label={`Cancel ingestion job ${job.id}`}>{cancelJob.isPending && cancelJobId === job.id ? 'Canceling…' : 'Cancel ingestion'}</button>}{job.cancel_requested && job.status.toLowerCase() !== "cancelled" && <small className="job-cancel-requested">Cancellation requested</small>}{cancelJobId === job.id && cancelJobError && <p role="alert">{cancelJobError}</p>}</div></div>)}</div>}{runningJobs.length > 0 && <p className="side-muted"><LoaderCircle size={13} className="spin" /> Refreshing while {runningJobs.length} job{runningJobs.length === 1 ? ' is' : 's are'} active.</p>}</section><div className="knowledge-note"><BookOpenText size={18} /><p>Only <strong>published</strong> documents available to this workspace and policy date can support customer answers.</p></div></aside></div>
  </div>
}

function DocumentRow({ doc, canManage, busy, error, onPublish, onRetry, onDelete, onReplace }: { doc: Document; canManage: boolean; busy: boolean; error: string | null; onPublish: () => void; onRetry: () => void; onDelete: () => void; onReplace: (event: ChangeEvent<HTMLInputElement>) => void }) {
  const isPublished = doc.status.toLowerCase() === 'published'
  const isFailed = doc.status.toLowerCase() === 'failed'
  const isProcessing = ACTIVE_STATES.has(doc.status.toLowerCase())
  return <article className="document-row"><span className="document-icon"><FileText size={20} /></span><div className="document-main"><div className="document-heading"><h3>{doc.title}</h3><StatusPill value={doc.status} /></div><div className="document-meta"><span>{titleCase(doc.kind || doc.title.split('.').pop() || 'file')}</span>{doc.category && <span>{titleCase(doc.category)}</span>}{doc.authority && <span>{titleCase(doc.authority)}</span>}<span>Version {doc.current_version ?? '—'}</span>{doc.chunk_count != null && <span>{doc.chunk_count} passages</span>}<span>{doc.updated_at ? relativeTime(doc.updated_at) : 'Date unavailable'}</span></div>{doc.effective_date && <small className="document-effective">Effective {shortDate(doc.effective_date)}</small>}{doc.error && <p className="document-error"><AlertCircle size={14} />{doc.error}</p>}{error && <p className="document-error" role="alert"><AlertCircle size={14} />{error}</p>}{canManage && <div className="document-actions">{!isPublished && !isFailed && !isProcessing && <button type="button" className="text-action" disabled={busy} onClick={onPublish}>Publish <ArrowRight size={13} /></button>}{isFailed && <button type="button" className="text-action" disabled={busy} onClick={onRetry}><RefreshCcw size={13} /> Retry</button>}<label className={`text-action upload-action${busy ? ' disabled' : ''}`}>Replace<input type="file" accept={ACCEPTED} onChange={onReplace} disabled={busy} /><ArrowRight size={13} /></label><button type="button" className="text-action danger" disabled={busy} onClick={onDelete}><Trash2 size={13} /> Delete</button></div>}</div></article>
}
