const S={books:[],book:null,chapter:null,scenes:[],view:'storyboard',selected:null,page:0,dirty:false,connection:null,settings:null,seenDone:new Set()};
const $=s=>document.querySelector(s);
const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const asset=p=>'/assets/'+p.split('/').map(encodeURIComponent).join('/');
const uuid=()=>crypto.randomUUID().replaceAll('-','');
const busy=()=>S.book?.jobs.some(j=>['running','queued'].includes(j.state));
const allPanels=()=>S.scenes.flatMap(s=>s.panels);
const panel=()=>allPanels().find(p=>p.id===S.selected);
let toastTimer;
function toast(text,error=false){const t=$('#toast');t.textContent=text;t.className=error?'error':'';t.style.display='block';clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.style.display='none',error?9500:4500)}
async function api(url,options={}){const isForm=options.body instanceof FormData;const response=await fetch(url,{...options,headers:{...(!isForm&&options.body?{'Content-Type':'application/json'}:{}),...options.headers}});let value;try{value=await response.json()}catch{throw Error('Die App hat keine lesbare Antwort geliefert.')}if(!response.ok){let detail=value.detail;if(Array.isArray(detail))detail=detail.map(d=>`${d.loc?.slice(1).join('.')}: ${d.msg}`).join('; ');throw Error(detail||'Aktion fehlgeschlagen.')}return value}
const post=(url,data={})=>api(url,{method:'POST',body:JSON.stringify(data)});
async function run(fn){try{await fn()}catch(err){toast(err.message,true)}}
function checkDirty(){return !S.dirty||confirm('Du hast ungespeicherte Storyboard-Änderungen. Trotzdem wechseln?')}
function modal(title,html){$('#modal').classList?.remove('lettering-mode','page-flow-mode');$('#modalContent').innerHTML=`<div class="dialog-head"><h2>${e(title)}</h2><button class="icon" data-action="close-modal" aria-label="Schließen">×</button></div>${html}`;$('#modal').showModal()}
function closeModal(){$('#modal').classList.remove('lettering-mode','page-flow-mode');$('#modal').close()}
async function loadBooks(){S.books=await api('/api/projects');renderRail()}
async function openBook(id){if(!checkDirty())return;S.dirty=false;S.book=await api('/api/projects/'+id);S.chapter=null;S.scenes=[];S.selected=null;S.page=0;S.view='storyboard';S.book.jobs.filter(j=>j.state==='done').forEach(j=>S.seenDone.add(j.id));if(S.book.chapters.length)await loadChapter(S.book.chapters[0].id,false);render();renderRail();localStorage.setItem('manga-book',id)}
async function loadChapter(id,ask=true){invalidatePagePreview();if(ask&&!checkDirty())return;S.chapter=await api('/api/chapters/'+id);S.scenes=structuredClone(S.chapter.scenes);S.dirty=false;S.selected=allPanels()[0]?.id||null;S.page=0;render();renderRail()}
function renderRail(){
 $('#bookList').innerHTML=S.books.length?S.books.map(b=>`<div class="book-item ${S.book?.id===b.id?'active':''}" data-action="book" data-id="${e(b.id)}"><span class="book-glyph">▤</span><span title="${e(b.title)}">${e(b.title)}</span></div>`).join(''):'<small>Noch kein Buch importiert.</small>';
 $('#bookList').innerHTML+='<button class="small quiet" data-action="deleted-books">Gelöschte Bücher</button>';
 $('#chapterNav').innerHTML=S.book?`<div class="chapter-side"><div class="rail-label">KAPITEL</div>${S.book.chapters.map(c=>`<div class="chapter-link ${S.chapter?.id===c.id?'active':''}" data-action="chapter" data-id="${e(c.id)}"><b>${String(c.position).padStart(2,'0')}</b><span>${e(c.title)}<br><small>${c.panels?`${c.images}/${c.panels} Bilder`:'Noch kein Storyboard'}</small></span></div>`).join('')}</div>`:'';
}
function welcome(){return `<section class="welcome"><div class="welcome-top"><div><div class="eyebrow">VOM MANUSKRIPT ZUR MANGA-SEITE</div><h1>Geschichten verdienen<br>eine <em>zweite Gestalt.</em></h1><p>Mach aus deinem Buch einen Manga. Plane Szenen, bewahre die Identität deiner Charaktere und erzähle mit Panels, die ihrem eigenen Rhythmus folgen.</p><div class="actions"><button class="primary" data-action="upload-book">＋ Buch importieren</button><button data-action="demo">Layout-Demo öffnen ↗</button></div><small>DOCX, TXT oder Markdown · Alles lokal gespeichert</small></div><div class="book-art" aria-hidden="true"><div class="art-heading"><small>STORY / INK / SEQUENCE</small>Zwischen<br>den Zeilen.</div><div class="art-panels"><div></div><div></div></div><div class="art-bottom">DEIN BUCH. DEIN MANGA.</div></div></div><div class="workflow-cards">${[['01','Die Geschichte','Kapitel einlesen und Szenen in ihrer erzählerischen Reihenfolge planen.'],['02','Die Besetzung','Referenzbilder und Beschreibungen für wiedererkennbare Charaktere.'],['03','Die Panels','Einzelne Bilder prüfen, bearbeiten und gezielt neu generieren.'],['04','Die Seiten','Variable Seitenlayouts, saubere Sprechblasen und ein Manga-PDF.']].map(([n,t,d])=>`<div class="workflow-card"><b>${n}</b><h3>${t}</h3><p>${d}</p></div>`).join('')}</div></section>`}
function render(){
 if(!S.book){$('#content').innerHTML=welcome();return}
 const chapters=S.book.chapters,panels=chapters.reduce((n,c)=>n+c.panels,0),images=chapters.reduce((n,c)=>n+c.images,0);
 $('#content').innerHTML=`<div class="book-header"><div><div class="eyebrow">${S.book.demo?'LAYOUT-DEMO · KEINE KI-BILDER':'DEIN MANGA-PROJEKT'}</div><h1>${e(S.book.title)}</h1><p>${chapters.length} Kapitel · ${S.book.direction==='rtl'?'Japanische Leserichtung ←':'Westliche Leserichtung →'} · ${S.book.monochrome?'Schwarzweiß':'Farbe'}</p></div><div class="header-actions"><button data-action="book-settings">Stil & Leserichtung</button><button class="primary" data-action="export">PDF exportieren ↗</button></div></div><div class="tabs">${[['storyboard','01','Storyboard'],['characters','02','Charaktere'],['pages','03','Seiten'],['source','04','Buchtext']].map(([v,n,label])=>`<button data-action="view" data-view="${v}" class="${S.view===v?'active':''}"><span>${n}</span>${label}</button>`).join('')}</div><div id="jobArea">${jobsHTML()}</div>${S.book.warnings.map(w=>`<div class="warning">${e(w)}</div>`).join('')}<div id="viewContent"></div>`;
 if(S.view==='characters')renderCharacters();else if(S.view==='source')renderSource();else if(S.view==='pages')renderGallery();else renderStoryboard();
}
function jobLabel(j){const kind={plan:'Storyboard',images:'Bilder',dramaturgy:'Dramaturgie',page_flow:'Seitenablauf',book_style:'Bildsprache',character_generate:'Charakterbild',character_render:'Charakterrender',character_autoadd:'Charakter-Autoadd',poses:'Körperhaltungen'}[j.kind]||'Auftrag';const ch=(S.book?.chapters||[]).find(c=>c.id===j.chapter_id);return kind+(ch?' · '+String(ch.position).padStart(2,'0')+' '+ch.title:'')}
function jobsHTML(){return (S.book?.jobs||[]).filter(j=>['running','queued','failed'].includes(j.state)).slice(0,3).map(j=>`<div class="job ${j.state==='failed'?'failed':''}"><div class="job-message"><span><b>${e(jobLabel(j))}</b><br>${j.state==='failed'?'Auftrag angehalten: ':''}${e(j.message)}</span>${j.state==='failed'?`<button class="small" data-action="retry" data-id="${e(j.id)}">Fortsetzen</button>`:`<span>${Math.round(j.progress*100)} %</span>`}</div>${j.state!=='failed'?`<div class="progress"><span style="width:${Math.max(3,j.progress*100)}%"></span></div>`:''}</div>`).join('')}
function chapterBar(){return `<div class="intro-line"><select class="chapter-select" id="chapterSelect" aria-label="Kapitel wählen">${S.book.chapters.map(c=>`<option value="${e(c.id)}" ${S.chapter?.id===c.id?'selected':''}>${e(c.title)}</option>`).join('')}</select><div class="toolbar"><span id="dirtyLabel" class="unsaved">${S.dirty?'● Ungespeichert':''}</span><button data-action="save" ${!S.dirty||busy()?'disabled':''}>Speichern</button><button data-action="plan" ${busy()?'disabled':''}>${S.scenes.length?'Neu planen':'Storyboard mit KI planen'}</button><button data-action="review-dramaturgy" ${!S.scenes.length||busy()?'disabled':''}>Storyboard dramaturgisch prüfen</button><button data-action="plan-page-flow" ${!S.scenes.length||busy()?'disabled':''}>Seitenablauf mit KI planen</button><button data-action="suggest-layout" ${!S.scenes.length||busy()?'disabled':''}>KI-Layout vorschlagen</button><button class="primary" data-action="generate-all" ${!S.scenes.length||busy()?'disabled':''}>Fehlende Bilder erzeugen</button></div></div>`}
function renderStoryboard(){
 if(!S.chapter){$('#viewContent').innerHTML='<div class="empty">Keine Kapitel gefunden.</div>';return}
 $('#viewContent').innerHTML=chapterBar()+`<div class="stats-strip"><div class="stat"><b>${S.scenes.length}</b><small>Szenen</small></div><div class="stat"><b>${allPanels().length}</b><small>Panels</small></div><div class="stat"><b>${S.chapter.pages.length}</b><small>Seiten</small></div><div class="stat"><b>${allPanels().filter(p=>p.image).length}</b><small>Bilder</small></div></div>${pageFlowBannerHTML()}${dramaturgyHTML()}<div class="workspace"><div class="story-column"><div class="sectionbar"><h2>Die Geschichte in Panels</h2><small>VON DER SZENE ZUR SEQUENZ</small></div><div id="sceneList"></div><div id="panelEditor"></div></div><div class="page-column"><div class="sectionbar"><h2>Seitenvorschau</h2><small>B5 · 176 × 250 MM</small></div><div id="pagePreview"></div></div></div>`;
 renderScenes();renderEditor();renderPreview();
}
function renderScenes(){
 let count=0;
 $('#sceneList').innerHTML=S.scenes.length?`<div class="action-row" style="margin-bottom:12px"><button class="small danger-quiet" data-action="clear-storyboard" ${busy()?'disabled':''}>Alle Panels dieses Kapitels löschen</button></div>`+S.scenes.map((scene,i)=>`<section class="scene"><div class="scene-heading"><span class="scene-no">${String(i+1).padStart(2,'0')}</span><div><h3>${e(scene.title)}</h3><small>${e(scene.location||'Ort noch offen')} · ${scene.panels.length} Panels</small></div></div><details class="scene-layout"><summary>Koma-Wari: ${{auto:'Automatisch',balanced:'Ruhige Rechtecke',dynamic:'Dynamisch / diagonal',cinematic:'Filmische Streifen',full_bleed:'Randlose Einzelseiten'}[scene.layout||'auto']}</summary><div class="row"><label>Seitenlayout<select data-scene-field="layout" data-scene-id="${e(scene.id)}" ${busy()?'disabled':''}>${[['auto','Automatisch'],['balanced','Ruhige Rechtecke'],['dynamic','Dynamisch / diagonal'],['cinematic','Filmische Streifen'],['full_bleed','Randlose Einzelseiten']].map(([v,l])=>`<option value="${v}" ${(scene.layout||'auto')===v?'selected':''}>${l}</option>`).join('')}</select></label><label>Rhythmus<select data-scene-field="rhythm" data-scene-id="${e(scene.id)}" ${busy()?'disabled':''}>${[['calm','Ruhig'],['action','Bewegung / Spannung'],['reveal','Enthüllung']].map(([v,l])=>`<option value="${v}" ${(scene.rhythm||'calm')===v?'selected':''}>${l}</option>`).join('')}</select></label></div><p class="note">${e(scene.layout_reason||'Noch kein KI-Vorschlag. Layout manuell wählen oder oben einen Vorschlag anfordern.')}<br>Randlos: jedes Panel dieser Szene bekommt eine eigene Seite.</p></details>${scene.panels.map(p=>{count++;return `<div class="scene-panel ${p.id===S.selected?'selected':''}" data-action="panel" data-id="${e(p.id)}"><div class="thumb">${p.image?`<img src="${asset(p.image)}" alt="Panel ${count}">`:'<div class="mini-silhouette"></div>'}</div><div class="panel-meta"><div class="panel-label">Panel ${String(count).padStart(2,'0')} · ${{wide:'Totale',medium:'Halbnah',close:'Nahaufnahme',detail:'Detail'}[p.shot]}</div><p>${e(p.description)}</p><small>${e(p.emphasis==='splash'?'Ganzseitig':p.emphasis==='wide'?'Breites Panel':p.emphasis==='tall'?'Hochformat':'Automatisches Layout')}${p.bubbles.length?' · '+p.bubbles.length+' Sprechblasen':''}</small></div><span class="panel-state ${p.image?(S.chapter.stale_panels.includes(p.id)?'stale':'ready'):''}" title="${p.image?'Bild vorhanden':'Bild fehlt'}"></span><button class="small danger-quiet" data-action="remove-panel" data-id="${e(p.id)}" aria-label="Panel ${count} löschen" title="${scene.panels.length===1?'Letztes Panel und die leere Szene löschen':'Panel löschen'}" ${busy()?'disabled':''}>Löschen</button></div>`}).join('')}<div class="scene-footer"><button class="quiet small source-link" data-action="evidence" data-id="${e(scene.id)}">↳ Buchstelle · Abs. ${scene.source_start}–${scene.source_end}</button><button class="quiet small" data-action="add-panel" data-id="${e(scene.id)}" ${busy()?'disabled':''}>＋ Panel</button></div><div id="evidence-${e(scene.id)}" hidden class="evidence">${e(scene.source_excerpt)}</div></section>`).join(''):`<div class="empty wide-empty"><div class="empty-mark">描</div><h3>Die erste Szene wartet.</h3><p>Lade zuerst deine Charaktere hoch. Danach plant die lokale Text-KI dieses Kapitel als zusammenhängende Szenen und Panels mit belegten Buchstellen.</p><button class="primary" data-action="plan" ${busy()?'disabled':''}>Storyboard mit KI planen</button><p class="note" style="margin-top:18px">ComfyUI muss laufen. Bilder werden erst nach deinem Klick erzeugt.</p></div>`;
}
function renderEditor(){
 const p=panel();if(!p){$('#panelEditor').innerHTML='';return}
 const disabled=busy()?'disabled':'';
 $('#panelEditor').innerHTML=`<section class="editor"><div class="editor-heading"><h3>Panel bearbeiten</h3><div><button class="small quiet" data-action="move-panel" data-delta="-1" ${disabled}>↑</button><button class="small quiet" data-action="move-panel" data-delta="1" ${disabled}>↓</button></div></div><label>Handlung / Panelbeschreibung</label><textarea data-field="description" maxlength="1200" ${disabled}>${e(p.description)}</textarea><label>Bildanweisung <small>· auf Englisch empfohlen</small></label><textarea data-field="visual_prompt" maxlength="2500" rows="4" ${disabled}>${e(p.visual_prompt)}</textarea><div class="row"><div><label>Einstellungsgröße</label><select data-field="shot" ${disabled}>${[['wide','Totale'],['medium','Halbnah'],['close','Nahaufnahme'],['detail','Detail']].map(([v,l])=>`<option value="${v}" ${p.shot===v?'selected':''}>${l}</option>`).join('')}</select></div><div><label>Gewicht im Seitenlayout</label><select data-field="emphasis" ${disabled}>${[['normal','Automatisch'],['wide','Breit / Atmosphäre'],['tall','Hoch / Figur'],['splash','Ganzseitig / Enthüllung']].map(([v,l])=>`<option value="${v}" ${p.emphasis===v?'selected':''}>${l}</option>`).join('')}</select></div></div><div class="row"><label>Panel-Funktion<select data-field="beat" ${disabled}>${[['establishing','Ort / Überblick'],['action','Handlung'],['reaction','Reaktion'],['detail','Detail'],['reveal','Enthüllung']].map(([v,l])=>`<option value="${v}" ${(p.beat||'action')===v?'selected':''}>${l}</option>`).join('')}</select></label><label>Rahmen<select data-field="border" ${disabled}><option value="framed" ${p.border!=='open'?'selected':''}>Mit Rahmen</option><option value="open" ${p.border==='open'?'selected':''}>Offenes Panel</option></select></label></div><label class="checkline"><input type="checkbox" data-field="page_break_before" ${p.page_break_before?'checked':''} ${disabled}>Neue Seite vor diesem Panel</label><label class="checkline"><input type="checkbox" data-field="page_break_after" ${p.page_break_after?'checked':''} ${disabled}>Seite nach diesem Panel beenden</label><label>Charaktere in diesem Panel</label><div class="checks">${S.book.characters.length?S.book.characters.map(c=>`<label><input type="checkbox" data-character="${e(c.id)}" ${p.characters.includes(c.id)?'checked':''} ${disabled}>${e(c.name)}${c.image?' ◉':''}</label>`).join(''):'<small>Noch keine Charaktere hinterlegt.</small>'}</div><label>Körperhaltung & Aktion <small>· pro Person, Englisch empfohlen</small></label>${p.characters.map(id=>{const c=S.book.characters.find(c=>c.id===id);return c?`<label>${e(c.name)}</label><textarea data-pose-character="${e(id)}" maxlength="800" rows="3" placeholder="z. B. Kneeling, leaning forward, both hands examining the pendant, gaze lowered." ${disabled}>${e(p.character_poses?.[id]||'')}</textarea>`:''}).join('')}<div class="action-row"><button class="small" data-action="generate-poses" ${disabled} ${p.characters.length?'':'disabled'}>Körperhaltungen für dieses Panel ergänzen</button><button class="small quiet" data-action="generate-chapter-poses" ${disabled}>Für ganzes Kapitel ergänzen</button></div><p class="note">Die KI füllt nur leere Felder. Vorgaben gelten für diese Szene und haben Vorrang vor der Pose im Referenzbild. Danach betroffene Bilder neu erzeugen.</p><label>Erzählkasten <small>· optional</small></label><textarea data-field="caption" maxlength="160" rows="2" ${disabled}>${e(p.caption)}</textarea><label>Dialoge <small>· separat gesetzt, nicht ins Bild generiert</small></label>${p.bubbles.map((b,i)=>`<div class="bubble-edit"><div class="row"><input data-bfield="speaker" data-bi="${i}" value="${e(b.speaker)}" placeholder="Sprecher" maxlength="100" aria-label="Sprecher" ${disabled}><select data-bfield="side" data-bi="${i}" aria-label="Horizontale Blasenposition" ${disabled}><option value="right" ${b.side==='right'?'selected':''}>Rechts</option><option value="left" ${b.side==='left'?'selected':''}>Links</option></select></div><label>Vertikale Position</label><select data-bfield="vertical" data-bi="${i}" aria-label="Vertikale Blasenposition" ${disabled}><option value="top" ${(b.vertical||'top')==='top'?'selected':''}>Oben</option><option value="bottom" ${b.vertical==='bottom'?'selected':''}>Unten</option></select><textarea data-bfield="text" data-bi="${i}" maxlength="220" ${disabled}>${e(b.text)}</textarea>${bubbleControls(b,i)}<button class="small quiet" data-action="remove-bubble" data-index="${i}" ${disabled}>Blase entfernen</button></div>`).join('')}${p.bubbles.length<4?`<button class="small quiet" data-action="add-bubble" ${disabled}>＋ Sprechblase</button>`:''}<div class="row"><div><label>Bildfokus horizontal</label><input type="range" data-field="focus_x" min="0" max="1" step=".01" value="${p.focus_x}" ${disabled}></div><div><label>Bildfokus vertikal</label><input type="range" data-field="focus_y" min="0" max="1" step=".01" value="${p.focus_y}" ${disabled}></div></div><div class="action-row"><button class="primary small" data-action="generate-panel" ${disabled}>${p.image?'Bild neu erzeugen':'Bild erzeugen'}</button><button class="small" data-action="upload-panel" ${disabled}>Eigenes Bild hochladen</button><button class="small quiet" data-action="remove-panel" ${disabled}>Panel löschen</button></div><p class="note" style="margin:12px 0 0">Layout-Änderungen werden nach dem Speichern neu berechnet. Charakterreferenzen verbessern Wiedererkennbarkeit, garantieren aber keine identischen Gesichter.</p></section>`;
}
function paperHTML(page,interactive=true,external=false){
 return `<div class="paper ${page.layout==='full_bleed'?'full-bleed':''}"><div class="paper-title">${e(page.chapter_title)}</div>${page.panels.filter(original=>external||allPanels().some(p=>p.id===original.id)).map(original=>{
 const p=(external?original:allPanels().find(x=>x.id===original.id)||original),b=original.box;
 const poly=original.polygon?.map(([x,y])=>[(x-b.x)/b.w*100,(y-b.y)/b.h*100]);
 const border=p.border!=='open'&&page.layout!=='full_bleed';
 return `<div class="paper-panel ${S.book.monochrome?'mono':''} ${S.selected===p.id?'selected':''}" ${interactive?`data-action="panel" data-id="${e(p.id)}"`:''} style="left:${b.x/10}%;top:${b.y/14.2}%;width:${b.w/10}%;height:${b.h/14.2}%;border:0;${poly?'clip-path:polygon('+poly.map(pt=>pt.join('% ')+'%').join(',')+');':''}">${p.image?`<img src="${asset(p.image)}" style="object-position:${p.focus_x*100}% ${p.focus_y*100}%" alt="${e(p.description)}">`:`<div class="placeholder"><div class="sketch"></div><b>PANEL ${String(original.order).padStart(2,'0')}</b><span>${e(p.description)}</span></div>`}${svgLettering(original,p)}${border?`<svg class="panel-vector-frame" viewBox="0 0 100 100" preserveAspectRatio="none"><polygon points="${(poly||[[0,0],[100,0],[100,100],[0,100]]).map(pt=>pt.join(',')).join(' ')}" fill="none" stroke="#151515" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`:''}</div>`}).join('')}<div class="paper-folio">${String(page.number).padStart(2,'0')}</div></div>`;
}
function renderPreview(){
 const holder=$('#pagePreview');if(!holder)return;const pages=S.chapter.pages;
 if(!allPanels().length||!pages.length){holder.innerHTML='<div class="paper-wrap"><div class="page-empty"><b>Eine leere Seite.</b><p>Sobald dein Storyboard steht, entsteht hier der Rhythmus deiner Geschichte.</p></div></div>';return}
 S.page=Math.max(0,Math.min(S.page,pages.length-1));const page=pages[S.page];
 holder.innerHTML=`<div class="paper-wrap"><div class="preview-top"><span>SEITE ${String(page.number).padStart(2,'0')} <small>· ${S.page+1}/${pages.length} im Kapitel</small></span><div class="preview-controls"><button data-action="prev-page" aria-label="Vorherige Seite">‹</button><button data-action="next-page" aria-label="Nächste Seite">›</button></div></div>${paperHTML(page)}${letteringWarnings(page)}<button class="small" data-action="edit-lettering" data-bi="0" ${busy()?'disabled':''}>Sprechblasen auf Seite bearbeiten</button><div class="preview-note"><span>${S.book.direction==='rtl'?'← RECHTS NACH LINKS':'LINKS NACH RECHTS →'}</span><span>${page.panels.length===1?'SPLASH PAGE':page.panels.length+' PANELS · '+({dynamic:'DIAGONAL',cinematic:'FILMISCH',balanced:'RUHIG',auto:'AUTOMATISCH',full_bleed:'RANDLOS'}[page.layout||'auto'])}</span></div></div><div class="page-dots">${pages.map((_,i)=>`<button class="page-dot ${i===S.page?'active':''}" data-action="page" data-index="${i}" aria-label="Seite ${i+1}"></button>`).join('')}</div><p class="note">Die Vorschau zeigt die Seitenaufteilung. Blase ziehen, Eckpunkt für Größe und goldenen Punkt für Zipfel nutzen. Vorschau und PDF verwenden dieselben Textumbrüche. Speichern übernimmt die Änderungen.</p>`;
}
function renderCharacters(){
 const previous=S.book.jobs.find(j=>j.kind==='character_autoadd'&&j.chapter_id===S.chapter?.id&&j.state==='done');
 const result=previous?.payload?.result,deleted=S.book.deleted_characters||[];
 $('#viewContent').innerHTML=`<div class="sectionbar"><h2>Eine Besetzung. Eine visuelle Sprache.</h2><small>${S.book.characters.length} CHARAKTERE</small></div><p style="max-width:680px;font-size:12px">Ein Manga-Referenzbild direkt hochladen oder einen bestehenden Charakterrender von der KI analysieren und im Mangastil neu zeichnen lassen. Den erzeugten Entwurf kannst du vor der Übernahme prüfen.</p><div class="autoadd-controls"><div><label for="characterChapterSelect">Aktuelles Kapitel für Autoadd</label><select id="characterChapterSelect">${S.book.chapters.map(c=>`<option value="${e(c.id)}" ${S.chapter?.id===c.id?'selected':''}>${e(c.title)}</option>`).join('')}</select></div><button class="primary" data-action="autoadd-characters" ${busy()||!S.chapter?'disabled':''}>＋ Autoadd aus Kapitel</button></div><p class="note">Durchsucht nur dieses Kapitel. Bereits vorhandene Namen und Aliase werden abgeglichen; bestehende Profile und Bilder bleiben erhalten.</p>${result?`<div class="warning">Letzter Autoadd: ${result.added.length} neue Charaktere${result.added.length?' ('+e(result.added.map(c=>c.name).join(', '))+')':''}. ${result.existing} bereits vorhandene oder doppelte Nennungen übersprungen.${result.deleted?' '+result.deleted+' bewusst entfernte Profile nicht erneut angelegt.':''}${result.ambiguous?' '+result.ambiguous+' uneindeutige Zuordnungen übersprungen.':''}${result.unverified?' '+result.unverified+' nicht im Quelltext belegbare Vorschläge übersprungen.':''}<br>Automatische Beschreibungen prüfen und Referenzbilder ergänzen.</div>`:''}<div class="cast-grid">${S.book.characters.map(c=>`<article class="character"><div class="character-img">${c.image?`<img src="${asset(c.image)}" alt="${e(c.name)}">`:e(c.name[0])}</div><div class="character-info"><h3>${e(c.name)}</h3><small>${c.image?'AKTIVE CHARAKTERREFERENZ':'NOCH OHNE AKTIVES REFERENZBILD'}</small>${c.autodetected_from?'<small class="autoadd-origin">AUS KAPITELTEXT ERKANNT · BITTE PRÜFEN</small>':''}<p>${e(c.description)}</p><div class="character-actions"><button class="small" data-action="edit-character" data-id="${e(c.id)}">Profil & Render bearbeiten</button><button class="small danger-quiet" data-action="delete-character" data-id="${e(c.id)}" ${busy()?'disabled':''}>Löschen</button></div>${c.manga_draft?.image?`<div class="character-draft-card"><img src="${asset(c.manga_draft.image)}" alt="Manga-Entwurf ${e(c.name)}"><div><small>${c.image===c.manga_draft.image?'MANGA-REFERENZ ÜBERNOMMEN':'NEUER MANGA-ENTWURF'}</small><button class="small quiet" data-action="review-character-render" data-id="${e(c.id)}">${c.image===c.manga_draft.image?'Analyse ansehen':'Entwurf prüfen →'}</button></div></div>`:''}</div></article>`).join('')}<button class="character-add" data-action="add-character" ${busy()?'disabled':''}><b>＋</b>Charakter hinzufügen</button></div>${deleted.length?`<details class="deleted-characters"><summary>Gelöschte Charaktere (${deleted.length})</summary><p class="note">Profile und zugehörige Bilddateien bleiben zur Wiederherstellung erhalten. Autoadd legt diese Figuren nicht erneut an.</p>${deleted.map(c=>`<div><span>${e(c.name)}</span><button class="small" data-action="restore-character" data-id="${e(c.id)}" ${busy()?'disabled':''}>Wiederherstellen</button></div>`).join('')}</details>`:''}`;
}
function renderSource(){
 $('#viewContent').innerHTML=(S.chapter?chapterBar():'')+`<div class="source-text"><h2>${e(S.chapter?.title||'Buchtext')}</h2><p class="note">Originaltext des Imports. Absatznummern verbinden Storyboard-Szenen mit ihrer Buchstelle.</p>${(S.chapter?.source_paragraphs||[]).map(p=>`<div class="source-paragraph"><b>${p.number}</b><p>${e(p.text)}</p></div>`).join('')}</div>`;
}
function renderGallery(){
 const pages=S.chapter?.pages||[],card=p=>`<div class="spread-page"><div class="preview-top"><span>SEITE ${p.number}</span><small>${p.panels.length} PANELS</small></div>${paperHTML(p)}${letteringWarnings(p)}</div>`;
 let body='';
 if(S.spread){body=flowSpreadHTML(S.chapter.page_spreads||[],S.chapter.id)}
 else body=`<div class="gallery">${pages.map(card).join('')}</div>`;
 $('#viewContent').innerHTML=(S.chapter?chapterBar():'')+`${pageFlowBannerHTML()}<label class="checkline"><input id="spreadView" type="checkbox" ${S.spread?'checked':''}>Doppelseiten in aktueller PDF-Seitenlage</label>${body||'<div class="empty">Zuerst ein Kapitel planen.</div>'}`;
}
function removePanel(id){
 if(busy())return;
 const sc=S.scenes.find(s=>s.panels.some(p=>p.id===id));
 if(!sc)return;
 const last=sc.panels.length===1;
 if(!confirm(last?'Letztes Panel dieser Szene löschen? Die leere Szene wird ebenfalls entfernt. Buchtext und Bilddateien bleiben erhalten. Danach speichern.':'Dieses Panel mit seinen Dialogen und Zuordnungen aus dem Storyboard löschen? Die Bilddatei bleibt erhalten. Danach speichern.'))return;
 const at=sc.panels.findIndex(p=>p.id===id);
 sc.panels.splice(at,1);
 if(last)S.scenes=S.scenes.filter(s=>s!==sc);
 if(S.selected===id)S.selected=sc.panels[Math.min(at,sc.panels.length-1)]?.id||allPanels()[0]?.id||null;
 dirty();renderScenes();renderEditor();renderPreview();
}
function clearStoryboard(){
 if(busy()||!S.scenes.length)return;
 if(!confirm('Alle Panels und Szenen dieses Kapitels aus dem Storyboard löschen? Der Buchtext, die Charaktere und Bilddateien bleiben erhalten. Danach speichern.'))return;
 S.scenes=[];S.selected=null;S.page=0;dirty();renderScenes();renderEditor();renderPreview();
}
function dirty(){S.dirty=true;requestPagePreview();const label=$('#dirtyLabel');if(label)label.textContent='● Ungespeichert';const save=$('[data-action="save"]');if(save)save.disabled=false}
async function savePlan(){if(!S.dirty)return;invalidatePagePreview();S.chapter=await api('/api/chapters/'+S.chapter.id+'/plan',{method:'PUT',body:JSON.stringify({revision:S.chapter.revision,scenes:S.scenes})});S.scenes=structuredClone(S.chapter.scenes);S.dirty=false;S.book=await api('/api/projects/'+S.book.id);render();renderRail();toast('Storyboard gespeichert. Seitenlayout aktualisiert.')}
async function startPlan(){if(S.scenes.length&&!confirm('Storyboard dieses Kapitels neu planen? Beim erfolgreichen Abschluss werden die bisherigen Szenen und Panelzuordnungen ersetzt.'))return;await post('/api/chapters/'+S.chapter.id+'/plan',{replace:!!S.scenes.length});S.dirty=false;await refreshProject();toast('Storyboard-Auftrag vorgemerkt. ComfyUI verarbeitet den Kapiteltext lokal.')}
async function generate(single){await savePlan();const p=panel();await post('/api/chapters/'+S.chapter.id+'/images',{panel_id:single?p.id:null,missing_only:!single});await refreshProject();toast(single?'Panel-Auftrag vorgemerkt.':'Fehlende und veraltete Bilder werden nacheinander erzeugt.')}
async function refreshProject(){S.book=await api('/api/projects/'+S.book.id);renderRail();render()}
function characterModal(id){
 const c=S.book.characters.find(c=>c.id===id)||{name:'',description:'',aliases:''};const disabled=busy()?'disabled':'';
 modal(id?'Charakter bearbeiten':'Neuer Charakter',`<form id="characterForm" data-id="${e(id||'')}"><label>Name</label><input name="name" value="${e(c.name)}" required maxlength="100" ${disabled}><label>Andere Namen / Aliase</label><input name="aliases" value="${e(c.aliases)}" maxlength="300" ${disabled}><label>Aussehen & feste Merkmale</label><textarea name="description" rows="4" required maxlength="2000" placeholder="Alter, Gesicht, Haare, Kleidung, markante Details …" ${disabled}>${e(c.description)}</textarea><label>Fertiges Referenzbild direkt ${id?'ersetzen':'hochladen'} (optional)</label><input type="file" name="file" accept="image/png,image/jpeg,image/webp" ${disabled}><p class="note">Dieses Bild wird ohne KI-Umwandlung als aktive Charakterreferenz verwendet.</p><section class="render-upload"><h3>Bestehenden Charakterrender in Manga umwandeln</h3><p class="note">Die lokale Bild-KI analysiert den Render und zeichnet den Charakter in der Bildsprache deines Buchs neu. Das Ergebnis bleibt zunächst ein Entwurf.</p>${c.render_source?`<div class="render-source"><img src="${asset(c.render_source)}" alt="Zuletzt hochgeladener Charakterrender"><span>Bestehender Render hinterlegt</span></div>`:''}<label>Render für KI-Analyse & Manga-Zeichnung (optional)</label><input type="file" name="render_file" accept="image/png,image/jpeg,image/webp" ${disabled}><p class="note">PNG, JPEG oder WebP, maximal 15 MB. Möglichst eine einzelne Figur mit klar sichtbarem Gesicht.</p>${c.render_source?`<button type="button" class="small" data-action="regenerate-character-render" data-id="${e(id)}" ${disabled}>Vorhandenen Render erneut als Manga zeichnen</button>`:''}</section><section class="render-upload"><h3>Bild aus Beschreibung</h3><p class="note">Erzeugt nur den Charakter vor reinweißem Hintergrund aus dem oben eingetragenen Aussehen und dem Buchstil. Der Hintergrund ist weiß, nicht transparent. Kein Referenzbild nötig. Name und Beschreibung werden dabei gespeichert; das Ergebnis kannst du anschließend prüfen und übernehmen.</p><button type="button" class="small" data-action="generate-character-description" ${disabled}>Bild aus Beschreibung erzeugen</button></section><div class="modal-actions"><button type="button" data-action="close-modal">Schließen</button><button class="primary" type="submit" ${disabled}>Charakter speichern</button></div></form>${characterDraftHTML(c)}`);
}
function characterDraftHTML(c){
 const d=c.manga_draft;if(!d?.image)return '';const accepted=c.image===d.image;
 const fromDescription=d.origin==='description';
 return `<section class="render-result"><div class="eyebrow">${accepted?'ALS REFERENZ ÜBERNOMMEN':'MANGA-ENTWURF · VOR DER ÜBERNAHME PRÜFEN'}</div><div class="render-comparison">${d.source_image?`<div><small>URSPRÜNGLICHER RENDER</small><a href="${asset(d.source_image)}" target="_blank" rel="noopener"><img src="${asset(d.source_image)}" alt="Ursprünglicher Charakterrender"></a></div>`:''}<div><small>${fromDescription?'AUS BESCHREIBUNG ERZEUGT':'KI-MANGA-ENTWURF'}</small><a href="${asset(d.image)}" target="_blank" rel="noopener"><img src="${asset(d.image)}" alt="Neu gezeichneter Manga-Charakter"></a></div></div>${d.analysis?`<h3>Erkannte Merkmale</h3><p class="analysis-text">${e(d.analysis.observations)}</p>${d.analysis.uncertainty?`<p class="warning">${e(d.analysis.uncertainty)}</p>`:''}<details><summary>Bildbeschreibung für die Manga-KI ansehen</summary><p class="analysis-text">${e(d.analysis.description)}</p></details>`:`<details><summary>Verwendete Charakterbeschreibung ansehen</summary><p class="analysis-text">${e(d.description)}</p></details>`}${accepted?'<p class="note">Dieses Manga-Bild wird bereits als Charakterreferenz für Panels verwendet.</p>':`${d.analysis?'<label class="checkline"><input id="useRenderDescription" type="checkbox">KI-Bildbeschreibung ebenfalls als Charakterbeschreibung übernehmen</label>':''}<button class="primary" data-action="accept-character-render" data-id="${e(c.id)}" data-image="${e(d.image)}" ${busy()?'disabled':''}>Manga-Bild als Charakterreferenz übernehmen</button><p class="note">Die bisherige Referenz bleibt bis zur Übernahme aktiv. Die Originaldateien bleiben gespeichert.</p>`}</section>`;
}
async function saveCharacterForm(form,data,fromDescription=false){
 let id=form.dataset.id;const render=data.get('render_file');let queued=false;
 if(fromDescription&&render?.size)throw Error('Bitte den Render-Upload leeren, um stattdessen ein Bild aus der Beschreibung zu erzeugen.');
 if(id){
  await api(`/api/projects/${S.book.id}/characters/${id}`,{method:'PUT',body:JSON.stringify({name:data.get('name'),description:data.get('description'),aliases:data.get('aliases')})});
  const file=data.get('file');if(file?.size){const f=new FormData();f.append('file',file);await api(`/api/projects/${S.book.id}/characters/${id}/image`,{method:'POST',body:f})}
  if(render?.size){const f=new FormData();f.append('file',render);await api(`/api/projects/${S.book.id}/characters/${id}/render`,{method:'POST',body:f});queued=true}
 }else{const result=await api(`/api/projects/${S.book.id}/characters`,{method:'POST',body:data});id=result.id;form.dataset.id=id;queued=!!result.job_id}
 if(fromDescription){await post(`/api/projects/${S.book.id}/characters/${id}/generate`);queued=true}
 closeModal();await refreshProject();toast(fromDescription?'Charakter gespeichert. Bild aus Beschreibung wird erzeugt.':queued?'Charakter gespeichert. Render-Analyse und Manga-Zeichnung starten im Hintergrund.':'Charakter gespeichert.');
}
function bookSettingsModal(){modal('Stil & Leserichtung',`<form id="bookSettingsForm" data-book-id="${e(S.book.id)}"><label>Buchtitel</label><input name="title" value="${e(S.book.title)}" required maxlength="180"><label>Gemeinsame Bildsprache (englisch empfohlen)</label><textarea name="style" rows="5" required maxlength="1500">${e(S.book.style)}</textarea><div id="styleMagic">${styleMagicHTML()}</div><label>Leserichtung</label><select name="direction"><option value="rtl" ${S.book.direction==='rtl'?'selected':''}>Rechts nach links (Manga)</option><option value="ltr" ${S.book.direction==='ltr'?'selected':''}>Links nach rechts</option></select><label class="checkline"><input type="checkbox" name="monochrome" ${S.book.monochrome?'checked':''}>Schwarzweiß im PDF und in der Vorschau</label><p class="note">Änderungen der Bildsprache markieren vorhandene Panelbilder als veraltet. Leserichtung und Bildfokus ändern nur das Layout.</p><div id="bookDeleteConfirm" class="warning" hidden><p>„${e(S.book.title)}“ aus der Bibliothek löschen? Kapitel, Charaktere, Bilder und Exporte bleiben erhalten. Du kannst das Buch unter „Gelöschte Bücher“ wiederherstellen.</p><button type="button" class="danger-quiet" data-action="confirm-delete-book" data-id="${e(S.book.id)}">Ja, Buch löschen</button><button type="button" data-action="cancel-delete-book">Doch behalten</button></div><div class="modal-actions"><button type="button" class="danger-quiet" data-action="delete-book" ${busy()?'disabled':''}>Buch löschen</button><button type="button" data-action="close-modal">Abbrechen</button><button type="submit" class="primary">Speichern</button></div></form>`);const box=$('#styleMagic');if(box)box.dataset.styleHTML=styleMagicHTML();}
function deleteBook(){
 if(!S.book||busy())throw Error('Bitte laufende Buchaufträge zuerst abschließen.');
 $('#bookDeleteConfirm').hidden=false;
}
async function confirmDeleteBook(id){
 if(!S.book||id!==S.book.id||busy())throw Error('Bitte das Buch neu öffnen und laufende Aufträge abschließen.');
 await savePlan();await api('/api/projects/'+id,{method:'DELETE'});
 closeModal();invalidatePagePreview();S.book=null;S.chapter=null;S.scenes=[];S.selected=null;S.dirty=false;S.page=0;
 localStorage.setItem('manga-book','');await loadBooks();render();toast('Buch gelöscht. Unter „Gelöschte Bücher“ kannst du es wiederherstellen.');
}
async function deletedBooksModal(){
 const books=await api('/api/deleted-projects');
 modal('Gelöschte Bücher',`<p class="note">Alle Kapitel, Charaktere, Bilddateien und Exporte bleiben erhalten. Die Wiederherstellung bringt das ganze Buch zurück.</p>${books.length?books.map(b=>`<div class="action-row"><span>${e(b.title)}</span><button class="small" data-action="restore-book" data-id="${e(b.id)}">Wiederherstellen</button></div>`).join(''):'<p>Keine gelöschten Bücher.</p>'}`);
}
function imageModelFamily(name){
 const value=String(name||'').toLowerCase();
 if(value.includes('base'))return 'custom';
 return /flux-2-klein-4b(?:[-.]|$)/.test(value)?'4b':/flux-2-klein-9b(?:[-.]|$)/.test(value)?'9b':'custom';
}
function modelLicenseHTML(name){
 const family=imageModelFamily(name);
 if(family==='4b')return '<strong>Apache 2.0 · kommerzielle Nutzung erlaubt</strong><p>Klein 4B darf auch lokal für kommerzielle Projekte eingesetzt werden. Die Lizenzbedingungen gelten weiterhin.</p><a href="https://huggingface.co/black-forest-labs/FLUX.2-klein-4B" target="_blank" rel="noopener">Modell & Lizenz ↗</a>';
 if(family==='9b')return '<strong>FLUX Non-Commercial License · kommerzieller Modelleinsatz lizenzpflichtig</strong><p>Für die lokale Produktion kommerzieller Buchillustrationen benötigt Klein 9B eine gesonderte BFL-Lizenz. Die Output-Klausel ist keine pauschale Freigabe des kommerziellen Modelleinsatzes.</p><a href="https://help.bfl.ai/articles/9272590838-self-serve-dev-license-overview-pricing" target="_blank" rel="noopener">BFL-Lizenzübersicht ↗</a>';
 return '<strong>Lizenz nicht automatisch zugeordnet</strong><p>Für diese Datei die Herkunft und Lizenz selbst prüfen. Base-Modelle und andere Architekturen passen nicht zum vorbereiteten Distilled-Workflow.</p>';
}
function refreshModelLicense(){
 const model=$('#settingsImageModel').value;
 $('#settingsImagePreset').value=imageModelFamily(model);
 $('#settingsModelLicense').innerHTML=modelLicenseHTML(model);
}
function chooseImagePreset(family){
 if(!['4b','9b'].includes(family))return;
 const model=$('#settingsImageModel'),encoder=$('#settingsImageEncoder');
 const choices=S.connection?.image_models||[];
 if(imageModelFamily(model.value)!==family){
  const canonical=`flux-2-klein-${family}-fp8.safetensors`;
  model.value=choices.includes(canonical)?canonical:choices.find(name=>imageModelFamily(name)===family)||canonical;
 }
 encoder.value=family==='4b'?'qwen_3_4b.safetensors':'qwen_3_8b_fp8mixed.safetensors';
 refreshModelLicense();
}
async function settingsModal(){
 S.settings=await api('/api/settings');const s=S.settings,c=S.connection||{},family=imageModelFamily(s.image_model);
 modal('Verbindung & Modelle',`<p class="note">MangaStudio arbeitet mit lokalem ComfyUI.</p><form id="settingsForm">
 <label>ComfyUI-Adresse</label><input name="comfy_url" value="${e(s.comfy_url)}" required>
 <label>Textmodell (Kapitelplanung)</label><input name="text_model" value="${e(s.text_model)}" list="textModels" required>
 <label>Vision-Modell (Charakterrender analysieren)</label><input name="vision_model" value="${e(s.vision_model)}" list="textModels" required>
 <label for="settingsImagePreset">Bildmodell wählen</label><select id="settingsImagePreset">${[['4b','Klein 4B · Apache 2.0 · kommerziell nutzbar'],['9b','Klein 9B · Non-Commercial · Zusatzlizenz für kommerziellen Einsatz'],['custom','Andere Datei / manuell']].map(([value,label])=>`<option value="${value}" ${family===value?'selected':''}>${label}</option>`).join('')}</select>
 <div id="settingsModelLicense" class="warning" aria-live="polite">${modelLicenseHTML(s.image_model)}</div>
 <p class="note">Die Auswahl setzt die Modelldatei und den passenden Encoder. Erst Speichern aktiviert die Änderung. Modelle müssen separat installiert sein. Bestehende Bilder bleiben erhalten; nach einem Modellwechsel gelten sie als veraltet.</p>
 <label for="settingsImageModel">Modelldatei (Flux.2 Klein Distilled)</label><input id="settingsImageModel" name="image_model" value="${e(s.image_model)}" list="imageModels" required>
 <label for="settingsImageEncoder">Bild-Textencoder</label><input id="settingsImageEncoder" name="image_encoder" value="${e(s.image_encoder)}" list="textModels" required>
 <label>Bild-VAE</label><input name="image_vae" value="${e(s.image_vae)}" list="vaeModels" required>
 <p class="note">Die voreingestellten Qwen-Modelle und der FLUX.2 Small Decoder sind unter Apache 2.0 veröffentlicht. Bei anderen Dateien deren Lizenz prüfen. Die MIT-Lizenz der App ersetzt keine Modelllizenz.</p>
 <label>Zeitlimit pro Generierung (Sekunden)</label><input type="number" name="timeout" value="${s.timeout}" min="60" max="7200">
 <datalist id="textModels">${(c.text_models||[]).map(m=>`<option value="${e(m)}">`).join('')}</datalist><datalist id="imageModels">${(c.image_models||[]).map(m=>`<option value="${e(m)}">`).join('')}</datalist><datalist id="vaeModels">${(c.vaes||[]).map(m=>`<option value="${e(m)}">`).join('')}</datalist>
 <div id="settingsStatus" class="warning">${e(c.connected?(c.ready?'Verbindung und Modelle bereit.':'Verbindung steht. Fehlend: '+[...(c.missing_models||[]),...(c.missing_nodes||[])].join(', ')):c.message||'Verbindung noch nicht geprüft.')}</div>
 <div class="modal-actions"><button type="button" data-action="check-connection">Erneut prüfen</button><button type="submit" class="primary">Speichern</button></div></form>`);
 const box=$('#styleMagic');if(box)box.dataset.styleHTML=styleMagicHTML();
}
 document.addEventListener('change',event=>{
  if(event.target.id==='settingsImagePreset')chooseImagePreset(event.target.value);
  else if(event.target.id==='settingsImageModel')refreshModelLicense();
 });
 document.addEventListener('input',event=>{if(event.target.id==='settingsImageModel')refreshModelLicense()});

