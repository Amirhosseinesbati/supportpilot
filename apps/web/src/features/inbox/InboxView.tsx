import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, ArrowLeft, ArrowRight, BookOpenText, Check, ChevronDown, CircleHelp, ClipboardList, FileText, Inbox, LoaderCircle, MessageCircle, Package, PanelRightClose, PanelRightOpen, Search, Send, ShieldCheck, Sparkles, X } from 'lucide-react'
import { api, type Citation, type Conversation, type ConversationSummary, type Order, type OrderLine, type Proposal, type Session } from '../../lib/api'
import { initials, money, relativeTime, shortDate, shortTime, titleCase } from '../../lib/format'
import { EmptyState, LoadingState, QueryBlock, StatusPill } from '../../components/ui'

type ContextTab = 'evidence' | 'orders' | 'actions'
type MobilePane = 'list' | 'conversation' | 'context'

export function InboxView({ session }: { session: Session }) {
  const queryClient = useQueryClient()
  const list = useQuery({ queryKey: ['conversations'], queryFn: api.conversations })
  const [selectedId, setSelectedId] = useState<string | null>(() => window.location.hash.split('/')[1] || null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<'all' | 'open' | 'resolved'>('all')
  const [contextTab, setContextTab] = useState<ContextTab>('evidence')
  const [contextOpen, setContextOpen] = useState(true)
  const [mobilePane, setMobilePane] = useState<MobilePane>('list')
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null)
  const detail = useQuery({ queryKey: ['conversation', selectedId], queryFn: () => api.conversation(selectedId!), enabled: !!selectedId })

  useEffect(() => {
    if (!selectedId && list.data?.items.length) setSelectedId(list.data.items[0]!.id)
  }, [list.data, selectedId])

  const visible = useMemo(() => (list.data?.items || []).filter((item) => {
    const matchesFilter = filter === 'all' || item.status.toLowerCase() === filter
    const term = search.toLowerCase().trim()
    return matchesFilter && (!term || [item.subject, item.customer_name, item.last_message, item.id].some((value) => value?.toLowerCase().includes(term)))
  }), [filter, list.data, search])

  const selectConversation = (id: string) => {
    setSelectedId(id)
    setMobilePane('conversation')
    window.location.hash = `inbox/${id}`
  }

  const createConversation = useMutation({
    mutationFn: () => api.createConversation('New support conversation'),
    onSuccess: (created) => { void queryClient.invalidateQueries({ queryKey: ['conversations'] }); selectConversation(created.id) },
  })

  return <div className={`inbox-layout${contextOpen ? '' : ' context-collapsed'} mobile-pane-${mobilePane}`}>
    <section className="inbox-list-panel" aria-label="Conversations">
      <div className="inbox-list-header"><div><p className="eyebrow">SUPPORT DESK</p><h1>Inbox <span className="heading-count">{list.data?.items.length ?? '—'}</span></h1></div>{session.user.role === 'customer' && <button className="icon-button new-conversation-button" type="button" title="New conversation" aria-label="New conversation" onClick={() => createConversation.mutate()} disabled={createConversation.isPending}><span>＋</span></button>}</div>
      {createConversation.isError && <p className="inline-error" role="alert">{createConversation.error.message}</p>}
      <div className="inbox-tools"><label className="search-field"><Search size={16} /><span className="sr-only">Search conversations</span><input placeholder="Search conversations" value={search} onChange={(event) => setSearch(event.target.value)} /></label><div className="filter-segments" role="group" aria-label="Filter conversations">{(['all', 'open', 'resolved'] as const).map((value) => <button key={value} type="button" className={filter === value ? 'active' : ''} aria-pressed={filter === value} onClick={() => setFilter(value)}>{titleCase(value)}</button>)}</div></div>
      <div className="conversation-list-scroll"><QueryBlock title="Could not load conversations" error={list.error} retry={() => void list.refetch()}>{list.isPending ? <LoadingState label="Loading conversations…" /> : visible.length === 0 ? <EmptyState icon={<Inbox size={20} />} title={search ? 'No matching conversations' : 'Your inbox is clear'} description={search ? 'Try a different search or filter.' : 'New customer conversations will appear here.'} /> : visible.map((item) => <ConversationRow key={item.id} item={item} active={selectedId === item.id} onClick={() => selectConversation(item.id)} />)}</QueryBlock></div>
      <div className="inbox-list-footer"><span className="live-dot" />{list.data ? `${visible.length} conversations shown` : 'Waiting for service'}</div>
    </section>
    <section className="conversation-panel" aria-label="Selected conversation">
      <div className="mobile-pane-tabs" role="tablist" aria-label="Inbox panels"><button role="tab" aria-selected={mobilePane === 'list'} className={mobilePane === 'list' ? 'active' : ''} onClick={() => setMobilePane('list')} type="button">Inbox</button><button role="tab" aria-selected={mobilePane === 'conversation'} className={mobilePane === 'conversation' ? 'active' : ''} onClick={() => setMobilePane('conversation')} type="button">Conversation</button><button role="tab" aria-selected={mobilePane === 'context'} className={mobilePane === 'context' ? 'active' : ''} onClick={() => setMobilePane('context')} type="button">Context</button></div>
      {!selectedId ? <EmptyState icon={<MessageCircle size={22} />} title="Select a conversation" description="Choose a thread to see its messages, evidence, and order context." /> : <QueryBlock title="Could not load this conversation" error={detail.error} retry={() => void detail.refetch()}>{detail.isPending ? <LoadingState label="Loading conversation…" /> : detail.data && <ConversationThread key={detail.data.id} conversation={detail.data} session={session} onCitation={setActiveCitation} contextOpen={contextOpen} toggleContext={() => setContextOpen((value) => !value)} />}</QueryBlock>}
    </section>
    {contextOpen && <aside className="context-panel" aria-label="Conversation context"><div className="mobile-context-heading"><button type="button" className="icon-button" onClick={() => setMobilePane('conversation')} aria-label="Back to conversation"><ArrowLeft size={20} /></button><strong>Context</strong></div>{detail.data ? <ContextPanel conversation={detail.data} tab={contextTab} setTab={setContextTab} onCitation={setActiveCitation} canPropose={session.user.role !== 'viewer'} /> : <div className="context-placeholder"><CircleHelp size={24} /><p>Conversation details appear here.</p></div>}</aside>}
    {activeCitation && <SourceDrawer citation={activeCitation} close={() => setActiveCitation(null)} />}
  </div>
}

