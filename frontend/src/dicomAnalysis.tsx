import {useEffect,useState} from "react";
import {ScanSearch,Info} from "lucide-react";

const API=(import.meta as any).env?.VITE_API_URL||"http://localhost:8000/api";

type StudyLite={id:string;modality:string;body_region:string;patient_label:string};
type SeriesRow={study_id:string;series_name:string;modality:string;slice_count:number;dimensions:string;slice_thickness:string;series_description:string;processing_status:string;is_current:boolean};
type Pipeline={pipeline_id:string;display_name:string;anatomy:string;modalities:string[];model_name:string;model_version?:string;available:boolean;can_run_inference:boolean;status_reason:string;inference_capability:string;description:string};
type DicomAnalysisPayload={
  study_id:string;
  study_profile:{patient_study?:Record<string,string>;imaging?:Record<string,any>;error?:string};
  acquisition_parameters:{modality:string;parameters:Record<string,string>;note?:string};
  series_explorer:SeriesRow[];
  image_quality:Record<string,any>;
  ai_readiness:{detected_modality:string;detected_anatomy:string;compatible_pipelines:Pipeline[];recommended_pipeline:string|null;reason:string};
};

function KV({label,value}:{label:string;value:any}){
  return <div className="detail-line"><span>{label.replaceAll("_"," ")}</span><b>{value===null||value===undefined||value===""?"Not available":String(value)}</b></div>;
}

function QualityBadge({value}:{value:string}){
  const ok=/^(consistent|ready|single series)/i.test(value||"");
  const bad=/inconsistent|not ready|missing/i.test(value||"");
  return <span className={"status "+(ok?"":bad?"":"")}>{value}</span>;
}