function publicationHTML(){
 const p=S.book.publication||{};
 return `<details><summary>Standardseiten · Cover, Innentitel & Impressum</summary>
 <label class="checkline"><input id="publicationEnabled" type="checkbox" ${p.enabled?'checked':''}>Vier Standardseiten vor die Story setzen</label>
 <p class="note">In Leserichtung: 1 Cover/Titelseite · 2 Leerseite · 3 Innentitel · 4 Impressum · ab 5 Story. Im RTL-Druck-PDF liegt dieser Vorspann am Dateiende. Standardseiten erscheinen in PDFs und Seitenbildern; der Webcomic zeigt nur die Story.</p>
 <label for="publicationTitle">Titel</label><input id="publicationTitle" maxlength="300" value="${e(p.title||S.book.title||'')}">
 <label for="publicationSubtitle">Untertitel / Band</label><input id="publicationSubtitle" maxlength="300" value="${e(p.subtitle||'')}">
 <label for="publicationAuthor">Autor / Autorin</label><input id="publicationAuthor" maxlength="160" value="${e(p.author||'')}">
 <label for="publicationImprint">Impressum · Seite 4 in Leserichtung</label><textarea id="publicationImprint" maxlength="10000" rows="10" placeholder="Copyright, Mitwirkende, Verlag / Herstellung, ISBN und weitere Angaben für diese Ausgabe …">${e(p.imprint||'')}</textarea>
 <p class="note">Freier Text mit deinen Zeilenumbrüchen. Angaben für diese Manga-Ausgabe selbst eintragen; die ISBN des Romans wird nicht übernommen.</p>
 ${p.cover_image?`<img src="${asset(p.cover_image)}" alt="Aktuelles PDF-Cover" style="max-width:150px;max-height:210px"><button class="small" data-action="remove-publication-cover">Cover entfernen</button>`:''}
 <label for="publicationCover">Coverbild für PDF-Seite 1 (optional)</label><input id="publicationCover" type="file" accept="image/png,image/jpeg,image/webp">
 <p class="note">Das ganze Bild wird proportional eingepasst. Ohne Bild wird eine Titelseite erstellt. Für die fertige Ausgabe sind 300 dpi nötig. Ein Druckumschlag mit Rückseite und Buchrücken wird separat erstellt.</p>
 <button class="small" data-action="save-publication">Standardseiten speichern</button></details>`;
}
async function savePublication(){
 const enabled=$('#publicationEnabled');
 if(typeof enabled?.checked!=='boolean')return;
 const publication={enabled:enabled.checked,title:$('#publicationTitle').value,subtitle:$('#publicationSubtitle').value,author:$('#publicationAuthor').value,imprint:$('#publicationImprint').value};
 S.book.publication=await api('/api/projects/'+S.book.id+'/publication',{method:'PUT',body:JSON.stringify(publication)});
}
document.addEventListener('click',event=>{
 const action=event.target.closest('[data-action]')?.dataset.action;
 if(action==='save-publication')run(async()=>{await savePublication();toast('Standardseiten gespeichert.')});
 if(action==='remove-publication-cover')run(async()=>{await savePublication();S.book.publication=await api('/api/projects/'+S.book.id+'/publication/cover',{method:'DELETE'});exportModal()});
});
document.addEventListener('change',event=>{
 if(event.target.id==='publicationCover'&&event.target.files[0])run(async()=>{
  const file=event.target.files[0];await savePublication();const form=new FormData();form.append('file',file);
  S.book.publication=await api('/api/projects/'+S.book.id+'/publication/cover',{method:'POST',body:form});exportModal();toast('PDF-Cover gespeichert.');
 });
});
function exportModal(){
 const history=(S.book.exports||[]).slice(-3).reverse().map(x=>`<p class="note"><a href="${asset(x.path)}" download="${e(x.name||'manga.pdf')}">${x.draft?'Entwurf':'Export'} · ${x.pages} Seiten · ${e(x.name||'PDF')} herunterladen ↧</a></p>`).join('');
 modal('Manga exportieren',`<p>Wähle die gewünschten Ausgaben. Sie werden gemeinsam erstellt und als eine Datei heruntergeladen. Mehrere Varianten kommen in ein Exportpaket.</p>
 <div id="exportOptions">
 ${publicationHTML()}
 <label class="checkline"><input type="checkbox" name="export_format" value="pdf" checked>Lese-PDF · chronologische Seitenfolge, aktueller Farbmodus</label>
 <label class="checkline"><input type="checkbox" name="export_format" value="print_pdf">Druck-PDF · ${S.book.direction==='rtl'?'umgekehrte Seitenfolge':'chronologische Seitenfolge'}</label>
 <p class="note">Druck-PDF: ${S.book.direction==='rtl'?'Die erste Storyseite liegt am Ende der PDF. Für Druckereien, die den Buchblock in westlicher Reihenfolge verarbeiten.':'Die erste Storyseite liegt am Anfang der PDF.'} Bei ungerader Seitenzahl wird eine Leerseite am Storyende ergänzt. Aktueller Farbmodus, ohne Umschlag und ohne Druckbogen-Ausschießung. Seitenfolge, ergänzte Leerseiten und Umschlag in der Druckvorschau der Druckerei prüfen.</p>
 <label class="checkline"><input type="checkbox" name="export_format" value="grayscale" ${S.book.monochrome?'disabled':''}>Zusätzlich Graustufen-PDF erzeugen</label>
 <p class="note">${S.book.monochrome?'Das Buch ist bereits auf Schwarzweiß gestellt.':'Für die Druckausgabe; dein Buch und die Originalbilder bleiben farbig.'}</p>
 <label class="checkline"><input type="checkbox" name="export_format" value="pages">Seitenbilder als ZIP · nummerierte PNGs, 300 dpi</label>
 <label class="checkline"><input type="checkbox" name="export_format" value="webcomic">Webcomic als ZIP · HTML + nummerierte Panelbilder</label>
 <p class="note">Der Webcomic zeigt die Panels mit Dialogen in Buchreihenfolge untereinander. ZIP entpacken und index.html öffnen. Seitenbilder und Webcomic verwenden den aktuellen Farbmodus.</p>
 <label>Exportstand</label><select id="exportDraft"><option value="final">Fertige Ausgabe</option><option value="draft">Layout-Entwurf (fehlende/veraltete Bilder erlaubt)</option></select>
 <p class="note">Die fertige Ausgabe benötigt geplante Kapitel, aktuelle Bilder mit ausreichender Druckauflösung und passende Sprechblasen. Es werden keine neuen KI-Bilder erzeugt.</p>
 <button class="primary" data-action="export-selected">Auswahl erzeugen & herunterladen</button></div>
 <div id="exportResult" aria-live="polite"></div>${history?'<h3 style="margin-top:24px">Letzte Exporte</h3>'+history:''}`);
}
function selectedExportFormats(){
 const formats=Array.from(document.querySelectorAll('input[name="export_format"]:checked')).filter(n=>!n.disabled).map(n=>n.value);
 if(!formats.length)throw Error('Bitte mindestens ein Ausgabeformat auswählen.');
 return formats;
}
async function exportSelected(button){
 const formats=selectedExportFormats(),draft=$('#exportDraft').value==='draft';
 button.disabled=true;
 try{await savePublication();await exportPDF(draft,formats)}catch(error){$('#exportResult').textContent='Export fehlgeschlagen: '+error.message;throw error}finally{button.disabled=false}
}

