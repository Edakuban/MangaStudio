function styleMagicHTML(){
 const draft=S.book?.style_draft,stale=S.book?.style_draft_stale;
 const job=S.book?.jobs?.find(j=>j.kind==='book_style'&&['queued','running'].includes(j.state));
 return `<div class="action-row"><button type="button" class="small" data-style-action="analyze" ${busy()?'disabled':''}>✦ Bildsprache aus Buch vorschlagen</button></div><p class="note">Liest das gesamte Buch abschnittsweise mit der lokalen Text-KI. Kann je nach Buchlänge dauern. Dein eingetragener Stil bleibt erhalten, bis du einen Vorschlag ins Feld übernimmst und speicherst.</p>${job?`<p class="note" role="status">${e(job.message)} · ${Math.round(job.progress*100)} %</p>`:''}${draft?`<details open class="render-upload"><summary><b>KI-Stilvorschlag · ${draft.sections} Textabschnitte</b></summary>${stale?'<p class="warning">Buchtext wurde seit der Analyse geändert. Bitte neu analysieren.</p>':''}<p>${e(draft.rationale)}</p><p style="white-space:pre-wrap">${e(draft.style)}</p>${draft.base_style!==S.book.style?'<p class="note">Der gespeicherte Stil wurde seit der Analyse geändert. Vor der Übernahme vergleichen.</p>':''}<button type="button" class="small" data-style-action="use" ${stale||busy()?'disabled':''}>Vorschlag ins Feld übernehmen</button></details>`:''}`;
}
function refreshStyleMagic(){
 const form=$('#bookSettingsForm');
 if($('#modal')?.open&&form?.dataset?.bookId===S.book?.id){
  const box=$('#styleMagic'),html=styleMagicHTML();
  if(box&&box.dataset.styleHTML!==html){box.innerHTML=html;box.dataset.styleHTML=html;}
 }
}
async function startStyleAnalysis(){
 const form=$('#bookSettingsForm'),id=form?.dataset?.bookId;
 if(!id||id!==S.book?.id)throw Error('Bitte die Bucheinstellungen neu öffnen.');
 await savePlan();await post(`/api/projects/${id}/style-analysis`);
 await refreshProject();refreshStyleMagic();
 toast('KI analysiert die Bildsprache des Buchs. Der Stilvorschlag erscheint hier nach Abschluss.');
}
function useStyleDraft(){
 const form=$('#bookSettingsForm'),draft=S.book?.style_draft;
 if(!draft||S.book.style_draft_stale||busy()||form?.dataset?.bookId!==S.book.id)throw Error('Stilvorschlag nicht aktuell. Bitte neu laden.');
 form.querySelector('[name="style"]').value=draft.style;
 toast('Vorschlag ins Textfeld übernommen. Du kannst ihn bearbeiten; erst „Speichern“ aktiviert ihn.');
}
document.addEventListener('click',event=>{
 const t=event.target.closest?.('[data-style-action]');if(!t||t.disabled)return;
 run(async()=>{if(t.dataset.styleAction==='use')useStyleDraft();else{t.disabled=true;try{await startStyleAnalysis()}finally{t.disabled=false}}});
});
