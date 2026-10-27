import { useEffect } from 'react';
import { useResultStore } from '../store';
import type { SearchResult, SocketSend } from '../types';

const money = (value:number) => '₹'+value.toLocaleString('en-IN',{maximumFractionDigits:2});

export default function GoogleBookingContext({result,sendMessage}:{result:SearchResult;sendMessage:SocketSend}) {
  const report=useResultStore(s=>s.googleBooking[result.id]);
  const handoff=useResultStore(s=>report?.sessionId ? s.handoffStatus[report.sessionId] : undefined);
  useEffect(()=>{
    if (report?.status!=='loading') return;
    const timer=setTimeout(()=>{
      const current=useResultStore.getState().googleBooking[result.id];
      if (current?.status==='loading') useResultStore.getState().setGoogleBooking({...current,status:'unavailable',message:'Google guidance could not be read in time. Retry or open Google manually.'});
    },85000);
    return()=>clearTimeout(timer);
  },[report?.status,result.id]);
  const check=()=>{
    useResultStore.getState().setGoogleBooking({searchId:result.search_id,resultId:result.id,status:'loading'});
    sendMessage('search:booking-context:get',{searchId:result.search_id,resultId:result.id});
  };
  return <div style={{marginTop:12,textAlign:'left'}}>
    <button className="btn btn-secondary" style={{whiteSpace:'normal',maxWidth:'100%'}} disabled={report?.status==='loading' || result.savings_breakdown?.integrity?.status==='flagged'} onClick={check}>
      {report?.status==='loading'?'Checking Google...':'Google price guidance & booking options'}
    </button>
    {report?.status==='unavailable' && <p role="alert">{report.message} Your listed fare and model certainty have not changed.</p>}
    {report?.status==='available' && <div style={{maxWidth:460}}>
      {report.scope && <p>{report.scope.origin} → {report.scope.destination} · {report.scope.departure_date} · {report.scope.departure_time} · {report.scope.passenger_count} adult(s)</p>}
      {report.insight ? <p>Google rates {money(report.insight.quoted_price)} as <strong>{report.insight.classification}</strong>.
        {report.insight.typical_low!=null && report.insight.typical_high!=null && <> Similar trips usually cost {money(report.insight.typical_low)}–{money(report.insight.typical_high)}.</>}
        {' '}This is Google’s comparison, with no measured prediction certainty available to this app.</p> : <p>Google did not provide readable price guidance for this itinerary.</p>}
      {report.booking_options?.map((option,i)=><p key={i}><strong>{option.merchant}: {money(option.listed_total)}</strong>
        {option.included_convenience_fee!=null ? <> · includes {money(option.included_convenience_fee)} convenience fee</> : <> · {option.fee_note}</>}
        {' '}Listed partner offer; final payment total unverified.</p>)}
      {!report.booking_options?.length && <p>No supported INR partner options could be read. Their fees are unknown.</p>}
      <p>{report.limitation}</p>
      {report.observed_at && <p>Observed {new Date(report.observed_at).toLocaleString()}.</p>}
      {report.sessionId && <button className="btn btn-secondary" style={{whiteSpace:'normal',maxWidth:'100%'}} disabled={handoff==='pending'} onClick={()=>{
        useResultStore.getState().setHandoffStatus(report.sessionId!,'pending');
        sendMessage('session:handoff',{sessionId:report.sessionId});
      }}>Open selected Google itinerary</button>}
      {handoff==='failed' && <p>This browser session expired or could not open. Check Google again.</p>}
      {report.source_url && <a href={report.source_url} target="_blank" rel="noopener noreferrer" style={{marginLeft:10}}>Open exact Google search</a>}
    </div>}
  </div>;
}
