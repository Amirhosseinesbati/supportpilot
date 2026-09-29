import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BookOpenText, Clock3, FlaskConical, RefreshCcw, ShieldCheck } from 'lucide-react'
import { api, type EvaluationRatio, type EvaluationRun } from '../../lib/api'
import { titleCase } from '../../lib/format'
import { EmptyState, LoadingState, PageHeading, QueryBlock, StatusPill } from '../../components/ui'

const measuredMetrics = [
  { key: 'grounded_structured_claim_exact_match', label: 'Grounded claim exact match' },
  { key: 'citation_precision_on_emitted_ids', label: 'Citation ID precision' },
  { key: 'action_match', label: 'Expected action match' },
  { key: 'missing_evidence_clarify_or_abstain', label: 'Clarify or abstain when evidence is missing' },
  { key: 'security_denial_no_forbidden_fragment', label: 'Security denial checks' },
  { key: 'tool_success', label: 'Tool success' },
] as const

function ratioText(ratio: EvaluationRatio | undefined): string {
  return typeof ratio?.rate === 'number' ? `${(ratio.rate * 100).toFixed(1)}%` : '—'
}

function MeasuredRun({ run }: { run: EvaluationRun }) {
  const heldOut = run.split_results?.held_out
  const development = run.split_results?.development
  return <>
    <div className="section-heading"><div><p className="eyebrow">LATEST MODEL ASSESSMENT</p><h2>Measured DEMO fixture run</h2></div><StatusPill value={run.status || 'unknown'} /></div>
    <p className="evaluation-section-copy">Structured predictions against synthetic scenarios. The held-out split is shown below; exact field matches are a proxy for answer quality.</p>
    <div className="run-summary">
      <div><span>Predictions</span><strong>{run.total_predictions ?? '—'}</strong></div>
      <div><span>Held-out cases</span><strong>{heldOut?.coverage?.denominator ?? '—'}</strong></div>
      <div><span>Development cases</span><strong>{development?.coverage?.denominator ?? '—'}</strong></div>
      <div><span>Coverage, held out</span><strong>{ratioText(heldOut?.coverage)}</strong></div>
    </div>
    {heldOut ? <div className="metrics-grid">{measuredMetrics.map(({ key, label }) => {
      const ratio = heldOut[key] as EvaluationRatio | undefined
      return <div className="metric-card" key={key}><p className="eyebrow">{label}</p><strong>{ratioText(ratio)}</strong><small>{ratio?.numerator != null && ratio?.denominator != null ? `${ratio.numerator} of ${ratio.denominator} held-out cases` : 'No measured value'}</small></div>
    })}</div> : <EmptyState icon={<FlaskConical size={21} />} title="No held-out scores in this run" description="The latest model assessment does not include held-out ratios." />}
    <div className="evaluation-caveat"><ShieldCheck size={19} /><div><strong>Release targets {run.release_targets_verified ? 'verified' : 'not verified'} · Human review {run.human_review_completed ? 'complete' : 'pending'}</strong><p>{run.limitation || 'These synthetic results need sampled human review before they can support a production quality claim.'}</p></div></div>
  </>
}

function FixtureValidation({ run }: { run: EvaluationRun }) {
  return <><div className="section-heading"><div><p className="eyebrow">LATEST VALIDATION</p><h2>Fixture integrity check</h2></div><StatusPill value={run.status || 'unknown'} /></div><div className="run-summary"><div><span>Conversations</span><strong>{run.counts?.conversations ?? '—'}</strong></div><div><span>Documents</span><strong>{run.counts?.documents ?? '—'}</strong></div><div><span>Orders</span><strong>{run.counts?.orders ?? '—'}</strong></div><div><span>Proposals</span><strong>{run.counts?.proposals ?? '—'}</strong></div></div><div className="evaluation-caveat"><FlaskConical size={19} /><div><strong>Dataset integrity only</strong><p>This check validates synthetic fixture counts and files. It does not measure model quality.</p></div></div></>
}

export function EvaluationsView() {
  const summary = useQuery({ queryKey: ['evaluations'], queryFn: api.evaluations, refetchInterval: 60_000 })
  const run = summary.data?.latest_run
  return <div className="content-page"><PageHeading eyebrow="QUALITY & EVIDENCE" title="Measure what matters." description="Synthetic evaluation results are labeled by what was actually measured." action={<button className="btn btn-secondary" type="button" onClick={() => void summary.refetch()}><RefreshCcw size={16} /> Refresh results</button>} /><QueryBlock title="Could not load evaluation summary" error={summary.error} retry={() => void summary.refetch()}>{summary.isPending ? <LoadingState label="Loading evaluation results…" /> : <><div className="evaluation-hero"><div><p className="eyebrow">EVALUATION DATASET</p><strong>{summary.data?.dataset_count ?? '—'}</strong><span>scenarios configured</span></div><div className="evaluation-hero-graphic"><span /><span /><span /><span /><span /><span /><span /><span /></div></div>{run?.kind === 'structured_prediction_assessment' ? <MeasuredRun run={run} /> : run?.kind === 'fixture_integrity_only' ? <FixtureValidation run={run} /> : run ? <div className="evaluation-caveat"><FlaskConical size={19} /><div><strong>{titleCase(run.kind || 'Unclassified run')}</strong><p>This result has no supported performance fields to display.</p></div></div> : <EmptyState icon={<FlaskConical size={22} />} title="No evaluation run recorded" description="Run the included evaluation suite to populate measured results here." />}</>}</QueryBlock><div className="evaluation-principles"><div><BookOpenText size={20} /><h3>Grounding</h3><p>Assess supported claims and precision of cited passages.</p></div><div><ShieldCheck size={20} /><h3>Safety</h3><p>Probe identity boundaries, policy dates, and action authorization.</p></div><div><Clock3 size={20} /><h3>Reliability</h3><p>Record latency and tool outcomes under a stated environment.</p></div></div><p className="evaluation-footnote"><ArrowRight size={14} /> Synthetic evaluation indicates demo behavior; customer quality requires live review.</p></div>
}
