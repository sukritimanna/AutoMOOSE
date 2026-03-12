import { useState, useEffect, useRef, useMemo } from "react";
import {
  LineChart, Line, ScatterChart, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine
} from "recharts";

const API = "http://localhost:8000";

// ── Palette ───────────────────────────────────────────────────────────────
const C = {
  bg:"#06090f", surface:"#0d1117", card:"#161b22", border:"#21262d",
  border2:"#30363d", text:"#e6edf3", muted:"#7d8590",
  blue:"#58a6ff", green:"#3fb950", red:"#f85149", yellow:"#d29922",
  purple:"#bc8cff", cyan:"#39d353", orange:"#f0883e", pink:"#ff7eb6",
  teal:"#2dd4bf",
};
const STATUS_COLOR = {
  pending:C.yellow, running:C.blue, done:C.green,
  failed:C.red, stopped:C.muted, input_ready:C.purple,
};
const SERIES_COLORS = [C.blue,C.green,C.orange,C.purple,C.cyan,C.pink,C.yellow,C.teal];

// ── Atoms ─────────────────────────────────────────────────────────────────
const Dot = ({status}) => (
  <span style={{display:"inline-block",width:8,height:8,borderRadius:"50%",
    background:STATUS_COLOR[status]||C.muted, marginRight:6, flexShrink:0,
    boxShadow:status==="running"?`0 0 8px ${C.blue}`:"none"}}/>
);
const Card = ({children,style={}}) => (
  <div style={{background:C.card,border:`1px solid ${C.border}`,
    borderRadius:10,padding:18,...style}}>{children}</div>
);
const Btn = ({children,onClick,color=C.blue,disabled=false,style={}}) => (
  <button onClick={onClick} disabled={disabled} style={{
    background:"transparent",
    border:`1px solid ${disabled?C.border2:color}`,
    color:disabled?C.muted:color, borderRadius:7, padding:"7px 16px",
    cursor:disabled?"default":"pointer", fontSize:12, fontWeight:600,
    fontFamily:"inherit", transition:"all .15s",...style}}>
    {children}
  </button>
);
const SHead = ({color=C.blue,children,style={}}) => (
  <div style={{color, fontWeight:700, fontSize:11, marginBottom:10,
    textTransform:"uppercase", letterSpacing:0.7,
    borderBottom:`1px solid ${C.border}`, paddingBottom:6,...style}}>
    {children}
  </div>
);
const Label = ({children}) => (
  <div style={{fontSize:10,color:C.muted,marginBottom:3,
    textTransform:"uppercase",letterSpacing:0.5}}>{children}</div>
);
const Inp = ({label,value,onChange,type="number",step,min,style={}}) => (
  <div style={{marginBottom:10,...style}}>
    <Label>{label}</Label>
    <input type={type} value={value} step={step} min={min}
      onChange={e=>onChange(type==="number"?+e.target.value:e.target.value)}
      style={{width:"100%",background:C.surface,border:`1px solid ${C.border2}`,
        borderRadius:6,padding:"6px 10px",color:C.text,fontSize:12,
        fontFamily:"inherit",outline:"none",boxSizing:"border-box"}}/>
  </div>
);
const Toggle = ({label,value,onChange,color=C.green}) => (
  <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",
    marginBottom:8,cursor:"pointer"}} onClick={()=>onChange(!value)}>
    <span style={{fontSize:11,color:value?C.text:C.muted}}>{label}</span>
    <div style={{width:34,height:18,borderRadius:9,background:value?color:C.border2,
      position:"relative",transition:"background .2s",flexShrink:0}}>
      <div style={{width:14,height:14,borderRadius:7,background:"white",
        position:"absolute",top:2,left:value?18:2,transition:"left .2s"}}/>
    </div>
  </div>
);
const Select = ({label,value,onChange,options}) => (
  <div style={{marginBottom:10}}>
    <Label>{label}</Label>
    <select value={value} onChange={e=>onChange(e.target.value)}
      style={{width:"100%",background:C.surface,border:`1px solid ${C.border2}`,
        borderRadius:6,padding:"6px 10px",color:C.text,fontSize:12,
        fontFamily:"inherit",outline:"none"}}>
      {options.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  </div>
);
const Badge = ({children,color=C.muted}) => (
  <span style={{fontSize:9,padding:"2px 7px",borderRadius:10,
    border:`1px solid ${color}`,color,whiteSpace:"nowrap"}}>{children}</span>
);

// ── Configure Panel ───────────────────────────────────────────────────────
function ConfigurePanel({params,setParams,presets,onGenerate,onRun}){
  const f = k => v => setParams(p=>({...p,[k]:v}));
  const is3d = parseInt(params.dim||2)===3;
  const isLinear = params.formulation==="LinearizedInterface";
  const isRandom = params.ic_type==="Random";

  const autoOpNum = v => {
    const n=+v, rec=is3d?Math.max(12,Math.floor(n/4)):Math.max(8,Math.floor(n/4));
    setParams(p=>({...p,num_grains:n,op_num:Math.min(n,rec)}));
  };
  const setDim = d => {
    const dim=parseInt(d);
    setParams(p=>({...p,dim,
      op_num: dim===3?Math.max(12,p.op_num||8):p.op_num||8,
      exodus_interval: dim===3?Math.max(10,p.exodus_interval||5):p.exodus_interval||5,
      use_adaptivity: dim===3?false:p.use_adaptivity,
    }));
  };

  const mobility = isLinear ? null :
    ((params.GBmob0||2.5e-6)*Math.exp(-(params.Q||0.23)/(8.617e-5*(params.T||450)))).toExponential(2);

  const sect = (color,label,children) => (
    <Card style={{marginBottom:0}}>
      <SHead color={color}>{label}</SHead>
      {children}
    </Card>
  );

  return (
    <div style={{display:"flex",flexDirection:"column",gap:12}}>

      {/* ── Row 1: Identity ── */}
      <Card style={{padding:"12px 18px"}}>
        <div style={{display:"flex",gap:16,flexWrap:"wrap",alignItems:"flex-end"}}>

          {/* Dimension */}
          <div>
            <Label>Dimension</Label>
            <div style={{display:"flex",borderRadius:8,overflow:"hidden",
              border:`1px solid ${C.border2}`}}>
              {[2,3].map(d=>(
                <button key={d} onClick={()=>setDim(d)} style={{
                  padding:"7px 22px",border:"none",fontFamily:"inherit",
                  fontSize:13,fontWeight:600,cursor:"pointer",transition:"all .15s",
                  background:is3d===(d===3)?C.green:"transparent",
                  color:is3d===(d===3)?C.bg:C.muted}}>
                  {d}D
                </button>
              ))}
            </div>
          </div>

          {/* Formulation */}
          <div style={{minWidth:200}}>
            <Select label="Formulation"
              value={params.formulation||"GBEvolution"}
              onChange={f("formulation")}
              options={[
                {value:"GBEvolution",label:"GBEvolution (standard Cu)"},
                {value:"LinearizedInterface",label:"LinearizedInterface (κ/L)"},
              ]}/>
          </div>

          {/* IC Type */}
          <div style={{minWidth:160}}>
            <Select label="Initial Condition"
              value={params.ic_type||"Voronoi"}
              onChange={f("ic_type")}
              options={[
                {value:"Voronoi",label:"Voronoi (seeds)"},
                {value:"Random",label:"Random (discrete)"},
              ]}/>
          </div>

          {/* Run name */}
          <div style={{flex:1,minWidth:180}}>
            <Inp label="Run Name" value={params.run_name||"grain_growth"}
              onChange={f("run_name")} type="text"/>
          </div>

          {is3d&&(
            <div style={{padding:"8px 14px",borderRadius:7,background:"#2d1b00",
              border:`1px solid ${C.yellow}`,fontSize:11,color:C.yellow,maxWidth:360}}>
              ⚠ <strong>3D is much slower.</strong> Keep mesh coarse, use MPI ≥4,
              disable adaptivity, increase Exodus interval.
            </div>
          )}
        </div>
      </Card>

      {/* ── Row 2: 3 columns ── */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12}}>

        {/* Mesh */}
        {sect(C.blue,"🗂 Mesh",<>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
            <Inp label="NX" value={params.nx||40} onChange={f("nx")}/>
            <Inp label="NY" value={params.ny||40} onChange={f("ny")}/>
            {is3d&&<Inp label="NZ" value={params.nz||20} onChange={f("nz")}/>}
            <Inp label="Xmax (nm)" value={params.xmax||1000} onChange={f("xmax")} step={100}/>
            <Inp label="Ymax (nm)" value={params.ymax||1000} onChange={f("ymax")} step={100}/>
            {is3d&&<Inp label="Zmax (nm)" value={params.zmax||1000} onChange={f("zmax")} step={100}/>}
          </div>
          <Inp label="Uniform Refine" value={params.uniform_refine??2}
            onChange={f("uniform_refine")} min={0}/>
          <div style={{fontSize:10,color:C.muted,marginBottom:8}}>
            {is3d
              ?`~${((params.nx||40)*(params.ny||40)*(params.nz||20)*Math.pow(2,3*(params.uniform_refine??2))).toLocaleString()} HEX8 elements`
              :`~${((params.nx||40)*(params.ny||40)*Math.pow(4,params.uniform_refine??2)).toLocaleString()} QUAD4 elements`}
          </div>
          <SHead color={C.teal} style={{fontSize:10,marginTop:4}}>Periodic BCs</SHead>
          <Toggle label="Periodic X" value={params.periodic_x??true} onChange={f("periodic_x")}/>
          <Toggle label="Periodic Y" value={params.periodic_y??true} onChange={f("periodic_y")}/>
          {is3d&&<Toggle label="Periodic Z" value={params.periodic_z??false} onChange={f("periodic_z")}/>}
        </>)}

        {/* Material */}
        {sect(C.green,"⚗ Material & Physics",<>
          {!isRandom&&<>
            <Inp label="Num Grains" value={params.num_grains||20} onChange={autoOpNum}/>
            <Inp label={`Op Num ${is3d?"(≥12 for 3D)":""}`}
              value={params.op_num||8} onChange={f("op_num")}/>
            <Select label="Coloring Algorithm"
              value={params.coloring_algorithm||"jp"}
              onChange={f("coloring_algorithm")}
              options={[{value:"jp",label:"jp (many grains)"},{value:"bt",label:"bt (op_num=n_grains)"}]}/>
            <Inp label="Random Seed" value={params.rand_seed||42} onChange={f("rand_seed")}/>
          </>}
          {isRandom&&<>
            <Inp label={`Op Num ${is3d?"(≥12)":""}`} value={params.op_num||8} onChange={f("op_num")}/>
            <div style={{fontSize:10,color:C.muted,marginBottom:10,padding:"6px 8px",
              borderRadius:4,background:C.surface,border:`1px solid ${C.border2}`}}>
              Random IC: no grain_num needed. GrainTracker delayed tracking recommended.
            </div>
          </>}
          <div style={{height:1,background:C.border,margin:"8px 0"}}/>
          {!isLinear&&<>
            <Inp label="Temperature T (K)" value={params.T||450} onChange={f("T")} step={50}/>
            <Inp label="GB Width wGB (nm)" value={params.wGB||14} onChange={f("wGB")} step={1}/>
            <Inp label="GBmob0 (m⁴/Js)" value={params.GBmob0||2.5e-6} onChange={f("GBmob0")} step={1e-7}/>
            <Inp label="Q — Activation Energy (eV)" value={params.Q||0.23} onChange={f("Q")} step={0.01}/>
            <Inp label="GB Energy (J/m²)" value={params.GBenergy||0.708} onChange={f("GBenergy")} step={0.01}/>
            <div style={{fontSize:10,color:C.cyan,marginTop:4,padding:"4px 8px",
              borderRadius:4,background:"#001a2d",border:`1px solid ${C.cyan}`}}>
              m_eff = {mobility} m⁴/Js at {params.T||450}K
            </div>
          </>}
          {isLinear&&<>
            <Inp label="Bound Value" value={params.bound_value||5} onChange={f("bound_value")} step={0.5}/>
            <Inp label="GB Mobility (gbmob)" value={params.gbmob||100} onChange={f("gbmob")} step={10}/>
            <Inp label="GB Energy (gbenergy_li)" value={params.gbenergy_li||6} onChange={f("gbenergy_li")} step={0.5}/>
            <Inp label="GB Width (gbwidth_li)" value={params.gbwidth_li||10} onChange={f("gbwidth_li")} step={1}/>
            <Inp label="Gamma Asymm" value={params.gamma_asymm||1.5} onChange={f("gamma_asymm")} step={0.1}/>
            <div style={{fontSize:10,color:C.cyan,marginTop:4,padding:"4px 8px",
              borderRadius:4,background:"#001a2d",border:`1px solid ${C.cyan}`}}>
              κ = ¾·γ·w = {(0.75*(params.gbenergy_li||6)*(params.gbwidth_li||10)).toFixed(1)}
              &nbsp;&nbsp;L = 4/3·m/w = {((4/3*(params.gbmob||100))/(params.gbwidth_li||10)).toFixed(2)}
            </div>
          </>}
        </>)}

        {/* Solver */}
        {sect(C.yellow,"⚙ Solver & Time",<>
          <Select label="Preconditioner"
            value={params.preconditioner||"asm"}
            onChange={f("preconditioner")}
            options={[
              {value:"asm",label:"ASM (3D, simple)"},
              {value:"hypre_boomeramg",label:"Hypre BoomerAMG (2D adaptive)"},
            ]}/>
          <div style={{display:"flex",gap:8}}>
            {["end_time","num_steps"].map(m=>(
              <button key={m} onClick={()=>f("time_mode")(m)} style={{
                flex:1,padding:"6px",border:`1px solid ${params.time_mode===m?C.yellow:C.border2}`,
                borderRadius:6,background:params.time_mode===m?"#2d2500":"transparent",
                color:params.time_mode===m?C.yellow:C.muted,cursor:"pointer",
                fontSize:10,fontFamily:"inherit",marginBottom:10}}>
                {m==="end_time"?"End Time":"Num Steps"}
              </button>
            ))}
          </div>
          {params.time_mode==="end_time"
            ?<Inp label="End Time (ns)" value={params.end_time||4000} onChange={f("end_time")} step={500}/>
            :<Inp label="Num Steps" value={params.num_steps||500} onChange={f("num_steps")}/>
          }
          <Inp label="Initial dt" value={params.dt_start||25} onChange={f("dt_start")} step={1}/>
          <Inp label="Optimal NL Iters" value={params.optimal_iterations||8} onChange={f("optimal_iterations")}/>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
            <Inp label="NL Max Its" value={params.nl_max_its||20} onChange={f("nl_max_its")}/>
            <Inp label="L Max Its" value={params.l_max_its||30} onChange={f("l_max_its")}/>
            <Inp label="NL Rel Tol" value={params.nl_rel_tol||1e-8} onChange={f("nl_rel_tol")} step={1e-9}/>
            <Inp label="L Tol" value={params.l_tol||1e-4} onChange={f("l_tol")} step={1e-5}/>
          </div>
          <Inp label="MPI Ranks" value={params.mpi||1} onChange={f("mpi")}/>
        </>)}
      </div>

      {/* ── Row 3: Advanced ── */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12}}>

        {/* Mesh Adaptivity */}
        {sect(C.orange,"🔀 Mesh Adaptivity",<>
          <Toggle label="Enable Adaptivity"
            value={params.use_adaptivity??true}
            onChange={f("use_adaptivity")} color={C.orange}/>
          {params.use_adaptivity&&<>
            <Inp label="Initial Adaptivity" value={params.initial_adaptivity??2} onChange={f("initial_adaptivity")}/>
            <Inp label="Refine Fraction" value={params.refine_fraction||0.7} onChange={f("refine_fraction")} step={0.05}/>
            <Inp label="Coarsen Fraction" value={params.coarsen_fraction||0.1} onChange={f("coarsen_fraction")} step={0.05}/>
            <Inp label="Max H Level" value={params.max_h_level||4} onChange={f("max_h_level")}/>
          </>}
          {!params.use_adaptivity&&(
            <div style={{fontSize:10,color:C.muted,padding:"6px 8px",borderRadius:4,
              background:C.surface,border:`1px solid ${C.border2}`}}>
              Fixed mesh — recommended for 3D
            </div>
          )}
        </>)}

        {/* GrainTracker & Terminator */}
        {sect(C.cyan,"🔍 GrainTracker & Terminator",<>
          <Inp label="GT Threshold" value={params.gt_threshold||0.1} onChange={f("gt_threshold")} step={0.01}/>
          <Inp label="Tracking Step Delay" value={params.gt_tracking_step||0} onChange={f("gt_tracking_step")}
            style={{}}/>
          <div style={{fontSize:10,color:C.muted,marginBottom:10}}>
            Set &gt;0 for Random IC (e.g. 20) to delay until grains are established
          </div>
          <div style={{height:1,background:C.border,margin:"8px 0"}}/>
          <Toggle label="Enable Terminator"
            value={params.use_terminator||false}
            onChange={f("use_terminator")} color={C.red}/>
          {params.use_terminator&&<>
            <Inp label="Stop when grain_tracker <"
              value={params.terminator_threshold||5}
              onChange={f("terminator_threshold")}/>
            <div style={{fontSize:10,color:C.muted}}>
              Stops simulation early — useful for HPC runs
            </div>
          </>}
        </>)}

        {/* Outputs */}
        {sect(C.purple,"📦 Outputs",<>
          <Inp label="Exodus Interval" value={params.exodus_interval||5} onChange={f("exodus_interval")}/>
          <Toggle label="Checkpoint" value={params.use_checkpoint||false} onChange={f("use_checkpoint")}/>
          <Toggle label="Nemesis (parallel HPC)" value={params.use_nemesis||false} onChange={f("use_nemesis")}/>
          <Toggle label="Output Halos" value={params.output_halos||false} onChange={f("output_halos")}/>
          <Toggle label="Output Ghost Elements" value={params.output_ghosts||false} onChange={f("output_ghosts")}/>
          <div style={{fontSize:10,color:C.muted,marginTop:6,padding:"6px 8px",
            borderRadius:4,background:C.surface,border:`1px solid ${C.border2}`}}>
            {params.use_nemesis?"Nemesis output for parallel 3D — open with ParaView":"Exodus for serial/small runs"}
          </div>
        </>)}
      </div>

      {/* ── Presets ── */}
      <Card>
        <SHead color={C.teal}>⚡ Presets</SHead>
        <div style={{display:"flex",flexWrap:"wrap",gap:8,marginBottom:16}}>
          {Object.entries(presets).map(([k,v])=>{
            const is3dp=k.startsWith("3D");
            const isLinP=k.includes("linearized");
            const col=is3dp?C.orange:isLinP?C.purple:C.border2;
            return(
              <button key={k} onClick={()=>setParams(p=>({...p,...v}))}
                style={{padding:"6px 14px",borderRadius:8,fontFamily:"inherit",
                  cursor:"pointer",border:`1px solid ${col}`,background:"transparent",
                  color:is3dp?C.orange:isLinP?C.purple:C.text,transition:"all .15s"}}>
                <div style={{fontSize:12,fontWeight:600}}>{k}</div>
                <div style={{fontSize:9,color:C.muted,marginTop:1}}>{v.description||""}</div>
              </button>
            );
          })}
        </div>
        <div style={{display:"flex",gap:10}}>
          <Btn color={C.purple} onClick={onGenerate} style={{padding:"10px 24px",fontSize:13}}>
            📄 Generate .i File
          </Btn>
          <Btn color={C.green} onClick={onRun} style={{padding:"10px 24px",fontSize:13}}>
            ▶ Run Locally
          </Btn>
        </div>
      </Card>
    </div>
  );
}

