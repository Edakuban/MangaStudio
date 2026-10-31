function dramaturgyPanelHTML(p){
 if(!p)return '<p class="note">Dieses Panel entfällt.</p>';
 const cast=(p.characters||[]).map(id=>S.book.characters.find(c=>c.id===id)?.name||'Nicht mehr vorhanden');
 return `<p><b>Handlung</b><br>${e(p.description)}</p><p><b>Bildanweisung</b><br>${e(p.visual_prompt)}</p><p class="note">${e({wide:'Totale',medium:'Halbnah',close:'Nahaufnahme',detail:'Detail'}[p.shot]||'Halbnah')} · ${e({establishing:'Orientierung',action:'Handlung',reaction:'Reaktion',detail:'Detail',reveal:'Enthüllung'}[p.beat]||'Handlung')}${cast.length?' · '+e(cast.join(', ')):''}</p>${Object.values(p.character_poses||{}).length?`<p><b>Körperhaltung</b><br>${Object.entries(p.character_poses).map(([id,pose])=>e(S.book.characters.find(c=>c.id===id)?.name||'Figur')+': '+e(pose)).join('<br>')}</p>`:''}<p><b>Dialog</b><br>${p.bubbles?.length?p.bubbles.map(b=>`${e(b.speaker||'Ohne Sprecher')}: ${e(b.text)}`).join('<br>'):'Kein Dialog'}</p><p><b>Erzählkasten</b><br>${p.caption?e(p.caption):'Keiner'}</p>`;
}
function dramaturgyHTML(){
 const review=S.chapter?.dramaturgy_review;if(!review)return '';
 const pending=review.suggestions.filter(f=>f.status==='pending');
 const actions={replace:'Panel ersetzen',remove:'Panel streichen',insert_before:'Panel davor ergänzen',insert_after:'Panel danach ergänzen',insert_scene_before:'Szene davor ergänzen',insert_scene_after:'Szene danach ergänzen'};
 const categories={missing_beat:'Fehlender Handlungsschritt',repetition:'Wiederholung',show_dont_tell:'Zeigen statt erklären',continuity:'Zusammenhang',readability:'Lesefluss'};
 return `<details id="dramaturgyReview" class="dramaturgy-review" ${pending.length?'open':''}><summary>Dramaturgie-Prüfung · ${pending.length} offene Vorschläge</summary><p class="note">Die Prüfung verändert keine Panels. Vergleiche jeden Vorschlag mit seiner Buchstelle und übernimm ihn einzeln. ${S.dirty?'Ungespeicherte Änderungen zuerst speichern.':''}</p>${review.warnings?.length?`<div class="warning"><b>Prüfung teilweise unvollständig</b><p>Diese Vorschläge wurden nach zwei Korrekturen verworfen. Die angezeigten Vorschläge wurden einzeln geprüft; weitere Probleme können offen sein.</p>${review.warnings.map(e).join('<br>')}</div>`:''}${review.summaries.map(s=>`<p class="review-summary">${e(s)}</p>`).join('')}${!review.suggestions.length?'<p>Die KI hat für diesen Stand keine konkreten Änderungen vorgeschlagen.</p>':''}${review.suggestions.map(f=>`<article class="review-finding"><div class="eyebrow">${e(categories[f.category]||f.category)} · ${e(f.current_panel_label||f.panel_label)}</div><h3>${e(f.title)}</h3><p>${e(f.reason)}</p><details><summary>Buchstelle · Abs. ${f.source_start}–${f.source_end}</summary><p class="evidence">${e(f.source_excerpt)}</p></details><details><summary>${e(actions[f.action])}: Vorher / Vorschlag vergleichen</summary><div class="review-comparison"><div><h4>${f.action.startsWith('insert')?'Vorhandenes Ankerpanel':'Bisheriges Panel'}</h4>${dramaturgyPanelHTML(f.before)}</div><div><h4>${f.action==='remove'?'Weglassen':'Vorschlag'}</h4>${dramaturgyPanelHTML(f.replacement)}</div></div></details>${f.status==='pending'?`${f.stale?'<p class="warning">Panel oder Buchstelle wurde inzwischen geändert. Diesen Vorschlag bitte neu prüfen lassen.</p>':''}<div class="action-row"><button class="primary small" data-review-action="apply" data-finding-id="${e(f.id)}" ${busy()||f.stale||S.dirty?'disabled':''}>${e(actions[f.action])} übernehmen</button><button class="small quiet" data-review-action="dismiss" data-finding-id="${e(f.id)}" ${busy()?'disabled':''}>Verwerfen</button></div>`:`<p class="note">${f.status==='applied'?'Übernommen':'Verworfen'}</p>`}</article>`).join('')}</details>`;
}
async function startDramaturgyReview(){
 await savePlan();await post(`/api/chapters/${S.chapter.id}/dramaturgy`);
 S.view='storyboard';await refreshProject();toast('KI vergleicht Buch und Storyboard. Vorschläge werden noch nicht angewendet.');
}
async function decideDramaturgy(action,findingId){
 if(action==='apply'&&S.dirty)throw Error('Bitte deine Storyboard-Änderungen zuerst speichern.');
 const review=S.chapter?.dramaturgy_review;if(!review)return;
 const selected=S.selected;
 const chapter=await post(`/api/chapters/${S.chapter.id}/dramaturgy/${findingId}`,{review_id:review.id,action});
 if(action==='dismiss'&&S.dirty){S.chapter.dramaturgy_review=chapter.dramaturgy_review}
 else{S.chapter=chapter;S.scenes=structuredClone(chapter.scenes);S.dirty=false;
  const finding=chapter.dramaturgy_review.suggestions.find(f=>f.id===findingId);
  S.selected=finding?.inserted_panel_id|| (allPanels().some(p=>p.id===selected)?selected:allPanels()[0]?.id||null)}
 S.book=await api(`/api/projects/${S.book.id}`);render();renderRail();
 toast(action==='apply'?'Vorschlag übernommen und gespeichert. Betroffene Bilder bei Bedarf neu erzeugen.':'Vorschlag verworfen.');
}
document.addEventListener('click',event=>{
 const t=event.target.closest?.('[data-review-action]');if(!t||t.disabled)return;
 t.disabled=true;run(async()=>{try{await decideDramaturgy(t.dataset.reviewAction,t.dataset.findingId)}finally{t.disabled=false}});
});