async function exportPDF(draft,formats=['pdf']){
 await savePlan();
 const bookId=S.book.id;
 $('#exportResult').innerHTML='<p>Ausgaben werden erzeugt … Bei vielen Seiten kann das etwas dauern.</p>';
 const value=await post('/api/projects/'+bookId+'/export',{draft,formats});
 const files=value.files||[{path:value.path,name:'manga.pdf',label:'PDF'}];
 $('#exportResult').innerHTML=`<div class="warning">${value.pages} Seiten · ${draft?'Layout-Entwurf':'Fertige Ausgabe'}<p><a href="${asset(value.path)}" download="${e(value.name||'manga.pdf')}">Ausgabe${files.length>1?'paket':''} herunterladen ↧</a></p>${files.length>1?files.map(f=>`<p><a href="${asset(f.path)}" download="${e(f.name)}">${e(f.label)} herunterladen ↧</a></p>`).join(''):''}</div>`;
 const link=document.createElement('a');link.href=asset(value.path);link.download=value.name||'manga.pdf';document.body.appendChild(link);link.click();link.remove();
 S.book=await api('/api/projects/'+bookId);
}

async function checkConnection(){S.connection=await api('/api/connection');const c=S.connection;$('#connectionPill').textContent=c.connected?'COMFYUI · '+(c.ready?'BEREIT':'MODELLE PRÜFEN'):'COMFYUI · OFFLINE';$('#connectionPill').classList.toggle('off',!c.ready);$('#connectionLabel').textContent=c.connected?(c.ready?'Modelle verbunden':'Verbindung steht, Modelle prüfen'):'ComfyUI starten für KI-Generierung';if($('#settingsStatus'))$('#settingsStatus').textContent=c.connected?(c.ready?'Verbindung und Modelle bereit.':'Fehlend: '+[...(c.missing_models||[]),...(c.missing_nodes||[])].join(', ')):c.message}
document.addEventListener('click',event=>{const target=event.target.closest('[data-action]');if(!target||target.disabled)return;run(async()=>{const a=target.dataset.action;if(a==='close-modal')closeModal();else if(a==='upload-book')$('#bookFile').click();else if(a==='demo'){const b=await post('/api/demo');await loadBooks();await openBook(b.id)}else if(a==='book')await openBook(target.dataset.id);else if(a==='chapter')await loadChapter(target.dataset.id);else if(a==='view'){S.view=target.dataset.view;render()}else if(a==='panel'){S.selected=target.dataset.id;const page=S.chapter.pages.findIndex(p=>p.panels.some(x=>x.id===S.selected));if(page>=0)S.page=page;if(S.view==='pages'){S.view='storyboard';render()}else{renderScenes();renderEditor();renderPreview()}}else if(a==='page'){S.page=+target.dataset.index;renderPreview()}else if(a==='prev-page'){S.page--;renderPreview();refreshLetteringCanvas()}else if(a==='next-page'){S.page++;renderPreview();refreshLetteringCanvas()}else if(a==='evidence'){const holder=$('#evidence-'+target.dataset.id);holder.hidden=!holder.hidden}else if(a==='save')await savePlan();else if(a==='plan')await startPlan();else if(a==='plan-page-flow'){await startPageFlow()}else if(a==='review-dramaturgy'){await startDramaturgyReview()}else if(a==='suggest-layout'){await savePlan();await post(`/api/chapters/${S.chapter.id}/layout`);await refreshProject();toast('KI analysiert den Seitenrhythmus. Vorschläge erscheinen an den Szenen und bleiben änderbar.')}else if(a==='generate-poses'||a==='generate-chapter-poses'){const id=a==='generate-poses'?S.selected:null;await savePlan();await post(`/api/chapters/${S.chapter.id}/poses`,{panel_id:id});await refreshProject();toast('KI ergänzt leere Körperhaltungen aus der Szene.')}else if(a==='generate-all')await generate(false);else if(a==='generate-panel')await generate(true);else if(a==='add-character')characterModal();else if(a==='edit-character')characterModal(target.dataset.id);else if(a==='book-settings')bookSettingsModal();else if(a==='delete-book')await deleteBook();else if(a==='confirm-delete-book')await confirmDeleteBook(target.dataset.id);else if(a==='cancel-delete-book')$('#bookDeleteConfirm').hidden=true;else if(a==='deleted-books')await deletedBooksModal();else if(a==='restore-book'){await post('/api/projects/'+target.dataset.id+'/restore');await loadBooks();await deletedBooksModal();toast('Buch wiederhergestellt.');}else if(a==='export')exportModal();else if(a==='export-selected')await exportSelected(target);else if(a==='export-final')await exportPDF(false);else if(a==='export-draft')await exportPDF(true);else if(a==='check-connection')await checkConnection();else if(a==='retry'){await post('/api/jobs/'+target.dataset.id+'/retry');await refreshProject()}else if(a==='add-panel'){const sc=S.scenes.find(s=>s.id===target.dataset.id);if(sc.panels.length>=6)throw Error('Maximal sechs Panels pro Szene.');sc.panels.push({id:uuid(),description:'Neue Handlung beschreiben',visual_prompt:'Describe a single concrete manga panel.',shot:'medium',emphasis:'normal',characters:[],bubbles:[],caption:'',focus_x:.5,focus_y:.45,image:'',image_signature:''});S.selected=sc.panels.at(-1).id;dirty();renderScenes();renderEditor()}else if(a==='clear-storyboard'){clearStoryboard()}else if(a==='remove-panel'){removePanel(target.dataset.id||S.selected)}else if(a==='move-panel'){const sc=S.scenes.find(s=>s.panels.some(p=>p.id===S.selected));const at=sc.panels.findIndex(p=>p.id===S.selected),to=at+(+target.dataset.delta);if(to>=0&&to<sc.panels.length){[sc.panels[at],sc.panels[to]]=[sc.panels[to],sc.panels[at]];dirty();renderScenes()}}else if(a==='add-bubble'){panel().bubbles.push({speaker:'',text:'Dialogtext',side:'right'});dirty();renderEditor();renderPreview()}else if(a==='remove-bubble'){panel().bubbles.splice(+target.dataset.index,1);dirty();renderEditor();renderPreview()}else if(a==='upload-panel'){await savePlan();const input=document.createElement('input');input.type='file';input.accept='image/png,image/jpeg,image/webp';const selected=S.selected,chapterId=S.chapter.id;input.onchange=()=>run(async()=>{if(!input.files[0])return;const form=new FormData();form.append('file',input.files[0]);await api(`/api/chapters/${chapterId}/panels/${selected}/image`,{method:'POST',body:form});await loadChapter(chapterId,false);S.selected=selected;render();toast('Panelbild übernommen.')});input.click()}})});
document.addEventListener('input',event=>{const t=event.target,p=panel();if(!p||busy())return;if(t.dataset.field){p[t.dataset.field]=t.type==='checkbox'?t.checked:['focus_x','focus_y'].includes(t.dataset.field)?+t.value:t.value;dirty();renderPreview()}if(t.dataset.poseCharacter){(p.character_poses??={})[t.dataset.poseCharacter]=t.value;dirty()}if(t.dataset.bfield){updateBubbleField(t,p)}});
document.addEventListener('change',event=>{const t=event.target;if(t.id==='spreadView'){S.spread=t.checked;renderGallery();return}if(t.id==='chapterSelect'){run(()=>loadChapter(t.value));return}if(t.dataset.sceneField&&!busy()){const sc=S.scenes.find(sc=>sc.id===t.dataset.sceneId);if(sc){sc[t.dataset.sceneField]=t.value;sc.layout_reason='Manuell angepasst.';dirty()}return}const p=panel();if(p&&t.dataset.character){p.characters=t.checked?[...p.characters,t.dataset.character]:p.characters.filter(c=>c!==t.dataset.character);if(!t.checked&&p.character_poses)delete p.character_poses[t.dataset.character];dirty();renderEditor()}if(p&&t.dataset.field){p[t.dataset.field]=t.type==='checkbox'?t.checked:['focus_x','focus_y'].includes(t.dataset.field)?+t.value:t.value;dirty();renderPreview()}});
document.addEventListener('submit',event=>{
 const form=event.target;if(!['characterForm','bookSettingsForm','settingsForm'].includes(form.id))return;
 event.preventDefault();run(async()=>{const data=new FormData(form),submit=form.querySelector('[type=submit]');submit.disabled=true;
  try{
   if(form.id==='characterForm')await saveCharacterForm(form,data);
   else if(form.id==='bookSettingsForm'){
    await savePlan();await api('/api/projects/'+S.book.id,{method:'PUT',body:JSON.stringify({title:data.get('title'),style:data.get('style'),direction:data.get('direction'),monochrome:data.get('monochrome')==='on'})});
    closeModal();await loadBooks();await refreshProject();if(S.chapter)await loadChapter(S.chapter.id,false);
   }else{
    const value=Object.fromEntries(data);value.timeout=+value.timeout;await api('/api/settings',{method:'PUT',body:JSON.stringify(value)});
    closeModal();await checkConnection();toast('Verbindungseinstellungen gespeichert.');
   }
  }finally{submit.disabled=false}
 });
});
document.addEventListener('click',event=>{
 const t=event.target.closest('[data-action]');if(!t||t.disabled)return;
 const action=t.dataset.action;if(!['review-character-render','regenerate-character-render','accept-character-render','generate-character-description'].includes(action))return;
 run(async()=>{
  const id=t.dataset.id;
  if(action==='generate-character-description'){const form=t.closest('form');if(!form.reportValidity())return;const buttons=[...form.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);try{await saveCharacterForm(form,new FormData(form),true)}finally{buttons.forEach(b=>b.disabled=false)}}
  else if(action==='review-character-render'){S.book=await api('/api/projects/'+S.book.id);characterModal(id)}
  else if(action==='regenerate-character-render'){
   await post(`/api/projects/${S.book.id}/characters/${id}/render/regenerate`);closeModal();await refreshProject();toast('Render-Analyse und Manga-Zeichnung erneut gestartet.');
  }else{
   await post(`/api/projects/${S.book.id}/characters/${id}/render/accept`,{image:t.dataset.image,use_description:!!$('#useRenderDescription')?.checked});
   closeModal();await refreshProject();if(S.chapter&&!S.dirty)await loadChapter(S.chapter.id,false);toast('Manga-Bild als Charakterreferenz übernommen.');
  }
 });
});
document.addEventListener('change',event=>{
 if(event.target.name==='render_file'&&event.target.closest('#characterForm')){
  const submit=event.target.form.querySelector('[type=submit]');submit.textContent=event.target.files[0]?'Speichern & Manga-Entwurf erzeugen':'Charakter speichern';
 }
});
document.addEventListener('change',event=>{
 if(event.target.id==='characterChapterSelect')run(()=>loadChapter(event.target.value));
});
document.addEventListener('click',event=>{
 const t=event.target.closest('[data-action]');if(!t||t.disabled)return;
 const action=t.dataset.action;if(!['autoadd-characters','delete-character','restore-character'].includes(action))return;
 run(async()=>{
  if(action==='autoadd-characters'){
   if(!S.chapter)throw Error('Bitte zuerst ein Kapitel auswählen.');
   await savePlan();await post(`/api/chapters/${S.chapter.id}/characters/autoadd`);await refreshProject();toast('Autoadd durchsucht das ausgewählte Kapitel lokal nach fehlenden Charakteren.');
  }else if(action==='delete-character'){
   const c=S.book.characters.find(c=>c.id===t.dataset.id);if(!c)return;
   if(!confirm(`„${c.name}“ aus der Besetzung löschen? Die Zuordnungen zu Panels werden entfernt. Bilder und Buchtext bleiben erhalten. Du kannst den Charakter später wiederherstellen.`))return;
   await savePlan();await api(`/api/projects/${S.book.id}/characters/${c.id}`,{method:'DELETE'});closeModal();
   await refreshProject();if(S.chapter)await loadChapter(S.chapter.id,false);toast('Charakter gelöscht. Unter „Gelöschte Charaktere“ kannst du ihn wiederherstellen.');
  }else{
   await savePlan();await post(`/api/projects/${S.book.id}/characters/${t.dataset.id}/restore`);await refreshProject();if(S.chapter)await loadChapter(S.chapter.id,false);toast('Charakter und noch vorhandene Panelzuordnungen wiederhergestellt.');
  }
 });
});
$('#newBook').onclick=()=>$('#bookFile').click();$('#settingsButton').onclick=()=>run(settingsModal);
$('#bookFile').onchange=()=>run(async()=>{const file=$('#bookFile').files[0];if(!file||!checkDirty())return;toast('Buch wird eingelesen …');const form=new FormData();form.append('file',file);const b=await api('/api/import',{method:'POST',body:form});S.dirty=false;await loadBooks();await openBook(b.id);$('#bookFile').value='';toast('Buch und Kapitel importiert.')});
window.addEventListener('beforeunload',event=>{if(S.dirty){event.preventDefault();event.returnValue=''}});
setInterval(()=>run(async()=>{if(!S.book)return;const updated=await api('/api/projects/'+S.book.id);const newlyDone=updated.jobs.filter(j=>j.state==='done'&&!S.seenDone.has(j.id));updated.jobs.filter(j=>j.state==='done').forEach(j=>S.seenDone.add(j.id));const changed=JSON.stringify(updated.jobs)!==JSON.stringify(S.book.jobs);S.book=updated;refreshStyleMagic();if(newlyDone.length&&!S.dirty&&S.chapter){const selected=S.selected,page=S.page;await loadChapter(S.chapter.id,false);if(allPanels().some(p=>p.id===selected))S.selected=selected;S.page=page;render();toast('Auftrag abgeschlossen. Kapitel aktualisiert.')}else if(changed&&!S.dirty){render();renderRail()}else if(changed&&$('#jobArea'))$('#jobArea').innerHTML=jobsHTML()}),3000);
run(async()=>{await loadBooks();render();const selected=localStorage.getItem('manga-book');if(selected&&S.books.some(b=>b.id===selected))await openBook(selected);await checkConnection()});