// ── Input Preview ─────────────────────────────────────────────────────────
function InputPreviewPanel({content}){
  if(!content) return (
    <div style={{color:C.muted,textAlign:"center",paddingTop:60}}>
      Click "Generate .i File" in Configure tab.
    </div>
  );
  return(
    <div style={{background:"#010409",border:`1px solid ${C.border}`,borderRadius:8,
      padding:16,overflowY:"auto",height:"calc(100vh - 200px)",
      fontFamily:"monospace",fontSize:11.5,lineHeight:1.7,whiteSpace:"pre"}}>
      {content.split("\n").map((line,i)=>{
        const col=line.startsWith("#")?"#6e7681":
          /^\[.*\]$/.test(line.trim())?C.blue:
          /type\s*=/.test(line)?C.purple:
          /GBmob0|GBenergy|wGB|T\s*=|gbmob|kappa|bound_value/.test(line)?C.yellow:
          /grain_num|op_num|grain_tracker/.test(line)?C.cyan:C.muted;
        return(
          <div key={i} style={{color:col}}>
            <span style={{color:"#30363d",userSelect:"none",marginRight:12}}>
              {String(i+1).padStart(4)}
            </span>
            {line}
          </div>
        );
      })}
    </div>
  );
}

// ── Log Panel ─────────────────────────────────────────────────────────────
function LogPanel({runId,status,onStop}){
  const [lines,setLines]=useState([]);
  const ref=useRef(null);
  const esRef=useRef(null);
  useEffect(()=>{
    if(!runId) return;
    setLines([]);
    if(esRef.current) esRef.current.close();
    const es=new EventSource(`${API}/runs/${runId}/log`);
    esRef.current=es;
    es.onmessage=e=>{
      try{
        const d=JSON.parse(e.data);
        if(d.line!==undefined) setLines(p=>[...p,d.line]);
        if(d.done) es.close();
      }catch{}
    };
    es.onerror=()=>es.close();
    return()=>{ if(esRef.current) esRef.current.close(); };
  },[runId]);
  useEffect(()=>{ if(ref.current) ref.current.scrollTop=ref.current.scrollHeight; },[lines]);

  const lc=l=>{
    if(/converged/i.test(l))    return C.green;
    if(/Time Step/i.test(l))    return C.yellow;
    if(/\bERROR\b/i.test(l))    return C.red;
    if(/Nonlinear/i.test(l))    return "#79c0ff";
    if(/grain_tracker|GrainTracker/i.test(l)) return C.cyan;
    if(/Adaptivity/i.test(l))   return C.orange;
    if(/Terminator/i.test(l))   return C.purple;
    return C.muted;
  };

  return(
    <div style={{display:"flex",flexDirection:"column",height:"100%"}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10}}>
        <span style={{fontSize:11,color:C.muted}}>{runId?`📋 ${runId}`:"No run selected"}</span>
        <div style={{display:"flex",gap:8}}>
          {status==="running"&&<Btn color={C.red} onClick={onStop}>⏹ Stop</Btn>}
          <Btn onClick={()=>setLines([])} color={C.muted}>🗑 Clear</Btn>
        </div>
      </div>
      <div ref={ref} style={{flex:1,background:"#010409",border:`1px solid ${C.border}`,
        borderRadius:8,padding:14,overflowY:"auto",fontFamily:"monospace",
        fontSize:11.5,lineHeight:1.75}}>
        {lines.length===0
          ?<span style={{color:C.muted}}>{runId?"Waiting for output…":"Select a run."}</span>
          :lines.map((l,i)=><div key={i} style={{color:lc(l)}}>{l||" "}</div>)
        }
        {status==="running"&&<span style={{color:C.green,animation:"blink 1s infinite"}}>█</span>}
      </div>
    </div>
  );
}