function ConversationRow({ item, active, onClick }: { item: ConversationSummary; active: boolean; onClick: () => void }) {
  return <button type="button" onClick={onClick} className={`conversation-row${active ? ' active' : ''}`} aria-current={active ? 'true' : undefined}><span className="conversation-avatar">{initials(item.customer_name || item.subject)}</span><span className="conversation-row-content"><span className="conversation-row-top"><strong>{item.customer_name || 'Customer'}</strong><small>{relativeTime(item.updated_at)}</small></span><span className="conversation-row-subject">{item.subject}</span><span className="conversation-row-preview">{item.last_message || 'Open conversation'}</span><span className="conversation-row-bottom"><StatusPill value={item.status} subtle />{(item.unread_count ?? 0) > 0 && <span className="unread-count">{item.unread_count}</span>}</span></span></button>
}

function ConversationThread({ conversation, session, onCitation, contextOpen, toggleContext }: { conversation: Conversation; session: Session; onCitation: (citation: Citation) => void; contextOpen: boolean; toggleContext: () => void }) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState('')
  const [streamedAnswer, setStreamedAnswer] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const send = useMutation({
    mutationFn: () => api.sendMessageStream(conversation.id, draft.trim(), (chunk) => setStreamedAnswer((value) => value + chunk)),
    onSuccess: () => {
      setDraft('')
      void queryClient.invalidateQueries({ queryKey: ['conversation', conversation.id] })
      void queryClient.invalidateQueries({ queryKey: ['conversations'] })
    },
  })
  const escalate = useMutation({
    mutationFn: () => api.escalateConversation(conversation.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['conversation', conversation.id] })
      void queryClient.invalidateQueries({ queryKey: ['conversations'] })
      void queryClient.invalidateQueries({ queryKey: ['tickets'] })
    },
  })
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }) }, [conversation.messages.length, streamedAnswer])
  const submit = () => { if (draft.trim() && !send.isPending) { setStreamedAnswer(''); send.mutate() } }
  const citations = conversation.messages.flatMap((message) => message.citations || [])
  return <>
    <div className="thread-header"><div className="thread-header-main"><span className="thread-avatar">{initials(conversation.customer?.name || conversation.customer_name)}</span><span><p className="thread-kicker">CONVERSATION · {conversation.id}</p><h2>{conversation.subject}</h2><div className="thread-meta"><span>{conversation.customer?.name || conversation.customer_name || 'Customer'}</span><span className="meta-divider">·</span><StatusPill value={conversation.status} subtle /></div></span></div><div className="thread-header-actions">{!conversation.ticket && session.user.role !== 'viewer' && <button className="btn btn-secondary escalate-button" type="button" disabled={escalate.isPending} onClick={() => escalate.mutate()}><ClipboardList size={15} />{escalate.isPending ? 'Escalating…' : 'Escalate'}</button>}<button className="icon-button context-toggle" type="button" onClick={toggleContext} aria-label={contextOpen ? 'Hide context panel' : 'Show context panel'} title={contextOpen ? 'Hide context' : 'Show context'}>{contextOpen ? <PanelRightClose size={20} /> : <PanelRightOpen size={20} />}</button></div></div>{escalate.isError && <p className="thread-error" role="alert">{escalate.error.message}</p>}
    <div className="conversation-scroll" ref={scrollRef}><div className="conversation-content"><div className="conversation-date"><span>Conversation history</span></div>{conversation.messages.length === 0 ? <EmptyState icon={<MessageCircle size={20} />} title="Start the conversation" description="Ask a question about an order, product, or policy. Responses will show their sources." /> : conversation.messages.map((message) => <div key={message.id} className={`message message-${message.role.toLowerCase()}`}><span className={`message-avatar avatar-${message.role.toLowerCase()}`}>{message.role.toLowerCase() === 'assistant' ? <Sparkles size={16} /> : initials(message.role.toLowerCase() === 'customer' ? conversation.customer?.name : 'Support operator')}</span><div className="message-body"><div className="message-byline"><strong>{message.role.toLowerCase() === 'assistant' ? 'SupportPilot' : message.role.toLowerCase() === 'customer' ? conversation.customer?.name || 'Customer' : 'Support operator'}</strong><span>{shortTime(message.created_at)}</span>{message.role.toLowerCase() === 'assistant' && <span className="ai-label">AI ASSISTED</span>}</div><div className="message-bubble">{message.content}</div>{(message.citations || []).length > 0 && <div className="citation-list"><span className="citation-prefix"><BookOpenText size={13} /> SOURCES</span>{message.citations!.map((citation) => <button className="citation-chip" type="button" key={citation.chunk_id} onClick={() => onCitation(citation)}><FileText size={13} />{citation.document_title}<ArrowRight size={12} /></button>)}</div>}{!!message.missing_information?.length && <div className="message-info"><CircleHelp size={15} /><span>Missing information: {message.missing_information.join('; ')}</span></div>}{message.next_action && message.next_action !== 'none' && <div className="message-next-action"><ArrowRight size={14} />{titleCase(message.next_action)}</div>}</div></div>)}{conversation.proposals?.length ? <div className="thread-action-summary"><ShieldCheck size={18} /><span><strong>{conversation.proposals.length} service action{conversation.proposals.length === 1 ? '' : 's'}</strong><small>Review details in the Actions context tab.</small></span></div> : null}{conversation.ticket && <div className="thread-action-summary"><ClipboardList size={18} /><span><strong>Ticket {conversation.ticket.id}</strong><small>{conversation.ticket.subject} · {titleCase(conversation.ticket.status)}</small></span></div>}{send.isPending && (streamedAnswer ? <div className="message message-assistant" role="status"><span className="message-avatar avatar-assistant"><Sparkles size={16} /></span><div className="message-body"><div className="message-byline"><strong>SupportPilot</strong><span className="ai-label">STREAMING</span></div><div className="message-bubble">{streamedAnswer}</div></div></div> : <div className="sending-indicator" role="status"><LoaderCircle size={16} className="spin" /> Waiting for the support workflow…</div>)}</div></div>
    <div className="composer-wrap"><div className="composer"><label className="sr-only" htmlFor="message-composer">Write a message</label><textarea id="message-composer" rows={2} placeholder={session.user.role === 'viewer' ? 'Viewer access is read only' : session.user.role === 'customer' ? 'Ask about a product, policy, or your order…' : 'Write a reply or ask SupportPilot to investigate…'} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); submit() } }} disabled={send.isPending || session.user.role === 'viewer'} /><div className="composer-bottom"><span><ShieldCheck size={14} /> {session.user.role === 'viewer' ? 'Viewer access is read only' : 'Responses are checked against available evidence'}</span><button className="send-button" type="button" onClick={submit} disabled={!draft.trim() || send.isPending || session.user.role === 'viewer'} aria-label="Send message">{send.isPending ? <LoaderCircle size={17} className="spin" /> : <Send size={17} />}<span>Send</span></button></div></div>{send.isError && <div className="composer-error" role="alert"><AlertCircle size={15} />{send.error.message}<button type="button" onClick={submit}>Retry</button></div>}{citations.length === 0 && conversation.messages.length > 0 && <p className="composer-note">No source passages are attached to this thread yet.</p>}</div>
  </>
}

