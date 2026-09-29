import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Check, CircleHelp, Database, Globe2, Plug, RefreshCcw, ShieldCheck } from 'lucide-react'
import { api, type Connector } from '../../lib/api'
import { EmptyState, LoadingState, PageHeading, QueryBlock, StatusPill } from '../../components/ui'
import { titleCase } from '../../lib/format'

function connectorIcon(name: string) {
  if (name.toLowerCase().includes('shopify')) return <Globe2 size={23} />
  if (name.toLowerCase().includes('zendesk')) return <CircleHelp size={23} />
  return <Database size={23} />
}

export function ConnectorsView() {
  const connectors = useQuery({ queryKey: ['connectors'], queryFn: api.connectors, refetchInterval: 30_000 })
  return <div className="content-page"><PageHeading eyebrow="INTEGRATION HEALTH" title="Connected, with clarity." description="See exactly which commerce and support adapters are active in this installation." action={<button className="btn btn-secondary" type="button" onClick={() => void connectors.refetch()}><RefreshCcw size={16} /> Refresh status</button>} /><div className="connector-intro"><Plug size={19} /><p>Local simulators exercise the full workflow in demo mode. Live credentials and destinations are configured on the server, never in this browser.</p></div><QueryBlock title="Could not load connector status" error={connectors.error} retry={() => void connectors.refetch()}>{connectors.isPending ? <LoadingState label="Checking connectors…" /> : !connectors.data?.items.length ? <EmptyState icon={<Plug size={21} />} title="No connectors reported" description="Check the API configuration and refresh this page." /> : <div className="connector-grid">{connectors.data.items.map((connector: Connector) => <article className="connector-card" key={connector.name}><div className="connector-card-top"><span className="connector-icon">{connectorIcon(connector.name)}</span><StatusPill value={connector.status} /></div><p className="eyebrow">{titleCase(connector.mode)} ADAPTER</p><h2>{connector.name}</h2><p>{connector.detail || 'The API did not provide additional connector details.'}</p><div className="connector-card-bottom"><span><Check size={14} /> Server managed</span><span>{titleCase(connector.mode)} <ArrowRight size={14} /></span></div></article>)}</div>}</QueryBlock><div className="connector-security"><ShieldCheck size={19} /><span>Connection status reflects the API response. Live adapter verification requires customer credentials and is documented separately.</span></div></div>
}
