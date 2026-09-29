import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Check, Clock3, MessageSquareText, RefreshCcw, Search, Send, Ticket as TicketIcon } from 'lucide-react'
import { api, type Order, type Session, type Ticket } from '../../lib/api'
import { relativeTime, titleCase } from '../../lib/format'
import { EmptyState, LoadingState, PageHeading, QueryBlock, StatusPill } from '../../components/ui'

export function TicketsView({ session }: { session: Session }) {
  const tickets = useQuery({ queryKey: ['tickets'], queryFn: api.tickets })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const visible = useMemo(() => (tickets.data?.items || []).filter((ticket) => (filter === 'all' || ticket.status.toLowerCase() === filter) && (!search.trim() || [ticket.subject, ticket.customer_name, ticket.id].some((value) => value?.toLowerCase().includes(search.toLowerCase())))), [filter, search, tickets.data])
  const selected = visible.find((ticket) => ticket.id === selectedId) || visible[0]
  const open = (tickets.data?.items || []).filter((ticket) => ticket.status.toLowerCase() === 'open').length
  return <div className="content-page"><PageHeading eyebrow="CASE HANDOFF" title="Keep the human thread." description="Escalated cases retain the problem, evidence, and unresolved questions for a thoughtful reply." action={<div className="page-stats"><span><strong>{open}</strong> open tickets</span></div>} /><div className="tickets-layout"><section className="ticket-list-panel"><div className="section-heading"><div><p className="eyebrow">QUEUE</p><h2>Tickets</h2></div><button className="icon-button" type="button" onClick={() => void tickets.refetch()} title="Refresh tickets" aria-label="Refresh tickets"><RefreshCcw size={17} /></button></div><label className="search-field"><Search size={16} /><span className="sr-only">Search tickets</span><input placeholder="Search tickets" value={search} onChange={(event) => setSearch(event.target.value)} /></label><div className="filter-segments ticket-filter" role="group" aria-label="Filter tickets">{['all', 'open', 'resolved'].map((value) => <button key={value} type="button" className={filter === value ? 'active' : ''} aria-pressed={filter === value} onClick={() => setFilter(value)}>{titleCase(value)}</button>)}</div><QueryBlock title="Could not load tickets" error={tickets.error} retry={() => void tickets.refetch()}>{tickets.isPending ? <LoadingState label="Loading tickets…" /> : visible.length === 0 ? <EmptyState icon={<TicketIcon size={21} />} title="No tickets found" description="Escalated cases will appear here." /> : visible.map((ticket) => <button className={`ticket-row${selected?.id === ticket.id ? ' active' : ''}`} key={ticket.id} type="button" onClick={() => setSelectedId(ticket.id)}><span className="ticket-row-icon"><TicketIcon size={17} /></span><span><span className="ticket-row-title"><strong>{ticket.subject}</strong><small>{relativeTime(ticket.updated_at)}</small></span><span className="ticket-row-customer">{ticket.customer_name || `Ticket ${ticket.id}`}</span><StatusPill value={ticket.status} subtle /></span></button>)}</QueryBlock></section><section className="ticket-detail-panel">{selected ? <TicketDetail key={selected.id} ticket={selected} session={session} /> : <EmptyState icon={<MessageSquareText size={22} />} title="Choose a ticket" description="Open an escalated case to review its context and reply." />}</section></div></div>
}

function TicketDetail({ ticket, session }: { ticket: Ticket; session: Session }) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState(ticket.draft_response || '')
  const canReply = ['admin', 'operator'].includes(session.user.role)
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['tickets'] })
  const reply = useMutation({ mutationFn: () => api.replyTicket(ticket.id, draft.trim()), onSuccess: () => { setDraft(''); refresh(); if (ticket.conversation_id) void queryClient.invalidateQueries({ queryKey: ['conversation', ticket.conversation_id] }) } })
  const status = useMutation({ mutationFn: () => api.setTicketStatus(ticket.id, ticket.status.toLowerCase() === 'resolved' ? 'open' : 'resolved'), onSuccess: refresh })
  return <><div className="ticket-detail-header"><div><p className="eyebrow">TICKET · {ticket.id}</p><h2>{ticket.subject}</h2><p>{ticket.customer_name || 'Customer'} <span>·</span> Last activity {relativeTime(ticket.updated_at)}</p></div><StatusPill value={ticket.status} /></div><div className="ticket-detail-scroll"><div className="ticket-content-block"><span className="ticket-block-icon"><TicketIcon size={18} /></span><div><p className="eyebrow">HANDOFF SUMMARY</p><h3>What needs attention</h3><p>{ticket.summary || 'No summary was returned for this ticket. Review the linked conversation before replying.'}</p></div></div><TicketOrderContext orders={ticket.order_context} />{ticket.unresolved_questions?.length ? <div className="ticket-questions"><p className="eyebrow">UNRESOLVED QUESTIONS</p>{ticket.unresolved_questions.map((question) => <p key={question}><ArrowRight size={15} />{question}</p>)}</div> : null}{ticket.conversation_id && <a className="linked-conversation" href={`#inbox/${ticket.conversation_id}`}><MessageSquareText size={17} /> Open linked conversation <ArrowRight size={15} /></a>}</div><div className="ticket-reply-area"><label htmlFor={`reply-${ticket.id}`}>Reply to the customer</label><textarea id={`reply-${ticket.id}`} rows={4} value={draft} onChange={(event) => setDraft(event.target.value)} disabled={!canReply || reply.isPending} placeholder="Write a clear next step for the customer…" /><div className="ticket-actions"><button className="btn btn-secondary" type="button" disabled={!canReply || status.isPending} onClick={() => status.mutate()}>{ticket.status.toLowerCase() === 'resolved' ? <><Clock3 size={15} /> Reopen</> : <><Check size={15} /> Resolve</>}</button><button className="btn btn-primary" type="button" disabled={!canReply || !draft.trim() || reply.isPending} onClick={() => reply.mutate()}><Send size={15} /> {reply.isPending ? 'Sending…' : 'Send reply'}</button></div>{!canReply && <p className="permission-note">Operator or admin access is required to reply or change status.</p>}{reply.isError && <p className="inline-error" role="alert">{reply.error.message}</p>}{status.isError && <p className="inline-error" role="alert">{status.error.message}</p>}{reply.isSuccess && <p className="inline-success" role="status"><Check size={14} /> Reply recorded in the local conversation.</p>}</div></>
}

function TicketOrderContext({ orders }: { orders?: Order[] }) {
  if (!orders?.length) return null

  return <section className="ticket-order-context" aria-label="Verified order context">
    <p className="eyebrow">VERIFIED ORDER CONTEXT</p>
    {orders.map((order) => <div className="ticket-order-card" key={order.id}>
      <div className="ticket-order-top"><strong>Order {order.number || order.id}</strong><StatusPill value={order.status} subtle /></div>
      {order.shipments?.length ? <div className="ticket-shipments">{order.shipments.map((shipment, index) => {
        const tracking = shipment.tracking_code || shipment.tracking_number
        return <span className="ticket-shipment" key={shipment.id || index}>{titleCase(shipment.status || 'unknown')}{shipment.carrier ? ' · ' + shipment.carrier : ''}{tracking ? ' · ' + tracking : ''}</span>
      })}</div> : <p className="ticket-no-shipment">No shipment information attached.</p>}
    </div>)}
  </section>
}