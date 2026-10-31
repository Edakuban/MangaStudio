let flowCurrent=null,flowPreviewTimer;
const flowDrafts=new Map();
const flowLayouts=[['balanced','Variable Rechtecke'],['dynamic','Diagonal / Bewegung'],['cinematic','Filmische Streifen'],['full_bleed','Randlose Einzelseite']];
const flowCompositions=[['balanced','Ausgewogen'],['wide_start','Großer breiter Auftakt'],['tall_start','Großer hoher Auftakt'],['wide_finish','Großes Schlussbild']];
const flowTurns=[['none','Kein geschützter Umblättereffekt'],['setup','Spannungsaufbau vor dem Umblättern'],['reveal','Enthüllung nach dem Umblättern'],['cliffhanger','Kapitel-Cliffhanger']];
function flowSpreadHTML(groups,chapterId){
 return groups.map((spread,i)=>`<div class="flow-spread"><div class="flow-spread-label">${i===0?'Seitenlage':'Doppelseite'}</div>${['left','right'].map(side=>{const p=spread[side];return `<div class="flow-spread-side">${p?`<div class="preview-top"><span>SEITE ${p.number}</span><small>${p.chapter_id===chapterId?'Aktuelles Kapitel':'Nachbarkapitel'}</small></div><div class="flow-paper">${paperHTML(p,false,true)}</div>${p.turn&&p.turn!=='none'?`<p class="flow-turn">${e(flowTurns.find(t=>t[0]===p.turn)?.[1])}</p>`:''}`:'<div class="flow-empty-page">Buchbeginn oder benachbarte Seite</div>'}</div>`}).join('')}</div>`).join('');
}
function pageFlowBannerHTML(){
 const state=S.chapter?.page_flow;if(!state)return '';
 const pending=state.proposal?.status==='pending',active=state.active;
 if(!pending&&!active)return '';
 return `<div class="page-flow-banner"><b>Kapitel-Seitenablauf</b>${pending?`<p>Ein Seitenvorschlag wartet auf deine Prüfung.${state.proposal.stale?' Storyboard oder Seitenlage wurde seitdem geändert.':''}</p><button class="small primary" data-flow-action="open" ${busy()?'disabled':''}>Seitenvorschlag prüfen</button>`:''}${active?`<p>${active.enabled===false?'Gespeicherter Seitenplan ist deaktiviert.':active.structure_changed?'Die Panelreihenfolge hat sich geändert. Der aktive Plan passt nicht mehr; bitte neu planen.':`Aktiver Seitenplan: ${active.plan.pages.length} Seiten. Er hat Vorrang vor den Szenen-Layouts.`}</p>${active.context_changed||active.content_changed?'<p class="note">Inhalt oder Seitenlage wurde seit der Übernahme geändert. Seitenrhythmus und Umblättereffekte erneut prüfen.</p>':''}${active.errors?.length?`<div class="warning">${active.errors.map(e).join('<br>')}</div>`:''}<div class="action-row"><button class="small" data-flow-action="edit" ${busy()||active.structure_changed?'disabled':''}>Seitenplan anpassen</button><button class="small quiet" data-flow-action="${active.enabled===false?'restore':'reset'}" ${busy()?'disabled':''}>${active.enabled===false?'Gespeicherten Seitenplan wieder aktivieren':'Szenen-Layouts verwenden'}</button></div>`:''}</div>`;
}
async function startPageFlow(){
 await savePlan();await post(`/api/chapters/${S.chapter.id}/page-flow`);await refreshProject();
 toast('KI plant die Seitenfolge. Der aktuelle Seitenablauf bleibt bis zur Übernahme erhalten.');
}
async function openPageFlow(){
 await savePlan();const data=await api(`/api/chapters/${S.chapter.id}/page-flow`);
 if(!data.proposal){toast('Zuerst einen Seitenablauf mit KI planen.');return}
 const key=S.chapter.id+':'+data.proposal.id;
 let draft=flowDrafts.get(key);
 if(!draft){draft={plan:structuredClone(data.proposal.plan),version:0,changed:false};flowDrafts.set(key,draft)}
 flowCurrent={...draft,key,data,chapterId:S.chapter.id,tab:'proposed',pending:false};
 modal('Seitenablauf prüfen', '<div id="pageFlowEditor"></div>');$('#modal').classList.add('page-flow-mode');renderPageFlow();
 if(draft.changed)requestFlowPreview();
}
function flowSelect(field,value,choices,index,disabled=''){
 return `<select data-flow-field="${field}" data-flow-page="${index}" ${disabled}>${choices.map(([v,l])=>`<option value="${v}" ${value===v?'selected':''}>${l}</option>`).join('')}</select>`;
}
function renderPageFlow(){
 const f=flowCurrent,holder=$('#pageFlowEditor');if(!f||!holder)return;
 const openRows=new Set(Array.from(holder.querySelectorAll?.('.flow-page-controls>details[open]')||[]).map(el=>+el.dataset.flowControlpage));
 const scroll=$('#modal')?.scrollTop;
 const d=f.data,proposal=d.proposal,pending=proposal?.status==='pending',errors=d.errors||[];
 const labels=new Map(allPanels().map((p,i)=>[p.id,{number:i+1,description:p.description}]));
 holder.innerHTML=`<p class="note">Die Reihenfolge von Handlung und Dialogen bleibt erhalten. Jede Seite enthält ein bis fünf aufeinanderfolgende Panels. Seite 1 ist eine Auftaktseite; 2/3, 4/5 usw. sind gemeinsam sichtbar. Nachbarseiten werden zur Orientierung mitgezeigt.</p><p>${e(f.plan.summary)}</p><div class="toolbar"><button data-flow-tab="current" ${f.tab==='current'?'class="primary"':''}>Bisher (${d.current_pages.length} Seiten)</button><button data-flow-tab="proposed" ${f.tab==='proposed'?'class="primary"':''}>Vorschlag (${d.proposed_pages.length} Seiten)</button><button data-flow-action="apply" ${!pending||proposal.stale||errors.length||f.pending||S.dirty||busy()?'disabled':''}>Seitenablauf übernehmen</button><button data-flow-action="dismiss" ${!pending||busy()?'disabled':''}>Vorschlag verwerfen</button></div>${proposal.stale?'<div class="warning">Der Vorschlag ist veraltet. Bitte einen neuen Seitenablauf planen lassen.</div>':''}${errors.length?`<div class="warning">${errors.map(e).join('<br>')}</div>`:''}${d.page_shift?`<p class="note">Nachfolgende Kapitel verschieben sich um ${d.page_shift>0?'+':''}${d.page_shift} Seiten. Deren Umblättereffekte danach erneut prüfen.</p>`:''}${f.pending?'<p class="note">Vorschau wird berechnet …</p>':''}<div class="flow-page-controls">${f.plan.pages.map((page,i)=>`<details data-flow-controlpage="${i}" ${openRows.has(i)?'open':''}><summary>Seite ${d.start_page+i} · ${page.panels.length} Panels · ${e(flowLayouts.find(l=>l[0]===page.layout)?.[1])}</summary><p>${e(page.reason)}</p><div class="row"><label>Layout${flowSelect('layout',page.layout,flowLayouts,i)}</label><label>Größenbetonung${flowSelect('composition',page.composition,flowCompositions,i,page.layout!=='balanced'?'disabled':'')}</label></div><label>Umblätterfunktion${flowSelect('turn',page.turn,flowTurns,i)}</label><label>Begründung<textarea data-flow-field="reason" data-flow-page="${i}" maxlength="600" rows="2">${e(page.reason)}</textarea></label><ol>${page.panels.map((id,k)=>`<li><b>Panel ${labels.get(id)?.number||'?'}</b>: ${e(labels.get(id)?.description||'Nicht mehr vorhanden')}${k?` <button class="small quiet" data-flow-split="${i}" data-flow-at="${k}">Ab hier neue Seite</button>`:''}</li>`).join('')}</ol><div class="action-row"><button class="small" data-flow-boundary="first-prev" data-flow-page="${i}" ${i===0?'disabled':''}>Erstes Panel zur vorherigen Seite</button><button class="small" data-flow-boundary="last-next" data-flow-page="${i}">Letztes Panel auf folgende Seite</button><button class="small quiet" data-flow-merge="${i}" ${i+1>=f.plan.pages.length||page.panels.length+(f.plan.pages[i+1]?.panels.length||0)>5?'disabled':''}>Mit nächster Seite verbinden</button></div></details>`).join('')}</div>${d.lettering_warnings?.length?`<details class="warning"><summary>Sprechblasen nach Layoutänderung prüfen (${d.lettering_warnings.length})</summary>${d.lettering_warnings.map(e).join('<br>')}</details>`:''}<div class="page-flow-preview">${flowSpreadHTML(f.tab==='current'?d.current_spreads||[]:d.proposed_spreads||[],f.chapterId)}</div><p class="note">Vorschlagsänderungen werden erst mit „Seitenablauf übernehmen“ gespeichert. Bildausschnitte und Sprechblasen nach der Übernahme prüfen.</p>`;
 if(scroll!=null)$('#modal').scrollTop=scroll;
}
function flowChanged(){
 const f=flowCurrent;if(!f)return;f.changed=true;f.pending=true;
 flowDrafts.set(f.key,{plan:f.plan,version:f.version,changed:true});renderPageFlow();requestFlowPreview();
}
function requestFlowPreview(){
 clearTimeout(flowPreviewTimer);const f=flowCurrent;if(!f)return;
 const version=++f.version;
 flowPreviewTimer=setTimeout(()=>run(async()=>{
  try{const data=await post(`/api/chapters/${f.chapterId}/page-flow/preview`,f.plan);
   if(flowCurrent!==f||version!==f.version)return;f.data=data;f.pending=false;renderPageFlow();
  }catch(err){f.pending=false;renderPageFlow();throw err}
 }),200);
}
function splitFlowPage(index,at){
 const pages=flowCurrent.plan.pages,page=pages[index];if(!page||at<1||at>=page.panels.length)return;
 const rest=page.panels.splice(at);page.turn='none';
 pages.splice(index+1,0,{...structuredClone(page),panels:rest,reason:'Manuell geteilte Seite.'});flowChanged();
}
function mergeFlowPages(index){
 const pages=flowCurrent.plan.pages,a=pages[index],b=pages[index+1];if(!a||!b||a.panels.length+b.panels.length>5)return;
 a.panels.push(...b.panels);a.turn='none';if(a.layout==='full_bleed')a.layout='balanced';
 pages.splice(index+1,1);flowChanged();
}
function moveFlowBoundary(index,mode){
 const pages=flowCurrent.plan.pages,page=pages[index];if(!page)return;
 if(mode==='first-prev'){
  const previous=pages[index-1];if(!previous||previous.panels.length>=5)return;
  previous.panels.push(page.panels.shift());previous.turn='none';if(previous.layout==='full_bleed')previous.layout='balanced';
 }else{
  if(!pages[index+1])pages.push({...structuredClone(page),panels:[],turn:'none',reason:'Manuell ergänzte Seite.'});
  const next=pages[index+1];if(next.panels.length>=5)return;
  next.panels.unshift(page.panels.pop());next.turn='none';if(next.layout==='full_bleed')next.layout='balanced';
 }
 page.turn='none';if(!page.panels.length)pages.splice(index,1);flowChanged();
}
async function decidePageFlow(action){
 if(S.dirty)throw Error('Bitte Storyboard-Änderungen zuerst speichern.');
 const id=S.chapter.id,body={action};
 if(action==='apply'||action==='dismiss'){body.proposal_id=flowCurrent.data.proposal.id;if(action==='apply')body.plan=flowCurrent.plan}
 const chapter=await post(`/api/chapters/${id}/page-flow/decide`,body);
 closeModal();S.chapter=chapter;S.scenes=structuredClone(chapter.scenes);S.book=await api(`/api/projects/${S.book.id}`);render();renderRail();
 toast(action==='apply'?'Seitenablauf übernommen. Bildausschnitte und Sprechblasen prüfen.':action==='dismiss'?'Seitenvorschlag verworfen.':'Seitenablauf umgeschaltet.');
}
document.addEventListener('click',event=>{
 const t=event.target.closest?.('[data-flow-action],[data-flow-tab],[data-flow-split],[data-flow-merge],[data-flow-boundary]');if(!t||t.disabled)return;
 run(async()=>{
  if(t.dataset.flowTab){flowCurrent.tab=t.dataset.flowTab;renderPageFlow();return}
  if(t.dataset.flowSplit!=null){splitFlowPage(+t.dataset.flowSplit,+t.dataset.flowAt);return}
  if(t.dataset.flowMerge!=null){mergeFlowPages(+t.dataset.flowMerge);return}
  if(t.dataset.flowBoundary){moveFlowBoundary(+t.dataset.flowPage,t.dataset.flowBoundary);return}
  const a=t.dataset.flowAction;t.disabled=true;
  try{if(a==='open')await openPageFlow();else if(a==='edit'){await savePlan();const ch=await post(`/api/chapters/${S.chapter.id}/page-flow/edit`);S.chapter=ch;await openPageFlow()}else await decidePageFlow(a)}finally{t.disabled=false}
 });
});
document.addEventListener('change',event=>{
 const t=event.target;if(!t.dataset.flowField||!flowCurrent)return;
 const i=+t.dataset.flowPage,page=flowCurrent.plan.pages[i];page[t.dataset.flowField]=t.value;
 if(t.dataset.flowField==='layout'){
  if(page.layout!=='balanced')page.composition='balanced';
  if(page.layout==='full_bleed'&&page.panels.length>1){
   const ids=page.panels.slice();page.panels=[ids[0]];page.turn='none';
   flowCurrent.plan.pages.splice(i+1,0,...ids.slice(1).map(id=>({...structuredClone(page),panels:[id]})));
  }
 }
 flowChanged();
});
