import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpenText, ChartNoAxesCombined, CircleHelp, Headset, Inbox, LogOut, PanelLeftClose, Plug, ShieldCheck, Ticket, Wifi, WifiOff } from 'lucide-react'
import { api, ApiError, type Session } from './lib/api'
import { LoadingState, QueryBlock } from './components/ui'
import { InboxView } from './features/inbox/InboxView'
import { KnowledgeView } from './features/knowledge/KnowledgeView'
import { ApprovalsView } from './features/operations/ApprovalsView'
import { TicketsView } from './features/operations/TicketsView'
import { ConnectorsView } from './features/operations/ConnectorsView'
import { EvaluationsView } from './features/operations/EvaluationsView'
import { WidgetView } from './features/widget/WidgetView'

type Page = 'inbox' | 'knowledge' | 'approvals' | 'tickets' | 'connectors' | 'evaluations' | 'widget'
const pages: { id: Page; label: string; icon: typeof Inbox; roles?: string[] }[] = [
  { id: 'inbox', label: 'Inbox', icon: Inbox },
  { id: 'knowledge', label: 'Knowledge', icon: BookOpenText, roles: ['admin', 'operator', 'viewer'] },
  { id: 'approvals', label: 'Approvals', icon: ShieldCheck, roles: ['admin', 'operator', 'viewer'] },
  { id: 'tickets', label: 'Tickets', icon: Ticket, roles: ['admin', 'operator', 'viewer'] },
  { id: 'connectors', label: 'Connectors', icon: Plug, roles: ['admin', 'operator', 'viewer'] },
  { id: 'evaluations', label: 'Evaluation', icon: ChartNoAxesCombined, roles: ['admin', 'operator', 'viewer'] },
  { id: 'widget', label: 'Customer widget', icon: Headset },
]

function pageFromHash(): Page {
  const value = window.location.hash.slice(1).split('/')[0]
  return pages.some((page) => page.id === value) ? value as Page : 'inbox'
}

