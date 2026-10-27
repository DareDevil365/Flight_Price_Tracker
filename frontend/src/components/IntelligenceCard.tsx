import type { BrainReport } from '../types';

export default function IntelligenceCard({report}:{report:BrainReport|null|undefined}) {
  if (!report) return <p>Collecting comparable fares and market context.</p>;
  return <div>
    <h3>{report.signal.replaceAll('_',' ')}</h3>
    <p>{report.reasoning}</p>
    {Object.entries(report.source_problems || {}).map(([site,problem])=><p key={site}><strong>{site}:</strong> {problem}</p>)}
    {!!report.partial_results?.length && <details><summary>What the sources returned</summary>{report.partial_results.map((r,i)=><p key={i}>{r.platform} · {r.airline} {r.departure_time} · ₹{r.price.toLocaleString('en-IN')} listed · {r.integrity?.status || 'Unchecked'} {r.integrity?.reasons?.join(' ')}</p>)}</details>}
    <div style={{margin:'12px 0'}}><strong>Prediction certainty: {report.certainty.percent==null?'Not calibrated':report.certainty.percent+'% historical accuracy'}</strong>
      {report.certainty.percent!=null && <progress max={100} value={report.certainty.percent} style={{display:'block',width:'100%'}}/>}
      <p>{report.certainty.sample_count} independent seven-day outcomes{report.certainty.range ? ' · range '+report.certainty.range[0]+'–'+report.certainty.range[1]+'%' : ''}. {report.certainty.explanation}</p>
    </div>
    {report.wait_until && <p>Recheck by {report.wait_until}. This is conditional advice; availability can change.</p>}
    <p>{report.forecast.observed_days} distinct fare observation days · Model: {report.forecast.status.replaceAll('_',' ')}</p>
    {report.forecast.readiness && <details><summary>What our forecast still needs</summary>
      <p>{report.forecast.readiness.training_days_remaining} more accepted observation days to reach the initial training requirement; {report.forecast.readiness.weekly_outcomes_observed} completed independent weekly outcomes.</p>
      <p>{report.forecast.readiness.weekly_outcomes_remaining_for_forecast} weekly outcomes still needed for the forecast evidence gate, and {report.forecast.readiness.weekly_outcomes_remaining_for_certainty} for a measured certainty percentage. The model must also outperform simply reusing the last observed price.</p>
      {report.forecast.readiness.minimum_additional_daily_observations_for_forecast!=null && <p>With successful comparable daily collection, the forecast evidence minimum needs at least {report.forecast.readiness.minimum_additional_daily_observations_for_forecast} further observation days. This is an evidence milestone; a usable forecast is not guaranteed.</p>}
      {report.forecast.readiness.blockers.map((b,i)=><p key={i}>{b}</p>)}
      <p>Save this trip in Red Room to collect real observations while the app runs. For trips too close to gather sufficient history, compare current fares, nearby dates and Google’s separate price guidance.</p>
      <p>{report.forecast.readiness.assumptions.join(' ')}</p>
    </details>}
    {report.forecast.forecast_7d!=null && <p>Exploratory seven-day estimate: ₹{report.forecast.forecast_7d.toLocaleString('en-IN')} · low confidence. Recent holdout error ₹{report.forecast.model_mae?.toLocaleString('en-IN')}, last-price baseline ₹{report.forecast.baseline_mae?.toLocaleString('en-IN')}.</p>}
    <details><summary>Evidence, news and missing data</summary>
      {report.context_problems?.map((problem,i)=><p key={i} role="alert">{problem}</p>)}
      {report.feed_status?.data && typeof report.feed_status.data==='object' && Object.entries(report.feed_status.data).map(([name,status])=>typeof status==='string' && <p key={name}><strong>{name.replaceAll('_',' ')}:</strong> {status}</p>)}
      {report.factors.map((f,i)=><div key={i} style={{margin:'12px 0'}}><strong>{f.title}</strong>
        {f.value!=null && <p>{f.value.toLocaleString('en-IN')} {f.units} · {f.as_of}{f.stale?' · stale':''}{f.change_30d_pct!=null ? ' · 30-day change '+f.change_30d_pct+'%' : ''}</p>}
        {f.previous_year_value!=null && <p>Same month last year: {f.previous_year_value.toLocaleString('en-IN')}{f.change_yoy_pct!=null ? ' · change '+f.change_yoy_pct+'%' : ' · percentage comparison unavailable'}.</p>}
        {f.change_yoy_pp!=null && <p>Same-month load factor change: {f.change_yoy_pp} percentage points. This is carrier-wide utilisation.</p>}
        <p>{f.interpretation}</p>{f.source_url && <a href={f.source_url} target="_blank" rel="noopener noreferrer">Data source</a>}</div>)}
      {report.news.map(n=><p key={n.url}><a href={n.url} target="_blank" rel="noopener noreferrer">{n.title}</a><br/>{new Date(n.published_at).toLocaleDateString()} · {n.primary_source?'Primary source':'Reported headline; read and verify the source'}</p>)}
      {report.upcoming_offers.map(o=><p key={o.platform+o.code}><a href={o.source_url} target="_blank" rel="noopener noreferrer">{o.platform}: {o.code} starts {o.valid_from}</a> · Savings need actual checkout testing.</p>)}
      <p>Still missing: {report.missing_parameters.join('; ')}.</p>
    </details>
    <p style={{fontSize:12}}>Assessed {new Date(report.updated_at).toLocaleString()}. Fuel and headlines are context; they do not establish a future fare.</p>
  </div>;
}
