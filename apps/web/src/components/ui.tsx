import type { ReactNode } from 'react'
import { AlertCircle, ArrowRight, LoaderCircle, RefreshCcw } from 'lucide-react'
import { titleCase } from '../lib/format'

export function StatusPill({ value, subtle = false }: { value: string; subtle?: boolean }) {
  const key = value.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  return <span className={`status-pill status-${key}${subtle ? ' subtle' : ''}`}><span className="status-dot" />{titleCase(value)}</span>
}

export function QueryBlock({ title, error, retry, children }: { title: string; error?: Error | null; retry?: () => void; children?: ReactNode }) {
  if (!error) return <>{children}</>
  return (
    <div className="state-card error-state" role="alert">
      <span className="state-icon"><AlertCircle size={20} /></span>
      <h3>{title}</h3>
      <p>{error.message}</p>
      {retry && <button className="btn btn-secondary" type="button" onClick={retry}><RefreshCcw size={15} /> Retry</button>}
    </div>
  )
}

export function LoadingState({ label = 'Loading…', compact = false }: { label?: string; compact?: boolean }) {
  return <div className={`loading-state${compact ? ' compact' : ''}`} role="status"><LoaderCircle className="spin" size={18} />{label}</div>
}

export function EmptyState({ icon, title, description, action }: { icon?: ReactNode; title: string; description: string; action?: ReactNode }) {
  return <div className="state-card empty-state"><span className="state-icon">{icon || <ArrowRight size={20} />}</span><h3>{title}</h3><p>{description}</p>{action}</div>
}

export function PageHeading({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>{action && <div className="page-heading-action">{action}</div>}</div>
}
