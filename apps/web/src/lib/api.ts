const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly details?: unknown) {
    super(message)
    this.name = status === 401 ? 'AuthError' : 'ApiError'
  }
}

function messageFromError(body: unknown, status: number): string {
  if (body && typeof body === 'object') {
    const detail = 'detail' in body ? body.detail : 'message' in body ? body.message : undefined
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((item) =>
      item && typeof item === 'object' && 'msg' in item ? String(item.msg) : String(item),
    ).join('; ')
  }
  return `Request failed (${status}). Please try again.`
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      credentials: 'include',
      ...options,
      headers: {
        ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    })
  } catch {
    throw new ApiError('The support service is unreachable. Check the local API and retry.', 0)
  }
  if (response.status === 204) return undefined as T
  const contentType = response.headers.get('content-type') || ''
  const body: unknown = contentType.includes('application/json')
    ? await response.json().catch(() => null)
    : await response.text().catch(() => '')
  if (!response.ok) throw new ApiError(messageFromError(body, response.status), response.status, body)
  return body as T
}

const json = (value: unknown) => JSON.stringify(value)
const pathPart = (value: string) => encodeURIComponent(value)

export interface SendMessageResult { message: Message; assistant?: Message | null; next_action?: string | null; missing_information?: string[] | null }

async function streamedMessage(id: string, content: string, onChunk: (chunk: string) => void): Promise<SendMessageResult> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}/conversations/${pathPart(id)}/messages/stream`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: json({ content }),
    })
  } catch {
    throw new ApiError('The support service is unreachable. Check the local API and retry.', 0)
  }
  if (!response.ok) {
    if (response.status === 404 || response.status === 405 || response.status === 501) return request<SendMessageResult>(`/conversations/${pathPart(id)}/messages`, { method: 'POST', body: json({ content }) })
    const body: unknown = await response.json().catch(() => null)
    throw new ApiError(messageFromError(body, response.status), response.status, body)
  }
  if (!response.body) throw new ApiError('The answer stream was unavailable. Please refresh the conversation before retrying.', 0)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let event = ''
  let data: string[] = []
  let final: SendMessageResult | null = null
  const dispatch = () => {
    if (!data.length) { event = ''; return }
    let payload: unknown
    try { payload = JSON.parse(data.join('\n')) } catch { throw new ApiError('The answer stream contained invalid data. Refresh the conversation to check its saved state.', 0) }
    if (event === 'answer_chunk' && payload && typeof payload === 'object' && 'text' in payload && typeof payload.text === 'string') onChunk(payload.text)
    if (event === 'final') final = payload as SendMessageResult
    if (event === 'error') throw new ApiError(messageFromError(payload, 0), 0, payload)
    event = ''; data = []
  }
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const lines = buffer.split(/\r?\n/)
    buffer = done ? '' : lines.pop() || ''
    for (const line of lines) {
      if (!line) dispatch()
      else if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    }
    if (done) { if (buffer) data.push(buffer); dispatch(); break }
  }
  if (!final) throw new ApiError('The answer stream ended early. Refresh the conversation to check its saved state.', 0)
  return final
}

export type Role = 'admin' | 'operator' | 'viewer' | 'customer' | string
export interface User { id: string; email: string; role: Role; workspace_id: string; name: string; customer_id?: string | null }
export interface Workspace { id: string; name: string }
export interface Session { user: User; workspace: Workspace; demo: boolean }

export interface Citation {
  chunk_id: string
  document_title: string
  version?: string | number
  section?: string
  passage: string
  page?: number | null
  effective_date?: string | null
  effective_from?: string | null
  effective_to?: string | null
  historical?: boolean
}
export interface Message {
  id: string
  role: string
  content: string
  created_at: string
  citations?: Citation[]
  missing_information?: string[] | null
  next_action?: string | null
}
export interface ConversationSummary {
  id: string
  subject: string
  status: string
  customer_name?: string
  updated_at: string
  last_message?: string
  unread_count?: number
}
export interface Customer { id: string; name: string; email?: string }
export interface OrderLine {
  id: string
  product_id?: string
  product_name?: string
  title?: string
  sku?: string
  quantity: number
  unit_price_cents?: number
  returned_quantity?: number
  category?: string
}
export interface Shipment {
  id?: string
  status?: string
  carrier?: string
  tracking_number?: string
  tracking_code?: string
  estimated_delivery?: string | null
  delivered_at?: string | null
  promised_delivery_at?: string | null
}
export interface Order {
  id: string
  number?: string
  placed_at: string
  status: string
  total_cents?: number
  currency?: string
  lines?: OrderLine[]
  items?: OrderLine[]
  shipments?: Shipment[]
  delivered_at?: string | null
  customer_id?: string
}
export interface Proposal {
  id: string
  order_id: string
  line_id?: string
  conversation_id?: string | null
  status: string
  reason: string
  condition?: string
  quantity: number
  version: string
  requires_review?: boolean
  created_at?: string
  updated_at?: string
  eligibility_reason?: string | null
  consequence?: string | null
  return_request_id?: string | null
  return_record_id?: string | null
  policy_result?: { eligible?: boolean; requires_review?: boolean; code?: string; explanation?: string }
  expires_at?: string | null
}
export interface Ticket {
  id: string
  subject: string
  status: string
  customer_name?: string
  conversation_id?: string
  updated_at?: string
  summary?: string
  order_context?: Order[]
  unresolved_questions?: string[]
  draft_response?: string | null
}
export interface Event {
  id: string
  kind: string
  summary?: string
  created_at?: string
  detail?: Record<string, unknown> | string
}
export interface Conversation extends ConversationSummary {
  customer?: Customer
  messages: Message[]
  orders?: Order[]
  proposals?: Proposal[]
  ticket?: Ticket | null
  events?: Event[]
}
export interface Document {
  id: string
  title: string
  kind?: string
  category?: string
  authority?: string
  status: string
  current_version?: string | number
  updated_at?: string
  effective_date?: string | null
  chunk_count?: number
  error?: string | null
}
export interface IngestionJob {
  id: string
  document_id?: string
  status: string
  progress?: number
  failure_reason?: string | null
  error?: string | null
  cancel_requested?: boolean
  created_at?: string
}
export interface Connector {
  name: string
  mode: string
  status: string
  detail?: string
}
export interface EvaluationRatio { numerator?: number; denominator?: number; rate?: number }
export interface EvaluationSplit {
  coverage?: EvaluationRatio
  grounded_structured_claim_exact_match?: EvaluationRatio
  action_match?: EvaluationRatio
  citation_precision_on_emitted_ids?: EvaluationRatio
  missing_evidence_clarify_or_abstain?: EvaluationRatio
  security_denial_no_forbidden_fragment?: EvaluationRatio
  tool_success?: EvaluationRatio
  [key: string]: unknown
}
export interface EvaluationRun {
  id?: string
  started_at?: string
  completed_at?: string
  status?: string
  kind?: string
  total_predictions?: number
  split_results?: { development?: EvaluationSplit; held_out?: EvaluationSplit }
  human_review_completed?: boolean
  release_targets_verified?: boolean
  limitation?: string
  model_quality_measured?: boolean
  counts?: Record<string, number>
  total_cases?: number
  passed_cases?: number
  metrics?: Record<string, number | string | null>
  report_path?: string
}
export interface EvaluationSummary {
  dataset_count?: number
  latest_run: EvaluationRun | null
  [key: string]: unknown
}

export const api = {
  login: (email: string, password: string) => request<Session>('/auth/login', { method: 'POST', body: json({ email, password }) }),
  me: () => request<Session>('/me'),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  conversations: () => request<{ items: ConversationSummary[] }>('/conversations'),
  conversation: (id: string) => request<Conversation>(`/conversations/${pathPart(id)}`),
  createConversation: (subject: string) => request<ConversationSummary>('/conversations', { method: 'POST', body: json({ subject }) }),
  sendMessage: (id: string, content: string) => request<SendMessageResult>(`/conversations/${pathPart(id)}/messages`, { method: 'POST', body: json({ content }) }),
  sendMessageStream: streamedMessage,
  escalateConversation: (id: string) => request<Ticket>(`/conversations/${pathPart(id)}/escalate`, { method: 'POST' }),
  source: (chunkId: string) => request<Citation>(`/sources/${pathPart(chunkId)}`),
  order: (id: string) => request<Order>(`/orders/${pathPart(id)}`),
  documents: () => request<{ items: Document[]; jobs?: IngestionJob[] }>('/documents'),
  uploadDocument: (file: File, category = 'general', authority = 'uploaded') => {
    const body = new FormData()
    body.append('file', file)
    body.append('category', category)
    body.append('authority', authority)
    return request<Document | { document: Document; job?: IngestionJob }>('/documents', { method: 'POST', body })
  },
  replaceDocument: (id: string, file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<{ document: Document; job?: IngestionJob }>(`/documents/${pathPart(id)}/versions`, { method: 'POST', body })
  },
  retryDocument: (id: string) => request<{ document: Document; job?: IngestionJob }>(`/documents/${pathPart(id)}/retry`, { method: 'POST' }),
  cancelIngestionJob: (id: string) => request<{ id: string; status: string; cancel_requested: boolean }>(`/ingestion-jobs/${pathPart(id)}/cancel`, { method: 'POST' }),
  publishDocument: (id: string) => request<Document>(`/documents/${pathPart(id)}/publish`, { method: 'POST' }),
  deleteDocument: (id: string) => request<void>(`/documents/${pathPart(id)}`, { method: 'DELETE' }),
  proposals: () => request<{ items: Proposal[] }>('/proposals'),
  createReturnProposal: (input: { order_id: string; line_id: string; quantity: number; condition: string; reason: string; conversation_id?: string }) => request<{ proposal: Proposal; idempotent_replay: boolean }>('/returns/proposals', { method: 'POST', body: json(input) }),
  reviewProposal: (id: string, input: { decision: 'approve' | 'edit' | 'reject'; version: string; edited_reason?: string }) => request<{ proposal: Proposal; idempotent_replay: boolean }>(`/proposals/${pathPart(id)}/review`, { method: 'POST', body: json(input) }),
  tickets: () => request<{ items: Ticket[] }>('/tickets'),
  replyTicket: (id: string, content: string) => request<{ ticket: Ticket; message: Message }>(`/tickets/${pathPart(id)}/reply`, { method: 'POST', body: json({ content }) }),
  setTicketStatus: (id: string, status: 'resolved' | 'open') => request<Ticket>(`/tickets/${pathPart(id)}/status`, { method: 'POST', body: json({ status }) }),
  connectors: () => request<{ items: Connector[] }>('/connectors'),
  evaluations: () => request<EvaluationSummary>('/evaluations/summary'),
}
