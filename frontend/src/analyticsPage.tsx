import {useEffect,useState} from "react";
import {Activity} from "lucide-react";

const API=(import.meta as any).env?.VITE_API_URL||"http://localhost:8000/api";
function authHeader():Record<string,string>{const u=JSON.parse(localStorage.getItem("pi-user")||"null");return u?.token?{Authorization:"Bearer "+u.token}:{}}

const TABS=["Overview","AI Analytics","Imaging Analytics","Findings","Performance","Audit"] as const;
type Tab=typeof TABS[number];

function Bars({items,labelKey="label",valueKey="count"}:{items:any[];labelKey?:string;valueKey?:string}){
  if(!items||!items.length)return <p className="muted">No data yet.</p>;
  const max=Math.max(...items.map(i=>Number(i[valueKey])||0),1);
  return <div className="bar-chart">{items.map((i,idx)=><div className="bar-chart-row" key={idx}>
    <span className="bar-chart-label">{String(i[labelKey])}</span>
    <div className="bar"><i style={{width:((Number(i[valueKey])||0)/max*100)+"%"}}/></div>
    <b className="bar-chart-value">{i[valueKey]}</b>
  </div>)}</div>;
}

function Section({title,children}:{title:string;children:any}){
  return <div className="detail-card"><h3>{title}</h3>{children}</div>;
}

function Overview(){
  const[d,setD]=useState<any>(null);
  useEffect(()=>{fetch(API+"/analytics/overview").then(r=>r.json()).then(setD).catch(()=>{})},[]);
  if(!d)return <p className="muted">Loading…</p>;
  return <>
    <div className="metric-grid">
      {[["Total Studies",d.total_studies],["Processed Today",d.studies_processed_today],["AI Analyses Completed",d.ai_analyses_completed],
        ["Pending Analyses",d.pending_analyses],["Findings Detected",d.findings_detected],
        ["Avg Processing Time",d.average_processing_time_seconds!=null?d.average_processing_time_seconds+"s":"Not available"]]
        .map(x=><div className="metric" key={x[0] as string}><span>{x[0]}</span><strong>{x[1]}</strong></div>)}
    </div>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginTop:14}}>
      <Section title="Studies by Modality"><Bars items={d.studies_by_modality}/></Section>
      <Section title="Studies by Anatomy"><Bars items={d.studies_by_anatomy}/></Section>
      <Section title="AI Pipeline Utilization"><Bars items={d.ai_pipeline_utilization} labelKey="pipeline_id"/></Section>
      <Section title="Studies Over Time"><Bars items={d.studies_over_time} labelKey="date"/></Section>
    </div>
    <Section title="Recent Activity"><div className="audit-list">{d.recent_activity.length?d.recent_activity.map((a:any,i:number)=><div className="audit-row" key={i}><Activity size={16}/><div><b>{a.action.replaceAll("_"," ")}</b><p>{a.detail}</p></div><small>{new Date(a.created_at).toLocaleString()}</small></div>):<p className="muted">No activity yet.</p>}</div></Section>
  </>;
}

function AIAnalytics(){
  const[d,setD]=useState<any>(null);
  useEffect(()=>{fetch(API+"/analytics/ai").then(r=>r.json()).then(setD).catch(()=>{})},[]);
  if(!d)return <p className="muted">Loading…</p>;
  return <>
    <div className="metric-grid" style={{gridTemplateColumns:"repeat(3,1fr)"}}>
      <div className="metric"><span>Average Inference Time</span><strong>{d.average_inference_time_seconds!=null?d.average_inference_time_seconds+"s":"Not available"}</strong></div>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginTop:14}}>
      <Section title="Analyses by Pipeline">
        <div className="table-wrap"><table><thead><tr><th>Pipeline</th><th>Total</th><th>Succeeded</th><th>Failed</th></tr></thead>
          <tbody>{d.analyses_by_pipeline.length?d.analyses_by_pipeline.map((p:any)=><tr key={p.pipeline_id}><td>{p.pipeline_id}</td><td>{p.total}</td><td>{p.succeeded}</td><td>{p.failed}</td></tr>):<tr><td colSpan={4}>No AI analyses run yet.</td></tr>}</tbody>
        </table></div>
      </Section>
      <Section title="Model Usage"><Bars items={d.model_usage} labelKey="model_name"/></Section>
      <Section title="Findings by Pipeline"><Bars items={d.findings_by_pipeline} labelKey="pipeline_id" valueKey="findings"/></Section>
      <Section title="Confidence Distribution"><Bars items={d.confidence_distribution} labelKey="bucket"/></Section>
    </div>
    <Section title="Recent AI Jobs">
      <div className="table-wrap"><table><thead><tr><th>Study</th><th>Pipeline</th><th>Model</th><th>Status</th><th>Findings</th><th>Duration</th><th>When</th></tr></thead>
        <tbody>{d.recent_ai_jobs.length?d.recent_ai_jobs.map((j:any)=><tr key={j.id}><td>{j.study_id}</td><td>{j.pipeline_id}</td><td>{j.model_name||"—"}</td><td><span className="status">{j.status}</span></td><td>{j.nodule_count??"—"}</td><td>{j.duration_seconds!=null?j.duration_seconds+"s":"—"}</td><td><small>{new Date(j.created_at).toLocaleString()}</small></td></tr>):<tr><td colSpan={7}>No AI jobs recorded yet.</td></tr>}</tbody>
      </table></div>
    </Section>
  </>;
}