function ContextPanel({ conversation, tab, setTab, onCitation, canPropose }: { conversation: Conversation; tab: ContextTab; setTab: (tab: ContextTab) => void; onCitation: (citation: Citation) => void; canPropose: boolean }) {
  const citations = Array.from(new Map(conversation.messages.flatMap((message) => message.citations || []).map((citation) => [citation.chunk_id, citation])).values())
  return <><div className="context-heading"><div><p className="eyebrow">CUSTOMER CONTEXT</p><h2>At a glance</h2></div><span className="context-badge"><Sparkles size={13} /> Live context</span></div><div className="customer-context-card"><span className="customer-context-avatar">{initials(conversation.customer?.name || conversation.customer_name)}</span><div><strong>{conversation.customer?.name || conversation.customer_name || 'Customer'}</strong><small>{conversation.customer?.email || 'Email unavailable'}</small></div></div><div className="context-tabs" role="tablist" aria-label="Context sections">{(['evidence', 'orders', 'actions'] as const).map((value) => <button key={value} className={tab === value ? 'active' : ''} type="button" role="tab" aria-selected={tab === value} onClick={() => setTab(value)}>{titleCase(value)}{value === 'evidence' && citations.length > 0 ? <span>{citations.length}</span> : value === 'actions' && (conversation.proposals?.length || 0) > 0 ? <span>{conversation.proposals?.length}</span> : null}</button>)}</div><div className="context-scroll">{tab === 'evidence' && <div className="context-section"><p className="section-overline">GROUNDED ANSWERS</p><h3>Sources used in this thread</h3>{citations.length === 0 ? <div className="context-empty"><BookOpenText size={23} /><strong>No sources cited yet</strong><p>Source passages appear here when an answer is grounded in published knowledge.</p></div> : citations.map((citation, index) => <button key={citation.chunk_id} type="button" className="source-card" onClick={() => onCitation(citation)}><span className="source-index">{String(index + 1).padStart(2, '0')}</span><span className="source-card-body"><strong>{citation.document_title}</strong><small>{citation.section || `Version ${citation.version ?? 'current'}`}</small><span>{citation.passage}</span><em>View passage <ArrowRight size={13} /></em></span></button>)}{conversation.events?.length ? <div className="event-list"><p className="section-overline">OBSERVABLE ACTIVITY</p>{conversation.events.map((event) => <div className="event-row" key={event.id}><span className="event-marker" /><div><strong>{event.summary || titleCase(event.kind)}</strong><small>{eventText(event.detail) || (event.created_at ? shortDate(event.created_at) : '')}</small></div></div>)}</div> : null}</div>}{tab === 'orders' && <div className="context-section"><p className="section-overline">COMMERCE</p><h3>Linked orders</h3>{!conversation.orders?.length ? <div className="context-empty"><Package size={23} /><strong>No linked orders</strong><p>Authenticated order details will appear here when linked to this customer.</p></div> : conversation.orders.map((order) => <OrderCard key={order.id} order={order} conversationId={conversation.id} canPropose={canPropose} />)}</div>}{tab === 'actions' && <div className="context-section"><p className="section-overline">SERVICE ACTIONS</p><h3>Proposals & handoff</h3>{!conversation.proposals?.length && !conversation.ticket ? <div className="context-empty"><ShieldCheck size={23} /><strong>No actions drafted</strong><p>Return proposals and escalation tickets will appear here.</p></div> : null}{conversation.proposals?.map((proposal) => <ProposalCard key={proposal.id} proposal={proposal} />)}{conversation.ticket && <div className="context-action-card"><div className="action-card-head"><ClipboardList size={18} /><StatusPill value={conversation.ticket.status} /></div><strong>Ticket {conversation.ticket.id}</strong><p>{conversation.ticket.subject}</p><small>Open Tickets for the operator reply and resolution.</small></div>}</div>}</div></>
}