export default function DicomAnalysis({initialStudyId,openViewer}:{initialStudyId?:string;openViewer?:(id:string)=>void}){
  const[studies,setStudies]=useState<StudyLite[]>([]);
  const[selected,setSelected]=useState(initialStudyId||"");
  const[data,setData]=useState<DicomAnalysisPayload|null>(null);
  const[err,setErr]=useState("");
  const[loading,setLoading]=useState(false);

  useEffect(()=>{fetch(API+"/studies").then(r=>r.json()).then((rows:StudyLite[])=>{setStudies(rows);if(!selected&&rows.length)setSelected(rows[0].id)}).catch(()=>{})},[]);

  useEffect(()=>{
    if(!selected)return;
    setLoading(true);setErr("");
    fetch(API+"/studies/"+selected+"/dicom-analysis").then(async r=>{
      if(!r.ok){setErr("Could not load DICOM analysis for this study.");setLoading(false);return}
      setData(await r.json());setLoading(false);
    }).catch(()=>{setErr("Could not reach the DICOM analysis service.");setLoading(false)});
  },[selected]);

  return <>
    <div className="page-heading"><div><p className="eyebrow">DICOM INTELLIGENCE</p><h1>DICOM Analysis</h1><p className="muted">Study profile, acquisition parameters, series explorer, image quality, and AI readiness — computed from the actual uploaded DICOM files.</p></div>
      <select className="filter" value={selected} onChange={e=>setSelected(e.target.value)}>
        {!studies.length&&<option value="">No studies uploaded yet</option>}
        {studies.map(s=><option key={s.id} value={s.id}>{s.id} · {s.modality||"—"} · {s.body_region||"—"}</option>)}
      </select>
    </div>

    {err&&<p className="error">{err}</p>}
    {loading&&<p className="muted">Loading DICOM analysis…</p>}

    {data&&!loading&&<div className="detail-panel" style={{display:"grid",gap:14}}>

      <div className="detail-card">
        <h3>Study Profile</h3>
        {data.study_profile.error?<p className="error">{data.study_profile.error}</p>:<>
          <div className="quality-grid">
            {Object.entries(data.study_profile.patient_study||{}).map(([k,v])=><KV key={k} label={k} value={v}/>)}
          </div>
          <h4 className="subhead">Imaging</h4>
          <div className="quality-grid">
            {Object.entries(data.study_profile.imaging||{}).map(([k,v])=><KV key={k} label={k} value={v}/>)}
          </div>
        </>}
      </div>

      <div className="detail-card">
        <div className="card-title"><h3>Acquisition Parameters</h3><span className="analysis-badge">{data.acquisition_parameters.modality}</span></div>
        {data.acquisition_parameters.note&&<p className="muted">{data.acquisition_parameters.note}</p>}
        {Object.keys(data.acquisition_parameters.parameters||{}).length>0?
          <div className="quality-grid">{Object.entries(data.acquisition_parameters.parameters).map(([k,v])=><KV key={k} label={k} value={v}/>)}</div>
          :<p className="muted">No modality-specific parameters available for this study.</p>}
      </div>

      <div className="detail-card">
        <h3>Series Explorer</h3>
        <div className="table-wrap"><table><thead><tr><th>Series</th><th>Modality</th><th>Slices</th><th>Dimensions</th><th>Thickness</th><th>Description</th><th>Status</th></tr></thead>
          <tbody>{data.series_explorer.map(s=><tr key={s.study_id} onClick={()=>openViewer&&openViewer(s.study_id)} style={s.is_current?{background:"var(--soft)"}:{}}>
            <td><b>{s.study_id}</b>{s.is_current&&<small> · current</small>}</td>
            <td>{s.modality}</td><td>{s.slice_count}</td><td>{s.dimensions}</td><td>{s.slice_thickness}</td><td>{s.series_description}</td>
            <td><span className="status">{s.processing_status}</span></td>
          </tr>)}</tbody>
        </table></div>
      </div>

      <div className="detail-card">
        <h3>Image Quality</h3>
        <div className="quality-grid">
          {Object.entries(data.image_quality).filter(([k])=>k!=="missing_critical_tags").map(([k,v])=><KV key={k} label={k} value={v}/>)}
        </div>
        {data.image_quality.missing_critical_tags && data.image_quality.missing_critical_tags[0]!=="None" &&
          <div className="flags">{data.image_quality.missing_critical_tags.map((t:string)=><p key={t}>⚠ Missing: {t}</p>)}</div>}
      </div>

      <div className="detail-card">
        <div className="card-title"><h3>AI Readiness</h3><ScanSearch size={16}/></div>
        <div className="detail-line"><span>Detected modality</span><b>{data.ai_readiness.detected_modality}</b></div>
        <div className="detail-line"><span>Detected anatomy</span><b>{data.ai_readiness.detected_anatomy}</b></div>
        <p className="muted" style={{marginTop:10}}>{data.ai_readiness.reason}</p>
        {data.ai_readiness.compatible_pipelines.length===0&&<div className="triage-unavailable"><Info size={15}/><span><b>No compatible pipeline</b>No AI pipeline is registered for this modality/anatomy combination.</span></div>}
        <div style={{display:"grid",gap:10,marginTop:14}}>
          {data.ai_readiness.compatible_pipelines.map(p=>
            <div className="pipeline-card" key={p.pipeline_id}>
              <div className="card-title"><b>{p.display_name}</b><span className={"status "+(p.can_run_inference?"":"off")}>{p.can_run_inference?"Model Available":"Model Not Available"}</span></div>
              <p className="muted">{p.description}</p>
              <small>{p.anatomy} · {p.modalities.join(", ")} · {p.inference_capability}</small>
              {!p.can_run_inference&&<p className="error" style={{marginTop:8}}>{p.status_reason}</p>}
              {data.ai_readiness.recommended_pipeline===p.pipeline_id&&<span className="analysis-badge" style={{marginTop:8,display:"inline-block"}}>RECOMMENDED</span>}
            </div>
          )}
        </div>
      </div>
    </div>}
  </>;
}