export default function App() {
  const queryClient = useQueryClient()
  const session = useQuery({ queryKey: ['me'], queryFn: api.me, retry: false, refetchInterval: 60_000 })
  const [page, setPage] = useState<Page>(pageFromHash)
  const [navOpen, setNavOpen] = useState(false)
  useEffect(() => {
    const onHashChange = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.clear()
      void queryClient.invalidateQueries({ queryKey: ['me'] })
    },
  })

  if (session.isPending) return <div className="boot-screen"><div className="brand-symbol">S<span>✳</span></div><LoadingState label="Connecting to SupportPilot…" /></div>
  if (session.isError) {
    const isUnauthorized = session.error instanceof ApiError && session.error.status === 401
    if (isUnauthorized) return <LoginScreen onLogin={(result) => queryClient.setQueryData(['me'], result)} />
    return <div className="boot-screen"><div className="brand-symbol">S<span>✳</span></div><QueryBlock title="Could not connect to SupportPilot" error={session.error} retry={() => void session.refetch()} /></div>
  }

  const activePage = pages.find((item) => item.id === page) || pages[0]!
  const visiblePages = pages.filter((item) => !item.roles || item.roles.includes(session.data.user.role))
  const allowedPage = visiblePages.some((item) => item.id === page) ? page : 'widget'
  const navigate = (next: Page) => { window.location.hash = next; setPage(next); setNavOpen(false) }
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className={`app-sidebar${navOpen ? ' is-open' : ''}`} aria-label="Primary navigation">
      <div className="sidebar-top">
        <button className="brand-lockup" type="button" onClick={() => navigate('inbox')} aria-label="SupportPilot home">
          <span className="brand-mark">S<span>✳</span></span><span className="brand-name">supportpilot<span className="brand-period">.</span></span>
        </button>
        <button className="mobile-close icon-button" onClick={() => setNavOpen(false)} type="button" aria-label="Close navigation"><PanelLeftClose size={20} /></button>
      </div>
      <div className="workspace-card"><span className="workspace-monogram">N</span><span className="workspace-name"><strong>{session.data.workspace.name}</strong><small>Support workspace</small></span><span className="workspace-chevron">⌄</span></div>
      <p className="sidebar-label">WORKSPACE</p>
      <nav className="nav-list">
        {visiblePages.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-item${allowedPage === id ? ' active' : ''}`} type="button" onClick={() => navigate(id)} aria-label={label} title={label} aria-current={allowedPage === id ? 'page' : undefined}><Icon size={18} strokeWidth={1.9} /><span>{label}</span></button>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="demo-note"><span className="demo-note-dot" /><span><strong>{session.data.demo ? 'Demo environment' : 'Connected environment'}</strong><small>{session.data.demo ? 'Synthetic demo dataset' : 'Live connectors may be active'}</small></span></div>
        <div className="sidebar-user"><span className="user-avatar">{session.data.user.name?.[0]?.toUpperCase() || 'U'}</span><span className="sidebar-user-copy"><strong>{session.data.user.name}</strong><small>{session.data.user.role}</small></span><button className="icon-button logout-button" type="button" onClick={() => logout.mutate()} disabled={logout.isPending} title="Sign out" aria-label="Sign out"><LogOut size={17} /></button></div>
        {logout.isError && <p className="inline-error" role="alert">{logout.error.message}</p>}
      </div>
    </aside>
    {navOpen && <button type="button" className="mobile-nav-backdrop" aria-label="Close navigation" onClick={() => setNavOpen(false)} />}
    <div className="main-shell">
      <header className="topbar">
        <div className="topbar-leading"><button className="mobile-menu icon-button" type="button" onClick={() => setNavOpen(true)} aria-label="Open navigation"><PanelLeftClose size={21} /></button><span className="breadcrumb-parent">Northstar Supply</span><span className="breadcrumb-divider">/</span><strong>{activePage.label}</strong></div>
        <div className="topbar-trailing"><span className="environment-label">{session.data.demo ? 'SYNTHETIC DEMO' : 'CONNECTED'}</span><span className="connection-indicator"><Wifi size={15} /> Service online</span><span className="topbar-help" title="Support documentation is included in the project docs"><CircleHelp size={18} /></span></div>
      </header>
      <main id="main-content" className={`main-content page-${allowedPage}`}>
        {allowedPage === 'inbox' && <InboxView session={session.data} />}
        {allowedPage === 'knowledge' && <KnowledgeView session={session.data} />}
        {allowedPage === 'approvals' && <ApprovalsView session={session.data} />}
        {allowedPage === 'tickets' && <TicketsView session={session.data} />}
        {allowedPage === 'connectors' && <ConnectorsView />}
        {allowedPage === 'evaluations' && <EvaluationsView />}
        {allowedPage === 'widget' && <WidgetView session={session.data} />}
      </main>
    </div>
  </div>
}

function LoginScreen({ onLogin }: { onLogin: (session: Session) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const login = useMutation({ mutationFn: () => api.login(email, password), onSuccess: onLogin })
  return <div className="login-screen">
    <div className="login-art"><div className="brand-lockup login-brand"><span className="brand-mark">S<span>✳</span></span><span className="brand-name">supportpilot<span className="brand-period">.</span></span></div><div className="login-art-content"><p className="eyebrow">NORTHSTAR SUPPLY · SUPPORT OPERATIONS</p><h1>Every answer<br /><em>has a source.</em></h1><p>A considered workspace for grounded answers, order context, and human-reviewed actions.</p><div className="login-art-line"><span />Evidence first. People in control.</div></div></div>
    <div className="login-form-area"><form className="login-card" onSubmit={(event) => { event.preventDefault(); login.mutate() }}><p className="eyebrow">WELCOME BACK</p><h2>Sign in to your workspace</h2><p className="login-intro">Use the demo credentials in <code>docs/HANDOVER.md</code> for a local walkthrough.</p><label className="field-label" htmlFor="login-email">Email address</label><input id="login-email" type="email" autoComplete="username" placeholder="you@northstar.example.com" value={email} onChange={(event) => setEmail(event.target.value)} required /><label className="field-label" htmlFor="login-password">Password</label><input id="login-password" type="password" autoComplete="current-password" placeholder="Enter your password" value={password} onChange={(event) => setPassword(event.target.value)} required />{login.isError && <div className="form-error" role="alert">{login.error.message}</div>}<button className="btn btn-primary login-submit" type="submit" disabled={login.isPending}>{login.isPending ? 'Signing in…' : 'Sign in to SupportPilot'} <span>→</span></button><div className="login-footnote"><WifiOff size={15} /> Your credentials stay in the local installation.</div></form></div>
  </div>
}