// ── Results Panel ─────────────────────────────────────────────────────────
function ResultsPanel({run,allRuns}){
  const [csvData,setCsvData]=useState(null);
  const [compareIds,setCompareIds]=useState([]);
  const [compareCsvs,setCompareCsvs]=useState({});
  const [paraviewStatus,setParaviewStatus]=useState(null);

  useEffect(()=>{
    if(!run?.run_id) return;
    setCsvData(null);
    fetch(`${API}/runs/${run.run_id}/csv`)
      .then(r=>r.ok?r.json():null).then(setCsvData).catch(()=>{});
  },[run?.run_id,run?.status]);

  useEffect(()=>{
    compareIds.forEach(id=>{
      if(compareCsvs[id]) return;
      fetch(`${API}/runs/${id}/csv`)
        .then(r=>r.ok?r.json():null)
        .then(d=>{ if(d) setCompareCsvs(p=>({...p,[id]:d})); })
        .catch(()=>{});
    });
  },[compareIds]);

  if(!run) return(
    <div style={{color:C.muted,textAlign:"center",paddingTop:80}}>
      <div style={{fontSize:48,marginBottom:16}}>📊</div>
      Select a run from the sidebar to view results.
    </div>
  );

  const m   = run.metrics||{};
  const t   = m.time_series||[];
  const gg  = m.grain_tracker_series||[];
  const dt  = m.dt_series||[];
  const d2  = m.d2_series||[];
  const dofs= m.dofs_series||[];

  const grainChart = t.map((ti,i)=>({t:+ti.toFixed(1),grains:gg[i]})).filter(p=>p.grains!=null);
  const dtChart    = t.map((ti,i)=>({t:+ti.toFixed(1),dt:dt[i]})).filter(p=>p.dt!=null);
  const d2Chart    = t.map((ti,i)=>({t:+ti.toFixed(1),d2:d2[i]})).filter(p=>p.d2!=null);
  const dofChart   = t.map((ti,i)=>({t:+ti.toFixed(1),DOFs:dofs[i]})).filter(p=>p.DOFs!=null);

  // dN/dt
  const dndt = grainChart.map((p,i)=>{
    if(i===0) return {t:p.t,dndt:0};
    const dt2=(grainChart[i].t-grainChart[i-1].t)||1e-10;
    return {t:p.t,dndt:(grainChart[i].grains-grainChart[i-1].grains)/dt2};
  });

  // compare
  const compareRuns = allRuns.filter(r=>r.run_id!==run.run_id&&r.metrics?.grain_tracker_series);
  const compareChart = (() => {
    if(!compareIds.length) return [];
    const rows=[];
    const tAll=[run,...compareIds.map(id=>allRuns.find(r=>r.run_id===id)).filter(Boolean)];
    const series=[{id:run.run_id,label:run.params?.run_name,g:gg,t}];
    compareIds.forEach(id=>{
      const r=allRuns.find(x=>x.run_id===id);
      const csv=compareCsvs[id];
      if(r&&csv?.time&&csv?.grain_tracker)
        series.push({id,label:r.params?.run_name,g:csv.grain_tracker,t:csv.time});
    });
    const maxLen=Math.max(...series.map(s=>s.t.length));
    for(let i=0;i<maxLen;i++){
      const row={};
      series.forEach(s=>{ if(s.t[i]!=null){ row.t=+s.t[i].toFixed(1); row[s.id]=s.g[i]; }});
      rows.push(row);
    }
    return {rows,series};
  })();

  const MetricCard=({label,value,color=C.blue,unit=""})=>(
    <Card style={{textAlign:"center",padding:"12px 8px"}}>
      <div style={{fontSize:22,fontWeight:700,color}}>
        {value!=null?typeof value==="number"&&!Number.isInteger(value)
          ?value.toExponential(2):value:"–"}
        {unit}
      </div>
      <div style={{fontSize:9,color:C.muted,marginTop:3,
        textTransform:"uppercase",letterSpacing:0.5}}>{label}</div>
    </Card>
  );

  const ChartCard=({title,color,children})=>(
    <Card style={{marginBottom:14}}>
      <div style={{fontSize:12,color,fontWeight:700,marginBottom:12}}>{title}</div>
      {children}
    </Card>
  );

  const ttStyle={background:C.card,border:`1px solid ${C.border}`,borderRadius:6,fontSize:11};

  return(
    <div>
      {/* Status bar */}
      <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:16,
        padding:"10px 16px",borderRadius:8,background:C.card,
        border:`1px solid ${STATUS_COLOR[run.status]||C.border}`}}>
        <Dot status={run.status}/>
        <span style={{color:STATUS_COLOR[run.status],fontWeight:700}}>
          {run.status?.toUpperCase()}
        </span>
        {run.duration_s&&<Badge color={C.green}>⏱ {run.duration_s}s</Badge>}
        <span style={{color:C.muted,fontSize:11}}>
          {run.params?.run_name}
          {run.params?.formulation&&<> · <Badge color={C.purple}>{run.params.formulation}</Badge></>}
          {run.params?.ic_type&&<> · <Badge color={C.cyan}>{run.params.ic_type} IC</Badge></>}
          {run.params?.dim&&<> · <Badge color={C.blue}>{run.params.dim}D</Badge></>}
        </span>
        <div style={{flex:1}}/>
        {/* ParaView button */}
        <Btn color={C.teal} onClick={()=>{
          const exFile=run.params?.run_name;
          setParaviewStatus(`Open in ParaView: ${run.run_dir||"see sidebar"}/${exFile}.e`);
          setTimeout(()=>setParaviewStatus(null),6000);
        }}>🎨 ParaView</Btn>
      </div>
      {paraviewStatus&&(
        <div style={{marginBottom:12,padding:"8px 14px",borderRadius:6,
          background:"#001a2d",border:`1px solid ${C.teal}`,
          fontSize:11,color:C.teal,fontFamily:"monospace"}}>
          {paraviewStatus}
        </div>
      )}

      {/* Metrics */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginBottom:16}}>
        <MetricCard label="Initial Grains"  value={m.grains_initial}   color={C.blue}/>
        <MetricCard label="Final Grains"    value={m.grains_final}     color={C.green}/>
        <MetricCard label="Reduction"       value={m.grain_reduction_pct} color={C.cyan} unit="%"/>
        <MetricCard label="Parabolic R²"    value={m.parabolic_R2}     color={C.yellow}/>
        <MetricCard label="Timesteps"       value={m.total_timesteps}  color={C.orange}/>
        <MetricCard label="Final Time"      value={m.final_time}       color={C.purple}/>
        <MetricCard label="Final dt"        value={m.dt_final}         color={C.teal}/>
        <MetricCard label="Final DOFs"      value={m.dofs_final}       color={C.pink}/>
      </div>

      {grainChart.length===0
        ?<Card><div style={{color:C.muted,textAlign:"center",padding:30}}>
          {run.status==="running"?"⟳ Running — charts appear after CSV is written":"No CSV data yet."}
        </div></Card>
        :<>
          {/* Grain count */}
          <ChartCard title="🌾 Grain Count vs Time" color={C.blue}>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={grainChart} margin={{top:5,right:20,bottom:5,left:0}}>
                <CartesianGrid strokeDasharray="3 3" stroke={C.border}/>
                <XAxis dataKey="t" stroke={C.muted} tick={{fontSize:10}} label={{value:"Time (ns)",position:"insideBottom",offset:-2,fill:C.muted,fontSize:10}}/>
                <YAxis stroke={C.muted} tick={{fontSize:10}} label={{value:"Grains",angle:-90,position:"insideLeft",fill:C.muted,fontSize:10}}/>
                <Tooltip contentStyle={ttStyle} formatter={v=>[v?.toFixed(0),"grains"]} labelFormatter={v=>`t=${v}ns`}/>
                <Line type="monotone" dataKey="grains" stroke={C.blue} dot={false} strokeWidth={2}/>
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>

          {/* Parabolic fit */}
          {d2Chart.length>0&&(
            <ChartCard title={`📐 Parabolic Fit — d² ~ t  (R² = ${m.parabolic_R2??'–'})`} color={C.yellow}>
              <div style={{fontSize:10,color:C.muted,marginBottom:8}}>
                Using 1/N² as proxy for d² (N = grain count). Good fit → R² &gt; 0.99.
              </div>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={d2Chart} margin={{top:5,right:20,bottom:5,left:0}}>
                  <CartesianGrid strokeDasharray="3 3" stroke={C.border}/>
                  <XAxis dataKey="t" stroke={C.muted} tick={{fontSize:10}}/>
                  <YAxis stroke={C.muted} tick={{fontSize:10}} tickFormatter={v=>v?.toExponential(1)}/>
                  <Tooltip contentStyle={ttStyle}/>
                  <Line type="monotone" dataKey="d2" stroke={C.yellow} dot={false} strokeWidth={2} name="1/N²"/>
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
          )}

          {/* dN/dt */}
          <ChartCard title="📉 Grain Reduction Rate dN/dt" color={C.red}>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={dndt} margin={{top:5,right:20,bottom:5,left:0}}>
                <CartesianGrid strokeDasharray="3 3" stroke={C.border}/>
                <XAxis dataKey="t" stroke={C.muted} tick={{fontSize:10}}/>
                <YAxis stroke={C.muted} tick={{fontSize:10}}/>
                <ReferenceLine y={0} stroke={C.border2}/>
                <Tooltip contentStyle={ttStyle} formatter={v=>[v?.toFixed(4),"dN/dt"]}/>
                <Line type="monotone" dataKey="dndt" stroke={C.red} dot={false} strokeWidth={1.5} name="dN/dt"/>
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>

          {/* dt evolution */}
          {dtChart.length>0&&(
            <ChartCard title="⏱ Adaptive Timestep dt" color={C.green}>
              <ResponsiveContainer width="100%" height={140}>
                <LineChart data={dtChart} margin={{top:5,right:20,bottom:5,left:0}}>
                  <CartesianGrid strokeDasharray="3 3" stroke={C.border}/>
                  <XAxis dataKey="t" stroke={C.muted} tick={{fontSize:10}}/>
                  <YAxis stroke={C.muted} tick={{fontSize:10}} tickFormatter={v=>v?.toExponential(1)}/>
                  <Tooltip contentStyle={ttStyle}/>
                  <Line type="monotone" dataKey="dt" stroke={C.green} dot={false} strokeWidth={1.5}/>
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
          )}

          {/* DOF evolution */}
          {dofChart.length>0&&(
            <ChartCard title="🧮 Mesh DOFs" color={C.pink}>
              <ResponsiveContainer width="100%" height={140}>
                <LineChart data={dofChart} margin={{top:5,right:20,bottom:5,left:0}}>
                  <CartesianGrid strokeDasharray="3 3" stroke={C.border}/>
                  <XAxis dataKey="t" stroke={C.muted} tick={{fontSize:10}}/>
                  <YAxis stroke={C.muted} tick={{fontSize:10}} tickFormatter={v=>(v/1000).toFixed(0)+"k"}/>
                  <Tooltip contentStyle={ttStyle} formatter={v=>[v?.toLocaleString(),"DOFs"]}/>
                  <Line type="monotone" dataKey="DOFs" stroke={C.pink} dot={false} strokeWidth={1.5}/>
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
          )}

          {/* Side-by-side compare */}
          <Card>
            <SHead color={C.orange}>⚖ Compare Runs</SHead>
            <div style={{display:"flex",flexWrap:"wrap",gap:6,marginBottom:12}}>
              {compareRuns.map(r=>{
                const sel=compareIds.includes(r.run_id);
                return(
                  <button key={r.run_id} onClick={()=>setCompareIds(p=>
                    sel?p.filter(x=>x!==r.run_id):[...p,r.run_id])}
                    style={{padding:"4px 10px",borderRadius:6,fontFamily:"inherit",
                      fontSize:10,cursor:"pointer",
                      border:`1px solid ${sel?C.orange:C.border2}`,
                      background:sel?"#2d1200":"transparent",
                      color:sel?C.orange:C.muted}}>
                    {r.params?.run_name||r.run_id}
                    <span style={{marginLeft:4,fontSize:9,color:C.muted}}>
                      {r.params?.dim}D·{r.params?.num_grains}g·T{r.params?.T}
                    </span>
                  </button>
                );
              })}
              {compareRuns.length===0&&(
                <span style={{fontSize:11,color:C.muted}}>
                  Run more simulations to enable comparison.
                </span>
              )}
            </div>
            {compareChart.rows?.length>0&&(
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={compareChart.rows} margin={{top:5,right:20,bottom:5,left:0}}>
                  <CartesianGrid strokeDasharray="3 3" stroke={C.border}/>
                  <XAxis dataKey="t" stroke={C.muted} tick={{fontSize:10}}/>
                  <YAxis stroke={C.muted} tick={{fontSize:10}}/>
                  <Tooltip contentStyle={ttStyle} formatter={v=>[v?.toFixed(0),"grains"]}/>
                  <Legend wrapperStyle={{fontSize:10}}/>
                  {compareChart.series?.map((s,i)=>(
                    <Line key={s.id} type="monotone" dataKey={s.id}
                      name={s.label||s.id} stroke={SERIES_COLORS[i%SERIES_COLORS.length]}
                      dot={false} strokeWidth={2}/>
                  ))}
                </LineChart>
              </ResponsiveContainer>
            )}
          </Card>
        </>
      }
    </div>
  );
}