function eventText(detail: Record<string, unknown> | string | undefined): string {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  return Object.entries(detail).slice(0, 3).map(([key, value]) => `${titleCase(key)}: ${typeof value === 'string' ? value : JSON.stringify(value)}`).join(' · ')
}

function OrderCard({ order, conversationId, canPropose }: { order: Order; conversationId: string; canPropose: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const detail = useQuery({ queryKey: ['order', order.id], queryFn: () => api.order(order.id), enabled: expanded })
  const fullOrder = detail.data || order
  const lines = fullOrder.lines || fullOrder.items || []
  return <div className="order-card"><button className="order-card-toggle" type="button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}><span className="order-icon"><Package size={17} /></span><span><strong>Order {order.number || order.id}</strong><small>{shortDate(order.placed_at)} · {money(order.total_cents, order.currency)}</small></span><ChevronDown size={16} className={expanded ? 'rotate' : ''} /></button><div className="order-status-line"><StatusPill value={order.status} subtle /></div>{expanded && <div className="order-details"><QueryBlock title="Could not open this order" error={detail.error} retry={() => void detail.refetch()}>{detail.isPending ? <LoadingState compact label="Checking access and loading order…" /> : <><div className="order-data-row"><span>Placed</span><strong>{shortDate(fullOrder.placed_at)}</strong></div><div className="order-data-row"><span>Order total</span><strong>{money(fullOrder.total_cents, fullOrder.currency)}</strong></div>{fullOrder.shipments?.map((shipment, index) => <div className="shipment-row" key={shipment.id || index}><span className="shipment-icon"><Package size={14} /></span><span><strong>{titleCase(shipment.status)}</strong><small>{shipment.carrier || 'Shipment'}{shipment.tracking_code || shipment.tracking_number ? ` · ${shipment.tracking_code || shipment.tracking_number}` : ''}</small></span></div>)}{canPropose ? <ReturnForm order={fullOrder} lines={lines} conversationId={conversationId} /> : <p className="permission-note">Viewer access cannot draft returns.</p>}</>}</QueryBlock></div>}</div>
}

function ReturnForm({ order, lines, conversationId }: { order: Order; lines: OrderLine[]; conversationId: string }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [lineId, setLineId] = useState(lines[0]?.id || '')
  const [quantity, setQuantity] = useState(1)
  const [condition, setCondition] = useState('unopened')
  const [reason, setReason] = useState('')
  const selectedLine = lines.find((line) => line.id === lineId)
  const propose = useMutation({
    mutationFn: () => api.createReturnProposal({ order_id: order.id, line_id: lineId, quantity, condition, reason: reason.trim(), conversation_id: conversationId }),
    onSuccess: () => { setOpen(false); setReason(''); void queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] }); void queryClient.invalidateQueries({ queryKey: ['proposals'] }) },
  })
  if (!lines.length) return <p className="help-text">Return drafting is unavailable because line items were not returned for this order.</p>
  return <div className="return-area">{!open ? <button className="text-action" type="button" onClick={() => setOpen(true)}>Draft a return request <ArrowRight size={14} /></button> : <form onSubmit={(event) => { event.preventDefault(); propose.mutate() }} className="return-form"><div className="return-form-title"><strong>Draft return request</strong><button type="button" className="icon-button" onClick={() => setOpen(false)} aria-label="Close return form"><X size={15} /></button></div><label>Item<select value={lineId} onChange={(event) => { setLineId(event.target.value); setQuantity(1) }}>{lines.map((line) => <option key={line.id} value={line.id}>{line.product_name || line.title || line.sku || line.id}</option>)}</select></label><div className="form-grid-two"><label>Quantity<input type="number" min={1} max={Math.max(1, (selectedLine?.quantity || 1) - (selectedLine?.returned_quantity || 0))} value={quantity} onChange={(event) => setQuantity(Number(event.target.value))} required /></label><label>Condition<select value={condition} onChange={(event) => setCondition(event.target.value)}><option value="unopened">Unopened</option><option value="opened">Opened</option><option value="damaged">Damaged</option></select></label></div><label>Reason<textarea rows={3} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Describe why the customer wants to return this item" required /></label><p className="form-note"><ShieldCheck size={14} /> Eligibility and review requirements are checked by the server.</p>{propose.isError && <p className="inline-error" role="alert">{propose.error.message}</p>}<button className="btn btn-primary full-width" type="submit" disabled={propose.isPending || !lineId || !reason.trim()}>{propose.isPending ? 'Checking policy…' : 'Create proposal'}</button></form>}{propose.isSuccess && <div className="inline-success" role="status"><Check size={14} /> Proposal {propose.data.proposal.id} {propose.data.idempotent_replay ? 'already existed.' : `saved with status ${titleCase(propose.data.proposal.status)}.`}</div>}</div>
}