function ImagingAnalytics(){
  const[d,setD]=useState<any>(null);
  useEffect(()=>{fetch(API+"/analytics/imaging").then(r=>r.json()).then(setD).catch(()=>{})},[]);
  if(!d)return <p className="muted">Loading…</p>;
  return <>
    <div className="metric-grid" style={{gridTemplateColumns:"repeat(2,1fr)"}}>
      <div className="metric"><span>Distinct Series</span><strong>{d.distinct_series_count}</strong></div>
      <div className="metric"><span>Total Images / Slices</span><strong>{d.total_images_slices}</strong></div>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginTop:14}}>
      <Section title="Studies by Modality"><Bars items={d.studies_by_modality}/></Section>
      <Section title="Studies by Anatomy"><Bars items={d.studies_by_anatomy}/></Section>
      <Section title="Study Volume Over Time"><Bars items={d.study_volume_over_time} labelKey="date"/></Section>
      <Section title="Study Status"><Bars items={d.study_status}/></Section>
    </div>
  </>;
}

function Findings(){
  const[d,setD]=useState<any>(null);
  const[filters,setFilters]=useState<any>({});
  function load(){const p=new URLSearchParams(Object.entries(filters).filter(([,v])=>v));fetch(API+"/analytics/findings?"+p.toString()).then(r=>r.json()).then(setD).catch(()=>{})}
  useEffect(()=>{load()},[]);
  if(!d)return <p className="muted">Loading…</p>;
  return <>
    <div className="toolbar">
      <input className="filter" placeholder="Modality" onChange={e=>setFilters({...filters,modality:e.target.value})}/>
      <input className="filter" placeholder="Anatomy" onChange={e=>setFilters({...filters,anatomy:e.target.value})}/>
      <input className="filter" placeholder="Pipeline id" onChange={e=>setFilters({...filters,pipeline:e.target.value})}/>
      <button className="secondary" onClick={load}>Apply filters</button>
    </div>
    <div className="metric-grid" style={{gridTemplateColumns:"repeat(1,1fr)",maxWidth:220}}>
      <div className="metric"><span>Total Findings</span><strong>{d.total_findings}</strong></div>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginTop:14}}>
      <Section title="Findings by Type"><Bars items={d.findings_by_type}/></Section>
      <Section title="Findings by Anatomy"><Bars items={d.findings_by_anatomy}/></Section>
      <Section title="Findings by Pipeline"><Bars items={d.findings_by_pipeline}/></Section>
      <Section title="Findings Over Time"><Bars items={d.findings_over_time} labelKey="date"/></Section>
    </div>
    <Section title="Recent Findings">
      <div className="table-wrap"><table><thead><tr><th>Study</th><th>Type</th><th>Anatomy</th><th>Modality</th><th>Pipeline</th><th>Confidence</th><th>When</th></tr></thead>
        <tbody>{d.recent_findings.length?d.recent_findings.map((f:any,i:number)=><tr key={i}><td>{f.study_id}</td><td>{f.type}</td><td>{f.anatomy}</td><td>{f.modality}</td><td>{f.pipeline_id}</td><td>{f.confidence!=null?Math.round(f.confidence*100)+"%":"—"}</td><td><small>{new Date(f.created_at).toLocaleString()}</small></td></tr>):<tr><td colSpan={7}>No findings recorded yet.</td></tr>}</tbody>
      </table></div>
    </Section>
  </>;
}

