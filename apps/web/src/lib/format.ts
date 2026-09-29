function serverDate(value: string): Date {
  // SQLite demo timestamps can lose the UTC offset during serialization.
  const normalized = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value) ? `${value}Z` : value
  return new Date(normalized)
}

export function shortDate(value?: string | null): string {
  if (!value) return '—'
  const date = serverDate(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric' }).format(date)
}

export function shortTime(value?: string | null): string {
  if (!value) return ''
  const date = serverDate(value)
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('en', { hour: 'numeric', minute: '2-digit' }).format(date)
}

export function relativeTime(value?: string | null): string {
  if (!value) return ''
  const timestamp = serverDate(value).getTime()
  if (Number.isNaN(timestamp)) return ''
  const minutes = Math.round((timestamp - Date.now()) / 60_000)
  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  if (Math.abs(minutes) < 60) return formatter.format(minutes, 'minute')
  const hours = Math.round(minutes / 60)
  if (Math.abs(hours) < 48) return formatter.format(hours, 'hour')
  return formatter.format(Math.round(hours / 24), 'day')
}

export function money(cents?: number, currency = 'USD'): string {
  if (typeof cents !== 'number') return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(cents / 100)
}

export function titleCase(value?: string | null): string {
  if (!value) return 'Unknown'
  return value.replace(/[_-]/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function initials(value?: string | null): string {
  return (value || '?').trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() || '').join('')
}
