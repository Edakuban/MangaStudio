/* Vector lettering uses the same point geometry and line breaks as the PDF exporter. */
let previewTimer, previewVersion=0, bubbleDrag=null;
function invalidatePagePreview(){clearTimeout(previewTimer);previewVersion++}
function bubbleFrame(panelId,index){
 for(const page of S.chapter?.pages||[]){const p=page.panels.find(p=>p.id===panelId);if(p)return {frame:p.lettering?.bubbles.find(b=>b.index===index),lettering:p.lettering}}
 return {};
}
function bubbleControls(b,i){
 const {frame,lettering}=bubbleFrame(S.selected,i);
 const percent=(key,fallback)=>Math.round(100*(b[key]??(frame&&lettering?frame[key]/lettering[key==='x'||key==='width'?'width':'height']:fallback)));
 return `<div class="row"><div><label>Blasenform</label><select data-bfield="shape" data-bi="${i}" ${busy()?'disabled':''}>${[['speech','Sprache'],['thought','Gedanke'],['whisper','Flüstern'],['shout','Schreien']].map(([v,l])=>`<option value="${v}" ${(b.shape||'speech')===v?'selected':''}>${l}</option>`).join('')}</select></div><div><label>Schriftgröße (pt)</label><input type="number" min="8" max="18" step=".5" data-bfield="font_size" data-bi="${i}" value="${b.font_size||10}" ${busy()?'disabled':''}></div></div><div class="bubble-position-grid">${[['x','Links',.06],['y','Oben',.05],['width','Breite',.85],['height','Höhe',.25]].map(([key,label,fallback])=>`<label>${label} (%)<input type="number" min="${key==='width'?8:key==='height'?3:0}" max="100" step="1" data-bfield="${key}" data-bi="${i}" data-percent="true" value="${percent(key,fallback)}" ${busy()?'disabled':''}></label>`).join('')}</div><label class="checkline"><input type="checkbox" data-bfield="show_tail" data-bi="${i}" ${b.show_tail!==false?'checked':''} ${busy()?'disabled':''}>Zipfel / Gedankenpunkte anzeigen</label><div class="action-row"><button class="small" data-action="edit-lettering" data-bi="${i}" ${busy()?'disabled':''}>Auf Seite bearbeiten</button><button class="small quiet" data-action="reset-bubble" data-bi="${i}" ${busy()?'disabled':''}>Position automatisch</button></div>`;
}
function updateBubbleField(t,p){
 const b=p.bubbles[+t.dataset.bi],key=t.dataset.bfield;
 if(['x','y','width','height'].includes(key)){
  const {frame,lettering}=bubbleFrame(p.id,+t.dataset.bi),fallback={x:.05,y:.05,width:.7,height:.2};
  for(const k of ['x','y','width','height'])if(b[k]==null)b[k]=frame&&lettering?frame[k]/lettering[k==='x'||k==='width'?'width':'height']:fallback[k];
 }
 let value=t.type==='checkbox'?t.checked:t.type==='number'?Number(t.value):t.value;
 if(t.dataset.percent){value=value/100;if(!Number.isFinite(value))return;value=Math.max(key==='width' ? .08 : key==='height' ? .025 : 0,Math.min(1,value))}
 if(key==='font_size')value=Math.max(8,Math.min(18,value));
 b[key]=value;
 if(key==='side')b.x=null;if(key==='vertical')b.y=null;
 if(['x','width'].includes(key)&&b.x!=null&&b.width!=null)b.x=Math.min(b.x,1-b.width);
 if(['y','height'].includes(key)&&b.y!=null&&b.height!=null)b.y=Math.min(b.y,1-b.height);
 dirty();renderPreview();requestPagePreview();
}
function svgLettering(original,p){
 const l=original.lettering;if(!l)return '';
 const selection=S.letteringSelection;
 return `<svg class="lettering-svg" data-letter-panel="${e(p.id)}" viewBox="0 0 ${l.width} ${l.height}" xmlns="http://www.w3.org/2000/svg" aria-label="Sprechblasen bearbeiten">${l.bubbles.filter(g=>p.bubbles[g.index]).map(g=>{
 const b=p.bubbles[g.index],x=(b.x??g.x/l.width)*l.width,y=(b.y??g.y/l.height)*l.height,w=(b.width??g.width/l.width)*l.width,h=(b.height??g.height/l.height)*l.height;
 const sx=w/g.width,sy=h/g.height,active=selection?.panelId===p.id&&selection.index===g.index;
 const path=`M ${g.points.map(pt=>pt.join(' ')).join(' L ')} Z`;
 return `<g class="letter-bubble ${active?'active':''}" data-letter-index="${g.index}" role="button" aria-label="Sprechblase ${g.index+1} ${e(b.speaker||'')}" tabindex="0"><g transform="translate(${x-g.x*sx} ${y-g.y*sy}) scale(${sx} ${sy})"><path d="${path}" fill="white" stroke="#222" stroke-width=".75" ${g.shape==='whisper'?'stroke-dasharray="2 2"':''}/>${g.thought_dots.map(d=>`<circle cx="${d[0]}" cy="${d[1]}" r="${d[2]}" fill="white" stroke="#222" stroke-width=".7"/>`).join('')}<svg x="${g.x+g.width*.13}" y="${g.y+g.height*.14}" width="${g.width*.74}" height="${g.height*.72}" overflow="hidden"><text text-anchor="middle" fill="#111" font-family="Arial, sans-serif" font-size="${g.font_size}">${g.lines.map((line,i)=>`<tspan x="${g.width*.37}" y="${g.text_y-(g.y+g.height*.14)+i*g.font_size*1.24}">${e(line)}</tspan>`).join('')}</text></svg></g>${active&&!busy()?`<rect class="bubble-selection" x="${x}" y="${y}" width="${w}" height="${h}"/><circle class="bubble-handle" data-bubble-handle="resize" cx="${x+w}" cy="${y+h}" r="4"/>${g.tail?`<circle class="bubble-handle tail-handle" data-bubble-handle="tail" cx="${b.tail_x!=null?b.tail_x*l.width:g.tail[0]}" cy="${b.tail_y!=null?b.tail_y*l.height:g.tail[1]}" r="4"/>`:''}`:''}</g>`;
 }).join('')}${l.caption?`<g class="letter-caption"><rect x="${l.caption.x}" y="${l.caption.y}" width="${l.caption.width}" height="${l.caption.height}" fill="white" stroke="#222" stroke-width=".7"/><text fill="#111" font-family="Arial, sans-serif" font-size="9">${l.caption.lines.map((line,i)=>`<tspan x="${l.caption.x+6}" y="${l.caption.y+15+i*11.16}">${e(line)}</tspan>`).join('')}</text></g>`:''}</svg>`;
}
function pageIssues(page){return page.panels.flatMap(p=>(p.lettering?.issues||[]).map(issue=>`Panel ${p.order}: ${issue}`))}
function letteringWarnings(page){const issues=pageIssues(page);return issues.length?`<div class="warning">${issues.map(e).join('<br>')}<br>Bitte vor dem fertigen PDF-Export korrigieren.</div>`:''}
function refreshLetteringCanvas(){
 const holder=$('#letteringCanvas');if(!holder||!S.chapter?.pages.length)return;
 const page=S.chapter.pages[Math.max(0,Math.min(S.page,S.chapter.pages.length-1))];
 holder.innerHTML=letteringWarnings(page)+paperHTML(page,false);
}
function openLetteringEditor(index){
 S.letteringSelection={panelId:S.selected,index};
 modal('Sprechblasen auf der Seite bearbeiten',`<p class="note">Blase ziehen · Eckpunkt: Größe · goldener Punkt: Zipfel zum Sprecher ziehen. Reihenfolge der Dialoge im Panel beachten. Anschließend Änderungen speichern.</p><div class="toolbar"><button data-action="prev-page">← Vorherige Seite</button><button data-action="next-page">Nächste Seite →</button><button data-action="close-modal">Fertig</button></div><div id="letteringCanvas"></div>`);
 $('#modal').classList.add('lettering-mode');refreshLetteringCanvas();
}
function requestPagePreview(){
 if(!S.chapter||!S.book||bubbleDrag)return;
 clearTimeout(previewTimer);const version=++previewVersion,chapterId=S.chapter.id;
 previewTimer=setTimeout(()=>run(async()=>{
  const result=await post(`/api/chapters/${chapterId}/preview`,{revision:S.chapter.revision,scenes:S.scenes});
  if(version!==previewVersion||chapterId!==S.chapter?.id)return;
  S.chapter.pages=result.pages;S.chapter.page_spreads=result.page_spreads;renderPreview();if(S.view==='pages')renderGallery();refreshLetteringCanvas();
 }),220);
}
document.addEventListener('pointerdown',event=>{
 const g=event.target.closest?.('[data-letter-index]');if(!g||busy())return;
 const svg=g.closest('svg[data-letter-panel]'),id=svg.dataset.letterPanel,index=+g.dataset.letterIndex;
 const p=allPanels().find(p=>p.id===id),{frame,lettering}=bubbleFrame(id,index);if(!p||!frame)return;
 event.preventDefault();event.stopPropagation();
 S.selected=id;S.letteringSelection={panelId:id,index};
 const b=p.bubbles[index],rect=svg.getBoundingClientRect();
 bubbleDrag={panelId:id,index,handle:event.target.dataset.bubbleHandle||'move',startX:event.clientX,startY:event.clientY,rect,
  x:b.x??frame.x/lettering.width,y:b.y??frame.y/lettering.height,width:b.width??frame.width/lettering.width,height:b.height??frame.height/lettering.height,
  tailX:b.tail_x??(frame.tail?.[0]||0)/lettering.width,tailY:b.tail_y??(frame.tail?.[1]||0)/lettering.height};
 renderEditor();renderPreview();refreshLetteringCanvas();
});
document.addEventListener('pointermove',event=>{
 if(!bubbleDrag)return;event.preventDefault();
 const d=bubbleDrag,p=allPanels().find(p=>p.id===d.panelId),b=p?.bubbles[d.index];if(!b||busy())return;
 const dx=(event.clientX-d.startX)/d.rect.width,dy=(event.clientY-d.startY)/d.rect.height;
 const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
 if(d.handle==='resize'){Object.assign(b,{x:d.x,y:d.y,width:clamp(d.width+dx,.08,1-d.x),height:clamp(d.height+dy,.025,1-d.y)})}
 else if(d.handle==='tail'){b.tail_x=clamp(d.tailX+dx,0,1);b.tail_y=clamp(d.tailY+dy,0,1)}
 else{Object.assign(b,{x:clamp(d.x+dx,0,1-d.width),y:clamp(d.y+dy,0,1-d.height),width:d.width,height:d.height})}
 dirty();renderPreview();refreshLetteringCanvas();
});
function endBubbleDrag(){if(!bubbleDrag)return;bubbleDrag=null;renderEditor();requestPagePreview()}
document.addEventListener('pointerup',endBubbleDrag);
document.addEventListener('pointercancel',endBubbleDrag);
document.addEventListener('click',event=>{
 if(event.target.closest?.('[data-letter-index]')){event.stopImmediatePropagation();return}
 const t=event.target.closest?.('[data-action]');if(!t||t.disabled)return;
 if(t.dataset.action==='edit-lettering')openLetteringEditor(+t.dataset.bi);
 if(t.dataset.action==='reset-bubble'){
  const b=panel()?.bubbles[+t.dataset.bi];if(!b)return;
  for(const key of ['x','y','width','height','tail_x','tail_y'])b[key]=null;
  dirty();requestPagePreview();renderEditor();
 }
});