function ProposalCard({ proposal }: { proposal: Proposal }) {
  return <div className="context-action-card"><div className="action-card-head"><ShieldCheck size={18} /><StatusPill value={proposal.status} /></div><strong>Return proposal {proposal.id}</strong><p>{proposal.reason}</p><div className="action-card-grid"><span>Order</span><strong>{proposal.order_id}</strong><span>Quantity</span><strong>{proposal.quantity}</strong><span>Condition</span><strong>{titleCase(proposal.condition)}</strong></div>{proposal.policy_result?.explanation && <div className="action-exception"><AlertCircle size={14} />{proposal.policy_result.explanation}</div>}{proposal.requires_review && <small>Operator review required before creating a return record.</small>}{proposal.return_record_id && <small>Recorded return: {proposal.return_record_id}</small>}</div>
}

export function SourceDrawer({ citation, close }: { citation: Citation; close: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => { closeRef.current?.focus(); const onEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') close() }; window.addEventListener('keydown', onEscape); return () => window.removeEventListener('keydown', onEscape) }, [close])
  const source = useQuery({ queryKey: ['source', citation.chunk_id], queryFn: () => api.source(citation.chunk_id), retry: false, staleTime: 0 })
  const live = source.data
  return <div className="drawer-layer"><button type="button" className="drawer-backdrop" onClick={close} aria-label="Close source passage" /><aside className="source-drawer" role="dialog" aria-modal="true" aria-labelledby="source-drawer-title"><div className="drawer-header"><span className="drawer-icon"><BookOpenText size={20} /></span><button ref={closeRef} className="icon-button" type="button" aria-label="Close source passage" onClick={close}><X size={20} /></button></div><p className="eyebrow">VERIFIED SOURCE PASSAGE</p><h2 id="source-drawer-title">{live?.document_title || citation.document_title}</h2><QueryBlock title="This source is no longer available" error={source.error} retry={() => void source.refetch()}>{source.isPending ? <LoadingState label="Verifying published passage…" /> : live && <><div className="drawer-meta"><span><FileText size={14} /> {live.section || 'Document section'}</span>{live.page != null && <span>Page {live.page}</span>}{live.version != null && <span>Version {live.version}</span>}{live.effective_from && <span>Effective from {shortDate(live.effective_from)}</span>}{live.effective_to && <span>Effective until {shortDate(live.effective_to)}</span>}</div><div className="passage-card"><span>EXACT PUBLISHED PASSAGE</span><p>{live.passage}</p></div><p className="drawer-footnote"><ShieldCheck size={15} /> {live.historical ? 'This is a historical published version. Check its effective dates against the order event.' : 'This is the current published version available to this workspace.'}</p><div className="drawer-reference">Chunk reference <code>{live.chunk_id}</code></div></>}</QueryBlock></aside></div>
}