// ── Chat Panel ────────────────────────────────────────────────────────────
const WELCOME = {role:"assistant",content:
  "Hello! I'm your AutoMOOSE Grain Growth assistant.\n\n"+
  "**Capabilities:**\n"+
  "• Physics help — GBEvolution, LinearizedInterface, Voronoi/Random IC\n"+
  "• Parameter sweeps — type: `T 300, 450, 600, 800`\n"+
  "• Convergence & adaptivity guidance\n"+
  "• Results interpretation — parabolic fit, dN/dt, DOF evolution\n\n"+
  "**Quick sweeps:** `num_grains 10, 20, 50` · `GBenergy 0.5, 0.7, 1.0`"
};

function ChatPanel({activeRunId,physics,onRunTriggered}){
  const [msgs,setMsgs]=useState([WELCOME]);
  const [input,setInput]=useState("");
  const [loading,setLoading]=useState(false);
  const bottomRef=useRef(null);
  useEffect(()=>{ bottomRef.current?.scrollIntoView({behavior:"smooth"}); },[msgs,loading]);

  const send=async()=>{
    if(!input.trim()||loading) return;
    const userMsg=input.trim();
    setMsgs(p=>[...p,{role:"user",content:userMsg}]);
    setInput(""); setLoading(true);
    try{
      const res=await fetch(`${API}/chat`,{method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({message:userMsg,physics,run_id:activeRunId,history:msgs.slice(-10)})});
      const reader=res.body.getReader(); const dec=new TextDecoder();
      let buf="",aiText="";
      setMsgs(p=>[...p,{role:"assistant",content:""}]);
      while(true){
        const {done,value}=await reader.read(); if(done) break;
        buf+=dec.decode(value,{stream:true});
        const parts=buf.split("\n\n"); buf=parts.pop();
        for(const part of parts){
          if(!part.startsWith("data:")) continue;
          try{
            const d=JSON.parse(part.slice(5).trim());
            if(d.text){ aiText+=d.text;
              setMsgs(p=>{const c=[...p];c[c.length-1]={role:"assistant",content:aiText};return c;}); }
            if(d.run_triggered&&d.run_id) onRunTriggered(d.run_id);
          }catch{}
        }
      }
    }catch(e){ setMsgs(p=>[...p,{role:"assistant",content:`Error: ${e.message}`}]); }
    setLoading(false);
  };

  const QUICK=[
    "T 300, 450, 600, 800",
    "num_grains 10, 25, 50, 100",
    "GBenergy 0.5, 0.708, 1.0",
    "what does uniform_refine do?",
    "explain parabolic grain growth law",
    "when should I use LinearizedInterface?",
    "what is the Terminator UserObject?",
  ];

  const render=text=>text.split(/(\*\*[^*]+\*\*|`[^`]+`|\n)/g).map((p,i)=>{
    if(p==="\n") return <br key={i}/>;
    if(p.startsWith("**")&&p.endsWith("**")) return<strong key={i}>{p.slice(2,-2)}</strong>;
    if(p.startsWith("`")&&p.endsWith("`")) return<code key={i} style={{background:C.surface,
      padding:"1px 5px",borderRadius:4,fontSize:"0.9em",color:C.cyan}}>{p.slice(1,-1)}</code>;
    return p;
  });

  return(
    <div style={{display:"flex",flexDirection:"column",height:"100%"}}>
      <div style={{display:"flex",justifyContent:"flex-end",marginBottom:8}}>
        <Btn onClick={()=>setMsgs([WELCOME])} color={C.muted} style={{fontSize:11,padding:"4px 12px"}}>
          🗑 Clear
        </Btn>
      </div>
      <div style={{flex:1,overflowY:"auto",paddingRight:4,marginBottom:10}}>
        {msgs.map((m,i)=>(
          <div key={i} style={{display:"flex",gap:10,marginBottom:14,
            flexDirection:m.role==="user"?"row-reverse":"row"}}>
            <div style={{width:30,height:30,borderRadius:"50%",flexShrink:0,marginTop:2,
              display:"flex",alignItems:"center",justifyContent:"center",fontSize:14,
              background:m.role==="user"
                ?`linear-gradient(135deg,${C.blue},${C.purple})`
                :`linear-gradient(135deg,${C.green},${C.blue})`}}>
              {m.role==="user"?"U":"⚛"}
            </div>
            <div style={{maxWidth:"82%",background:m.role==="user"?"#1c2128":C.card,
              border:`1px solid ${C.border}`,
              borderRadius:m.role==="user"?"12px 12px 2px 12px":"12px 12px 12px 2px",
              padding:"10px 14px",fontSize:13,lineHeight:1.7}}>
              {render(m.content)}
            </div>
          </div>
        ))}
        {loading&&(
          <div style={{display:"flex",gap:10,marginBottom:14}}>
            <div style={{width:30,height:30,borderRadius:"50%",
              background:`linear-gradient(135deg,${C.green},${C.blue})`,
              display:"flex",alignItems:"center",justifyContent:"center"}}>⚛</div>
            <div style={{background:C.card,border:`1px solid ${C.border}`,
              borderRadius:"12px 12px 12px 2px",padding:"10px 14px"}}>
              <span style={{color:C.muted}}>Thinking…</span>
            </div>
          </div>
        )}
        <div ref={bottomRef}/>
      </div>
      <div style={{display:"flex",flexWrap:"wrap",gap:5,marginBottom:8}}>
        {QUICK.map(q=>(
          <button key={q} onClick={()=>setInput(q)} style={{padding:"3px 9px",
            border:`1px solid ${C.border2}`,borderRadius:20,background:"transparent",
            color:C.muted,cursor:"pointer",fontSize:10,fontFamily:"inherit"}}>{q}</button>
        ))}
      </div>
      <div style={{display:"flex",gap:8}}>
        <textarea value={input} onChange={e=>setInput(e.target.value)}
          onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();}}}
          placeholder='Ask anything or sweep: "T 300, 450, 600"'
          rows={2} style={{flex:1,background:C.card,border:`1px solid ${C.border2}`,
            borderRadius:8,padding:"10px 14px",color:C.text,fontSize:13,
            fontFamily:"inherit",outline:"none",resize:"none",lineHeight:1.5}}/>
        <Btn color={C.blue} onClick={send} disabled={loading}
          style={{padding:"10px 20px",alignSelf:"flex-end"}}>Send</Btn>
      </div>
    </div>
  );
}

// ── Physics Selector ──────────────────────────────────────────────────────
function PhysicsSelector({plugins,activePhysics,onSelect}){
  return(
    <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
      {Object.values(plugins).map(p=>{
        const active=p.id===activePhysics;
        return(
          <button key={p.id} onClick={()=>p.status==="ready"&&onSelect(p.id)}
            style={{display:"flex",alignItems:"center",gap:6,padding:"5px 13px",
              borderRadius:20,fontFamily:"inherit",fontSize:12,
              cursor:p.status==="ready"?"pointer":"default",
              border:`1px solid ${active?C.green:p.status==="ready"?C.border2:C.border}`,
              background:active?"#0d2419":"transparent",
              color:active?C.green:p.status==="ready"?C.text:C.muted,
              transition:"all .15s"}}>
            <span>{p.icon}</span><span>{p.label}</span>
            {p.status!=="ready"&&(
              <span style={{fontSize:9,color:C.muted,background:C.surface,
                padding:"1px 6px",borderRadius:10}}>soon</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ── Run Sidebar ───────────────────────────────────────────────────────────
function RunSidebar({runs,plugins,activeId,onSelect}){
  return(
    <div style={{display:"flex",flexDirection:"column",gap:5}}>
      {runs.length===0
        ?<div style={{color:C.muted,fontSize:11,textAlign:"center",paddingTop:20}}>No runs yet</div>
        :runs.map(r=>{
          const plugin=plugins[r.physics]||{};
          const form=r.params?.formulation;
          const ic=r.params?.ic_type;
          return(
            <div key={r.run_id} onClick={()=>onSelect(r.run_id)} style={{
              padding:"9px 11px",borderRadius:8,cursor:"pointer",
              border:`1px solid ${r.run_id===activeId?C.blue:C.border}`,
              background:r.run_id===activeId?"#0d1f33":C.card,
              transition:"all .15s"}}>
              <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:3}}>
                <div style={{display:"flex",alignItems:"center",gap:4}}>
                  <Dot status={r.status}/>
                  <span style={{fontSize:10,color:C.text,fontWeight:600,
                    overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",maxWidth:120}}>
                    {r.params?.run_name||r.run_id}
                  </span>
                </div>
                <span style={{fontSize:8,color:STATUS_COLOR[r.status],fontWeight:700,
                  textTransform:"uppercase",flexShrink:0}}>{r.status}</span>
              </div>
              <div style={{display:"flex",gap:4,flexWrap:"wrap",marginBottom:2}}>
                <Badge color={C.blue}>{plugin.icon} {plugin.label||r.physics}</Badge>
                {r.params?.dim&&<Badge color={C.green}>{r.params.dim}D</Badge>}
                {form&&<Badge color={C.purple}>{form==="GBEvolution"?"GBEvo":"LinIF"}</Badge>}
                {ic&&<Badge color={C.teal}>{ic}</Badge>}
              </div>
              <div style={{fontSize:9,color:C.muted}}>
                {r.params?.num_grains&&`${r.params.num_grains}g `}
                {r.params?.nx&&(r.params.dim===3?`${r.params.nx}³`:`${r.params.nx}×${r.params.ny}`)}
                {r.params?.T&&` T=${r.params.T}K`}
              </div>
              {r.metrics?.grain_reduction_pct!=null&&(
                <div style={{fontSize:9,color:C.green,marginTop:1}}>
                  ↓{r.metrics.grain_reduction_pct}%
                  {r.metrics.parabolic_R2!=null&&
                    <span style={{color:C.yellow,marginLeft:6}}>R²={r.metrics.parabolic_R2}</span>}
                </div>
              )}
              {r.sweep&&<div style={{fontSize:8,color:C.orange,marginTop:1}}>🔁 {r.sweep} sweep</div>}
              {r.duration_s&&<div style={{fontSize:8,color:C.muted}}>⏱ {r.duration_s}s</div>}
            </div>
          );
        })
      }
    </div>
  );
}

function StubPanel({plugin}){
  return(
    <Card style={{textAlign:"center",padding:60}}>
      <div style={{fontSize:48,marginBottom:16}}>{plugin?.icon}</div>
      <div style={{fontSize:18,color:C.text,fontWeight:700,marginBottom:8}}>{plugin?.label}</div>
      <div style={{fontSize:13,color:C.muted,marginBottom:16}}>{plugin?.description}</div>
      <div style={{fontSize:11,color:C.yellow,padding:"6px 16px",borderRadius:20,
        border:`1px solid ${C.yellow}`,display:"inline-block"}}>
        Coming soon — plugin under development
      </div>
    </Card>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────
export default function App(){
  const [tab,setTab]           = useState("chat");
  const [plugins,setPlugins]   = useState({});
  const [physics,setPhysics]   = useState("grain_growth");
  const [params,setParams]     = useState({});
  const [runs,setRuns]         = useState([]);
  const [activeId,setActiveId] = useState(null);
  const [health,setHealth]     = useState(null);
  const [inputPreview,setInputPreview] = useState("");

  const activeRun    = runs.find(r=>r.run_id===activeId)||null;
  const activePlugin = plugins[physics]||{};

  useEffect(()=>{
    const tick=async()=>{
      try{
        const [r,h,p]=await Promise.all([
          fetch(`${API}/runs`),fetch(`${API}/health`),fetch(`${API}/plugins`)]);
        if(r.ok) setRuns(await r.json());
        if(h.ok) setHealth(await h.json());
        if(p.ok){
          const pd=await p.json();
          setPlugins(pd);
          setParams(prev=>Object.keys(prev).length?prev:(pd[physics]?.params||{}));
        }
      }catch{}
    };
    tick(); const id=setInterval(tick,2000); return()=>clearInterval(id);
  },[]);

  useEffect(()=>{
    if(plugins[physics]) setParams(plugins[physics].params||{});
  },[physics]);

  useEffect(()=>{
    if(!activeId||activeRun?.status!=="running") return;
    const id=setInterval(async()=>{
      try{
        const r=await fetch(`${API}/runs/${activeId}`);
        if(r.ok){const d=await r.json();setRuns(p=>p.map(x=>x.run_id===activeId?d:x));}
      }catch{}
    },3000); return()=>clearInterval(id);
  },[activeId,activeRun?.status]);

  const handleGenerate=async()=>{
    try{
      const res=await fetch(`${API}/generate`,{method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({physics,params})});
      if(!res.ok){const e=await res.json();alert(e.detail);return;}
      const d=await res.json();
      setInputPreview(d.input_file); setTab("input");
    }catch(e){alert(`Error: ${e.message}`);}
  };

  const handleRun=async()=>{
    try{
      const res=await fetch(`${API}/run`,{method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({physics,params,mpi:params.mpi||1})});
      if(!res.ok){const e=await res.json();alert(e.detail);return;}
      const {run_id}=await res.json();
      setActiveId(run_id); setTab("log");
    }catch(e){alert(`Error: ${e.message}`);}
  };

  const handleStop=async()=>{
    if(activeId) await fetch(`${API}/stop/${activeId}`,{method:"POST"});
  };

  const handleRunTriggered=id=>{setActiveId(id);setTab("log");};
  const handleSelect=id=>{setActiveId(id);setTab("results");};

  function Tab({id,label}){
    return<button onClick={()=>setTab(id)} style={{padding:"8px 18px",border:"none",
      background:"transparent",color:tab===id?C.green:C.muted,cursor:"pointer",
      fontSize:13,fontWeight:tab===id?700:400,fontFamily:"inherit",
      borderBottom:`2px solid ${tab===id?C.green:"transparent"}`,
      transition:"all .15s"}}>{label}</button>;
  }

  const mooseOk=health?.executables?.grain_growth?.found;

  return(
    <div style={{background:C.bg,minHeight:"100vh",color:C.text,
      fontFamily:"'SF Mono','Fira Code',monospace",display:"flex",flexDirection:"column"}}>

      {/* Header */}
      <div style={{background:C.surface,borderBottom:`1px solid ${C.border}`,
        padding:"10px 24px",display:"flex",alignItems:"center",gap:16,flexWrap:"wrap"}}>
        <div style={{width:36,height:36,borderRadius:10,flexShrink:0,
          background:`linear-gradient(135deg,${C.green},${C.blue})`,
          display:"flex",alignItems:"center",justifyContent:"center",fontSize:20}}>⚛</div>
        <div style={{marginRight:8}}>
          <div style={{fontWeight:700,fontSize:15,letterSpacing:0.5}}>AutoMOOSE</div>
          <div style={{fontSize:9,color:C.muted,letterSpacing:1,textTransform:"uppercase"}}>
            Multi-Physics MOOSE Agent
          </div>
        </div>
        <PhysicsSelector plugins={plugins} activePhysics={physics} onSelect={p=>{
          setPhysics(p); setTab("chat"); setInputPreview("");
        }}/>
        <div style={{flex:1}}/>
        <div style={{display:"flex",gap:14,alignItems:"center"}}>
          {[{label:"MOOSE",ok:mooseOk},{label:"Claude API",ok:health?.api_key_set}].map(s=>(
            <div key={s.label} style={{fontSize:11,display:"flex",alignItems:"center",gap:5}}>
              <span style={{width:7,height:7,borderRadius:"50%",
                background:s.ok?C.green:C.yellow}}/>
              <span style={{color:s.ok?C.green:C.muted}}>{s.label}</span>
            </div>
          ))}
          {health?.hostname&&(
            <span style={{fontSize:9,color:C.muted}}>{health.hostname}</span>
          )}
          {activeRun&&(
            <div style={{fontSize:11,display:"flex",alignItems:"center"}}>
              <Dot status={activeRun.status}/>
              <span style={{color:STATUS_COLOR[activeRun.status]}}>
                {activeRun.params?.run_name} · {activeRun.status}
              </span>
            </div>
          )}
        </div>
      </div>

      <div style={{display:"flex",flex:1,overflow:"hidden"}}>
        {/* Sidebar */}
        <div style={{width:224,background:C.surface,borderRight:`1px solid ${C.border}`,
          padding:12,overflowY:"auto",flexShrink:0}}>
          <div style={{fontSize:9,color:C.muted,fontWeight:700,letterSpacing:1,
            textTransform:"uppercase",marginBottom:10}}>All Runs</div>
          <RunSidebar runs={runs} plugins={plugins} activeId={activeId}
            onSelect={handleSelect}/>
        </div>

        {/* Main */}
        <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>
          <div style={{background:C.surface,borderBottom:`1px solid ${C.border}`,
            padding:"0 24px",display:"flex",gap:2}}>
            <Tab id="chat"    label="💬 Chat"/>
            <Tab id="config"  label="⚙ Configure"/>
            <Tab id="input"   label="📄 Input File"/>
            <Tab id="log"     label="📋 Live Log"/>
            <Tab id="results" label="📊 Results"/>
          </div>
          <div style={{flex:1,overflowY:"auto",padding:24}}>
            {tab==="chat"&&(
              <div style={{maxWidth:800,height:"calc(100vh - 175px)",display:"flex",flexDirection:"column"}}>
                <ChatPanel activeRunId={activeId} physics={physics}
                  onRunTriggered={handleRunTriggered}/>
              </div>
            )}
            {tab==="config"&&(
              activePlugin.status==="ready"
                ?<ConfigurePanel params={params} setParams={setParams}
                    presets={activePlugin.presets||{}}
                    onGenerate={handleGenerate} onRun={handleRun}/>
                :<StubPanel plugin={activePlugin}/>
            )}
            {tab==="input"&&(
              <div style={{maxWidth:960}}><InputPreviewPanel content={inputPreview}/></div>
            )}
            {tab==="log"&&(
              <div style={{maxWidth:960,height:"calc(100vh - 175px)",display:"flex",flexDirection:"column"}}>
                <LogPanel runId={activeId} status={activeRun?.status} onStop={handleStop}/>
              </div>
            )}
            {tab==="results"&&(
              <div style={{maxWidth:1000}}>
                <ResultsPanel run={activeRun} allRuns={runs}/>
              </div>
            )}
          </div>
        </div>
      </div>

      <style>{`
        *{box-sizing:border-box;}body{margin:0;}
        ::-webkit-scrollbar{width:5px;height:5px;}
        ::-webkit-scrollbar-track{background:${C.surface};}
        ::-webkit-scrollbar-thumb{background:${C.border2};border-radius:3px;}
        input::-webkit-outer-spin-button,input::-webkit-inner-spin-button{-webkit-appearance:none;}
      `}</style>
    </div>
  );
}
