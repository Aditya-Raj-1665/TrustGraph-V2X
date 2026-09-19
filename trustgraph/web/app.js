/* Offline replay: every prediction and action comes from the Python exporter. */
"use strict";
const D=window.TRUSTGRAPH_DATA,$=id=>document.getElementById(id);
const colors=['#57d5cc','#ad9afa','#f5cc70'],names=['A','B','C'];
let scenario='attack',frameIndex=0,selected=0,playing=false,speed=1,sumoIndex=0,sumoPlaying=false,tab='network';
const fmt=(v,n=2)=>v===null||v===undefined?'—':Number(v).toFixed(n);
const pct=v=>v===null||v===undefined?'—':`${Math.round(v*100)}%`;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function replay(){return D.replays[scenario]}
function frame(){return replay().frames[frameIndex]}
function text(ctx,s,x,y,size=16,color='#b6c5d9',align='left'){ctx.fillStyle=color;ctx.font=`${size}px Segoe UI,Arial`;ctx.textAlign=align;ctx.fillText(s,x,y)}
function line(ctx,x1,y1,x2,y2,color,width=1,dash=[]){ctx.beginPath();ctx.setLineDash(dash);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();ctx.setLineDash([])}
function car(ctx,x,y,color,angle=0,chosen=false){ctx.save();ctx.translate(x,y);ctx.rotate(angle);if(chosen){ctx.strokeStyle='#ffffff';ctx.lineWidth=2;ctx.beginPath();ctx.arc(0,0,19,0,Math.PI*2);ctx.stroke()}ctx.fillStyle='#050c16';ctx.fillRect(-9,-11,5,22);ctx.fillRect(4,-11,5,22);ctx.fillStyle=color;ctx.fillRect(-13,-8,26,16);ctx.fillStyle='#172e42';ctx.fillRect(-3,-6,7,12);ctx.fillStyle='#e8ffef';ctx.fillRect(10,-6,3,3);ctx.fillRect(10,3,3,3);ctx.restore()}
function networkMap(){
 const ctx=$('network-map').getContext('2d'),f=frame(),o=f.observed,show=$('truth').checked;
 const x=v=>55+(v+650)/1600*1010,y=v=>v>0?287:344;
 ctx.clearRect(0,0,1120,460);ctx.fillStyle='#0e1a2a';ctx.fillRect(0,0,1120,460);
 for(let v=-600;v<=900;v+=100){line(ctx,x(v),25,x(v),410,'#1b2c41');if(v%200===0)text(ctx,`${v} m`,x(v),432,13,'#6e849e','center')}
 ctx.fillStyle='#25354a';ctx.fillRect(x(-600),259,x(600)-x(-600),112);
 line(ctx,x(-600),315,x(600),315,'#aab88b',2,[16,12]);line(ctx,x(-600),260,x(600),260,'#728094');line(ctx,x(-600),371,x(600),371,'#728094');
 text(ctx,'Synthetic straight-road environment',55,24,14,'#90a5bd');text(ctx,'Reported positions can lie beyond the road',1080,24,12,'#71879f','right');
 for(let c=0;c<3;c++){
   const cx=x(replay().cell_x[c]);ctx.fillStyle=colors[c];ctx.beginPath();ctx.arc(cx,111,9,0,Math.PI*2);ctx.fill();line(ctx,cx,120,cx,163,colors[c],3);line(ctx,cx-17,164,cx+17,164,colors[c],3);
   for(const radius of [19,31]){ctx.beginPath();ctx.strokeStyle=colors[c]+'70';ctx.lineWidth=2;ctx.arc(cx,111,radius,-Math.PI*.8,-Math.PI*.2);ctx.stroke()}
   text(ctx,`CELL ${names[c]}`,cx,192,16,colors[c],'center');
 }
 for(let i=0;i<o.serving.length;i++){
   let xx=x(show?f.truth.actual_x[i]:o.reported_x[i]),yy=y(o.reported_y[i]);
   line(ctx,x(replay().cell_x[o.serving[i]]),198,xx,yy,colors[o.serving[i]]+(i===selected?'b0':'20'),i===selected?2:1);
 }
 for(let i=0;i<o.serving.length;i++){
   const yy=y(o.reported_y[i]),actual=f.truth.actual_x[i],report=o.reported_x[i];
   if(show&&Math.abs(report-actual)>1){
     line(ctx,x(actual),yy,x(report),yy+35,i===selected?'#ff969a':'#ff969a55',1,[4,5]);ctx.setLineDash([4,3]);ctx.strokeStyle=i===selected?'#ff969a':'#b6858660';ctx.lineWidth=2;ctx.strokeRect(x(report)-10,yy+25,20,15);ctx.setLineDash([]);
     if(i===selected)text(ctx,'reported',x(report),yy+60,13,'#ff969a','center');
   }
   car(ctx,x(show?actual:report),yy,colors[o.serving[i]],o.direction[i]<0?Math.PI:0,i===selected);
   if(i===selected)text(ctx,replay().vehicle_ids[i],x(show?actual:report),yy-29,15,'#ffffff','center');
 }
 text(ctx,show?'Ground truth visible for evaluation only':'Reported positions only',55,452,12,'#91a6be');
 $('network-map').onclick=e=>{const rect=e.currentTarget.getBoundingClientRect(),cx=(e.clientX-rect.left)*1120/rect.width,cy=(e.clientY-rect.top)*460/rect.height;let nearest=-1,best=36;for(let i=0;i<o.serving.length;i++){let distance=Math.hypot(x(show?f.truth.actual_x[i]:o.reported_x[i])-cx,y(o.reported_y[i])-cy);if(distance<best){best=distance;nearest=i}}if(nearest>=0){selected=nearest;$('vehicle').value=String(selected);render()}};
}
function render(){
 const f=frame(),o=f.observed,p=f.prediction,v=selected,decision=f.decisions[v],risk=p?.risk[v],attack=p?.attack_probability[v],trust=p?1-attack:null;
 $('clock').textContent=`${f.time.toFixed(1)} s`;$('timeline').value=frameIndex;$('frame-count').textContent=`${f.total_handovers} handovers applied · ${frameIndex+1}/${replay().frames.length}`;
 $('vehicle-title').textContent=replay().vehicle_ids[v];
 $('attack-state').textContent=$('truth').checked?(f.truth.attack[v]?'Injected attack active · ground truth':'Telemetry unmodified · ground truth'):'Ground-truth status hidden';
 $('vehicle-data').innerHTML=[['Serving cell',`Cell ${names[o.serving[v]]}`],['Reported x',`${fmt(o.reported_x[v],1)} m`],...($('truth').checked?[['Actual x',`${fmt(f.truth.actual_x[v],1)} m`]]:[]),['Speed',`${fmt(o.speed[v],1)} m/s`],['Serving SINR',`${fmt(o.sinr[v][o.serving[v]],1)} dB`],['Predicted link risk',pct(risk)],['Attack estimate',pct(attack)]].map(([a,b])=>`<dt>${a}</dt><dd>${b}</dd>`).join('');
 $('trust-meter').style.width=p?`${100*trust}%`:'0%';$('trust-meter').style.background=trust<.5?'#ff969a':'#57d5cc';
 $('trust-value').textContent=p?`Message multiplier: ${fmt(trust,3)}×`:`Collecting ${D.config.history} observations…`;
 $('gate-delta').textContent=p?`Same weights, gate disabled: link risk ${pct(f.gate_disabled.risk[v])}. With gate: ${pct(risk)}. This is a mechanism comparison, not proof of better accuracy.`:'Predictions appear at 0.9 s after the history window fills.';
 $('decision').textContent=decision.target===decision.serving?`Keep cell ${names[decision.serving]}`:`Cell ${names[decision.serving]} → ${names[decision.target]}`;
 const mode={model:'Model-based scoring',reactive_fallback:'Conventional fallback',reactive:'Conventional rule',load_aware:'Load-aware rule'}[decision.mode];
 $('decision-reason').textContent=`${mode}. ${decision.reason}.`;
 $('certainty').textContent=decision.certainty===null?'No certainty score used for this decision.':`Certainty heuristic ${pct(decision.certainty)}; required ${pct(D.config.confidence_threshold)}. Scores below this threshold use fallback.`;
 $('cells').innerHTML=o.load.map((load,i)=>`<div class="cell"><span style="color:${colors[i]}">CELL ${names[i]}</span><strong>${pct(load)}</strong><div class="meter"><div style="width:${Math.min(load,1)*100}%;background:${load>1?'#ff969a':colors[i]}"></div></div><p>Predicted +1 s: ${pct(p?.load[i])}</p><p>${o.serving.filter(x=>x===i).length} attached / ${D.config.cell_capacity} capacity proxy</p></div>`).join('');
 const ev=replay().events.filter(e=>e.step<=frameIndex).slice(-5).reverse();
 $('event-log').innerHTML=ev.length?ev.map(e=>`<div class="event-line"><button data-step="${e.step}" data-vehicle="${e.vehicle}">${e.time.toFixed(1)} s · ${replay().vehicle_ids[e.vehicle]} · ${names[e.from]} → ${names[e.to]}</button><br>${e.mode==='model'?'Model-based scoring':'Conventional rule / fallback'}</div>`).join(''):'No handover has occurred at this point.';
 $('event-log').querySelectorAll('button').forEach(b=>b.onclick=()=>{playing=false;frameIndex=+b.dataset.step;selected=+b.dataset.vehicle;$('vehicle').value=selected;render()});
 $('narration').textContent=scenario==='clean'?'Clean telemetry provides a reference run with the same initial seed. The model can still produce false alarms. Switch scenarios at the same timestamp to inspect the effect of changed reports.':f.time<1.5?'The attack starts at 1.5 s. The model first receives unmodified reports. Use “Attack starts” and then step through the replay.':'Selected vehicles now report x positions shifted by about 250 m. Physical mobility and radio computation still use the simulator state. The graph model only receives the reports and observable measurements.';
 $('play').textContent=playing?'Pause':'Play';networkMap();
}
function sumoRender(){
 const f=D.sumo.frames[sumoIndex],ctx=$('sumo-map').getContext('2d'),scale=.55,c=425,cy=325;
 const x=v=>c+(v-500)*scale,y=v=>cy-(v-500)*scale;
 ctx.clearRect(0,0,850,640);ctx.fillStyle='#101d2d';ctx.fillRect(0,0,850,640);
 for(let i=0;i<850;i+=50)line(ctx,i,0,i,640,'#182a3f');for(let i=0;i<640;i+=50)line(ctx,0,i,850,i,'#182a3f');
 ctx.fillStyle='#2a3a4e';ctx.fillRect(x(0),cy-21,550,42);ctx.fillRect(c-21,y(1000),42,550);
 line(ctx,x(0),cy,x(450),cy,'#c1b68c',1,[10,9]);line(ctx,x(550),cy,x(1000),cy,'#c1b68c',1,[10,9]);line(ctx,c,y(0),c,y(450),'#c1b68c',1,[10,9]);line(ctx,c,y(550),c,y(1000),'#c1b68c',1,[10,9]);
 text(ctx,'WEST',x(0)-12,cy-35,13,'#7f96ad','center');text(ctx,'EAST',x(1000)+12,cy-35,13,'#7f96ad','center');text(ctx,'NORTH',c,y(1000)-18,13,'#7f96ad','center');text(ctx,'SOUTH',c,y(0)+28,13,'#7f96ad','center');
 f.vehicles.forEach(v=>{const angle=(v.heading-90)*Math.PI/180;ctx.save();ctx.translate(x(v.x),y(v.y));ctx.scale(.55,.55);car(ctx,0,0,v.speed<.1?'#f5cc70':'#57d5cc',angle);ctx.restore()});
 text(ctx,'Cyan: moving     Gold: stopped',30,610,14,'#a9b9cb');
 $('sumo-clock').textContent=`${f.time.toFixed(1)} s`;$('sumo-timeline').value=sumoIndex;$('sumo-play').textContent=sumoPlaying?'Pause traffic':'Play traffic';
 $('sumo-data').innerHTML=[['Source CSV rows',D.sumo.rows.toLocaleString()],['Vehicles in recording',D.sumo.vehicle_count],['Visible now',f.vehicles.length],['Stopped now',f.vehicles.filter(v=>v.speed<.1).length],['Recording ends',`${D.sumo.frames.at(-1).time.toFixed(1)} s`]].map(([a,b])=>`<dt>${a}</dt><dd>${b}</dd>`).join('');
}
function results(){
 const rows=[['Fixed rules',D.simple_baseline],['GNN + GRU',D.metrics.baseline.test],['TrustGraph',D.metrics.trustgraph.test]];
 const table=`<table><thead><tr><th>Method</th><th>Link F1 ↑</th><th>Link AUROC ↑</th><th>Attack F1 ↑</th><th>Load MAE ↓</th></tr></thead><tbody>${rows.map(([n,m])=>`<tr><td>${n}</td><td>${fmt(m.link.f1,3)}</td><td>${fmt(m.link.auroc,3)}</td><td>${fmt(m.attack.f1,3)}</td><td>${fmt(m.load.mae,3)}</td></tr>`).join('')}</tbody></table>`;
 const chart=(title,key,field)=>`<div class="chart"><h3>${title}</h3>${rows.map(([n,m],i)=>`<div class="bar-row"><span>${n}</span><div class="bar-track"><div class="bar-fill" style="width:${100*(m[key][field]??0)}%;background:${['#f5cc70','#879ab6','#57d5cc'][i]}"></div></div><span>${fmt(m[key][field],3)}</span></div>`).join('')}<p class="small muted">Axis 0–1. Same held-out runs and valid link labels.</p></div>`;
 const sum=D.network_results.summary.filter(r=>r.attack_fraction===.3);
 $('results-content').innerHTML=`<div class="results-summary"><div><strong>12</strong><span>Independent data runs</span></div><div><strong>7 / 2 / 3</strong><span>Train / validation / test</span></div><div><strong>36</strong><span>Closed-loop policy runs</span></div></div><h2>Prediction quality</h2><p>Frozen checkpoints from the initial eight-epoch experiment. Simple rules provide a useful reference without training.</p>${table}<div class="chart-grid">${chart('Serving-link ranking','link','auroc')}${chart('Active attack detection','attack','f1')}</div><p class="detail-note">Fixed rules: current SINR for link risk, current load for next-second load, and motion inconsistency for active attacks. Neural scores use a 0.5 classification threshold. These tests do not establish a consistent trust-aware advantage. Strong simple-rule results are evidence that the synthetic setup needs harder, more realistic evaluation.</p><h2>Closed-loop behavior at 30% attacked vehicles</h2><table><thead><tr><th>Policy</th><th>Delivery proxy ↑</th><th>Handovers</th><th>Overload cell-seconds ↓</th></tr></thead><tbody>${sum.map(r=>`<tr><td>${esc(r.policy)}</td><td>${fmt(r.delivery_proxy.mean,3)} ± ${fmt(r.delivery_proxy.std,3)}</td><td>${fmt(r.handovers.mean,1)} ± ${fmt(r.handovers.std,1)}</td><td>${fmt(r.overloaded_cell_seconds.mean,2)} ± ${fmt(r.overloaded_cell_seconds.std,2)}</td></tr>`).join('')}</tbody></table><p class="small muted">Mean ± sample standard deviation over three matched seeds. Delivery is a synthetic proxy, not measured packet delivery ratio. Handovers are applied in the toy environment. Smaller counts alone do not imply better service.</p><h2>Evidence provenance</h2><p class="results-source">Checkpoint SHA256: ${D.provenance.checkpoint_sha256}</p><p class="small muted">Replay seed ${D.provenance.demo_seed}: ${D.provenance.seed_selection}. Full numeric evidence is in evidence.json. Training and held-out metrics remain in outputs/demo.</p>`;
}
function selectTab(name){tab=name;playing=false;sumoPlaying=false;document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id===name));document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));$('page-title').textContent={network:'Predict. Inspect. Replay.',sumo:'The traffic foundation',results:'Initial evidence',architecture:'What works. What comes next.'}[name];if(name==='network')render();if(name==='sumo')sumoRender()}
function seek(index){playing=false;frameIndex=Math.max(0,Math.min(replay().frames.length-1,index));render()}
function init(){
 if(!D)throw new Error('Missing data.js. Rebuild with python -m trustgraph midsem.');
 selected=D.replays.attack.frames.at(-1).truth.attack.findIndex(v=>v>0);if(selected<0)selected=0;
 $('vehicle').innerHTML=replay().vehicle_ids.map((id,i)=>`<option value="${i}">${id}</option>`).join('');$('vehicle').value=selected;
 $('vehicle').onchange=e=>{selected=+e.target.value;render()};$('truth').onchange=render;
 $('scenario').onchange=e=>{scenario=e.target.value;playing=false;$('event-note').textContent='Same seed and timestamp; outcomes may diverge after policy decisions.';render()};
 $('timeline').max=replay().frames.length-1;$('timeline').oninput=e=>seek(+e.target.value);
 $('play').onclick=()=>{if(frameIndex===replay().frames.length-1)frameIndex=0;playing=!playing;render()};$('reset').onclick=()=>seek(0);$('speed').onchange=e=>speed=+e.target.value;
 $('before-attack').onclick=()=>seek(12);$('attack-onset').onclick=()=>{if(scenario==='clean'){$('event-note').textContent='Clean scenario has no injected attack.';return}seek(15)};
 $('next-handover').onclick=()=>{const event=replay().events.find(e=>e.step>frameIndex);if(event){selected=event.vehicle;$('vehicle').value=selected;seek(event.step);$('event-note').textContent='Command applies now; next frame shows the updated serving cell.'}else{$('event-note').textContent='No later handover. Restart to review earlier events.'}};
 $('sumo-timeline').max=D.sumo.frames.length-1;$('sumo-timeline').oninput=e=>{sumoPlaying=false;sumoIndex=+e.target.value;sumoRender()};$('sumo-play').onclick=()=>{if(sumoIndex===D.sumo.frames.length-1)sumoIndex=0;sumoPlaying=!sumoPlaying;sumoRender()};$('sumo-reset').onclick=()=>{sumoPlaying=false;sumoIndex=0;sumoRender()};
 $('fullscreen').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else document.documentElement.requestFullscreen().catch(()=>{})};
 document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>selectTab(b.dataset.tab));
 document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName))return;if(e.code==='Space'&&tab==='network'){e.preventDefault();$('play').click()}if(e.code==='ArrowRight'&&tab==='network'){e.preventDefault();seek(frameIndex+1)}if(e.code==='ArrowLeft'&&tab==='network'){e.preventDefault();seek(frameIndex-1)}});
 $('provenance').textContent=`Seed ${D.provenance.demo_seed} · Checkpoint ${D.provenance.checkpoint_sha256.slice(0,12)}`;
 results();render();sumoRender();
 let last=performance.now(),networkElapsed=0,sumoElapsed=0;
 function tick(now){const elapsed=Math.min(250,now-last);last=now;if(playing){networkElapsed+=elapsed*speed;while(networkElapsed>=D.config.dt*1000){networkElapsed-=D.config.dt*1000;if(frameIndex<replay().frames.length-1)frameIndex++;else{playing=false;break}}render()}else networkElapsed=0;if(sumoPlaying){sumoElapsed+=elapsed*2;while(sumoElapsed>=500){sumoElapsed-=500;if(sumoIndex<D.sumo.frames.length-1)sumoIndex++;else{sumoPlaying=false;break}}sumoRender()}else sumoElapsed=0;requestAnimationFrame(tick)}requestAnimationFrame(tick);
 window.demoState=()=>({tab,scenario,frameIndex,selected,playing,sumoIndex,sumoPlaying});
}
try{init()}catch(error){document.querySelector('main').innerHTML=`<div class="error">${esc(error.message)}</div>`;console.error(error)}