function Performance(){
  const[d,setD]=useState<any>(null);
  useEffect(()=>{fetch(API+"/analytics/performance").then(r=>r.json()).then(setD).catch(()=>{})},[]);
  if(!d)return <p className="muted">Loading…</p>;
  return <>
    <div className="metric-grid" style={{gridTemplateColumns:"repeat(4,1fr)"}}>
      <div className="metric"><span>Successful Jobs</span><strong>{d.successful_jobs}</strong></div>
      <div className="metric"><span>Failed Jobs</span><strong>{d.failed_jobs}</strong></div>
      <div className="metric"><span>Pending Jobs</span><strong>{d.pending_jobs}</strong></div>
      <div className="metric"><span>Avg Processing Time</span><strong>{d.average_processing_time_seconds!=null?d.average_processing_time_seconds+"s":"Not available"}</strong></div>
    </div>
    <div style={{marginTop:14}}><Section title="Throughput by Day"><Bars items={d.throughput_by_day} labelKey="date"/></Section></div>
    <Section title="Recent Processing Events">
      <div className="table-wrap"><table><thead><tr><th>Study</th><th>Pipeline</th><th>Status</th><th>Duration</th><th>When</th></tr></thead>
        <tbody>{d.recent_processing_events.length?d.recent_processing_events.map((e:any)=><tr key={e.id}><td>{e.study_id}</td><td>{e.pipeline_id}</td><td><span className="status">{e.status}</span></td><td>{e.duration_seconds!=null?e.duration_seconds+"s":"—"}</td><td><small>{new Date(e.created_at).toLocaleString()}</small></td></tr>):<tr><td colSpan={5}>No processing events recorded yet.</td></tr>}</tbody>
      </table></div>
    </Section>
    <p className="muted" style={{marginTop:14}}>This page reports processing/AI-job metrics actually collected by the application. It does not report Kubernetes or cloud infrastructure telemetry, which this deployment does not currently collect.</p>
  </>;
}

function AuditAnalytics(){
  const[d,setD]=useState<any>(null);
  const[err,setErr]=useState("");
  useEffect(()=>{fetch(API+"/analytics/audit",{headers:authHeader()}).then(async r=>{if(!r.ok){setErr((await r.json()).detail||"Not authorized.");return}setD(await r.json())}).catch(()=>setErr("Could not reach the audit service."))},[]);
  if(err)return <p className="error">{err}</p>;
  if(!d)return <p className="muted">Loading…</p>;
  return <>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Section title="Events by Type"><Bars items={d.events_by_type} labelKey="action"/></Section>
      <Section title="Recent AI Inference Events">
        <div className="audit-list">{d.ai_inference_events.length?d.ai_inference_events.map((a:any)=><div className="audit-row" key={a.id}><Activity size={16}/><div><b>{a.action.replaceAll("_"," ")}</b><p>{a.detail}</p></div><small>{new Date(a.created_at).toLocaleString()}</small></div>):<p className="muted">No AI inference events yet.</p>}</div>
      </Section>
    </div>
    <Section title="Recent Audit Events"><div className="audit-list">{d.recent_events.map((a:any)=><div className="audit-row" key={a.id}><Activity size={16}/><div><b>{a.action.replaceAll("_"," ")}</b><p>{a.detail}</p></div><small>{new Date(a.created_at).toLocaleString()}</small></div>)}</div></Section>
  </>;
}

export default function Analytics({role}:{role:string}){
  const[tab,setTab]=useState<Tab>("Overview");
  const visibleTabs=TABS.filter(t=>t!=="Audit"||role==="admin");
  return <>
    <div className="page-heading"><div><p className="eyebrow">ANALYTICS</p><h1>Analytics</h1><p className="muted">Real platform statistics derived from studies, AI analyses, and audit events in this application.</p></div></div>
    <div className="tabs">{visibleTabs.map(t=><button key={t} className={"tab "+(tab===t?"active":"")} onClick={()=>setTab(t)}>{t}</button>)}</div>
    <div style={{marginTop:18}}>
      {tab==="Overview"&&<Overview/>}
      {tab==="AI Analytics"&&<AIAnalytics/>}
      {tab==="Imaging Analytics"&&<ImagingAnalytics/>}
      {tab==="Findings"&&<Findings/>}
      {tab==="Performance"&&<Performance/>}
      {tab==="Audit"&&role==="admin"&&<AuditAnalytics/>}
    </div>
  </>;
}
