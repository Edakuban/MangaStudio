const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const test=require('node:test');
const assert=require('node:assert/strict');

function harness(){
 const nodes=new Map();
 const get=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',dataset:{},showModal(){},close(){}});return nodes.get(id)};
 const context=vm.createContext({document:{querySelector:get,addEventListener(){}},window:{addEventListener(){}},
   localStorage:{getItem(){return null},setItem(){}},setInterval(){},setTimeout(){},clearTimeout(){},
   FormData,console,crypto:globalThis.crypto,structuredClone});
 let source=fs.readFileSync(path.join(__dirname,'../mangastudio/static/app.js'),'utf8');
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../mangastudio/static/lettering.js'),'utf8'),context);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../mangastudio/static/dramaturgy.js'),'utf8'),context);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../mangastudio/static/page_flow.js'),'utf8'),context);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../mangastudio/static/book_style.js'),'utf8'),context);
 const start=source.lastIndexOf('\nrun(async()=>{await loadBooks();');
 assert.ok(start>0,'Expected a separate application bootstrap');
 vm.runInContext(source.slice(0,start),context);
 vm.runInContext(`S.book={id:'book',characters:[{id:'char',name:'Eira',description:'Silver hair',aliases:'',image:'active.png',
  render_source:'source.png',manga_draft:{image:'draft.png',source_image:'source.png',analysis:{observations:'Silbernes Haar.',description:'Silver hair',uncertainty:''}}}],jobs:[]};`,context);
 return {context,nodes};
}

test('character profile shows second upload below the normal reference plus review and opt-in adoption',()=>{
 const {context,nodes}=harness();
 vm.runInContext(`characterModal('char')`,context);
 const html=nodes.get('#modalContent').innerHTML;
 assert.ok(html.indexOf('name="render_file"')>html.indexOf('name="file"'));
 assert.match(html,/Ursprünglicher Charakterrender/);
 assert.match(html,/data-action="accept-character-render"/);
 assert.match(html,/id="useRenderDescription" type="checkbox">/);
 assert.doesNotMatch(html,/id="useRenderDescription" type="checkbox" checked/);
});

test('saving an existing profile sends render to the dedicated analysis route, not the active-image upload',async()=>{
 const {context}=harness();
 // Construct browser FormData values in the same VM as the application.
 context.Blob=Blob;
 vm.runInContext(`calls=[];api=async(url,options)=>{calls.push(url);return {}};closeModal=()=>{};refreshProject=async()=>{};toast=()=>{};
 form={dataset:{id:'char'}};data=new Map([['name','Eira'],['description','Silver hair'],['aliases',''],['file',{size:0}],['render_file',new Blob(['source'],{type:'image/png'})]]);`,context);
 await vm.runInContext('saveCharacterForm(form,data)',context);
 assert.deepEqual(Array.from(context.calls),['/api/projects/book/characters/char','/api/projects/book/characters/char/render']);
});

test('cast shows chapter-scoped autoadd, delete and archived-character restore controls',()=>{
 const {context,nodes}=harness();
 vm.runInContext(`S.book.chapters=[{id:'chapter1',title:'Aktuelles Kapitel'}];S.chapter={id:'chapter1'};
 S.book.deleted_characters=[{id:'old',name:'Entfernt'}];renderCharacters();`,context);
 const html=Array.from(nodes.values()).map(n=>n.innerHTML).join('');
 assert.match(html,/characterChapterSelect/);
 assert.match(html,/Aktuelles Kapitel/);
 assert.match(html,/data-action="autoadd-characters"/);
 assert.match(html,/data-action="delete-character"/);
 assert.match(html,/data-action="restore-character"/);
 assert.match(html,/Entfernt/);
});

test('dialog editor offers independent horizontal and vertical positions',()=>{
 const {context,nodes}=harness();
 vm.runInContext(`S.selected='panel';S.scenes=[{panels:[{id:'panel',description:'Test',visual_prompt:'Test',characters:[],caption:'',
  bubbles:[{speaker:'Sam',text:'Hallo',side:'left',vertical:'bottom'}],focus_x:.5,focus_y:.5}]}];renderEditor();`,context);
 const html=nodes.get('#panelEditor').innerHTML;
 assert.match(html,/data-bfield="side"/);
 assert.match(html,/data-bfield="vertical"/);
 assert.match(html,/value="bottom" selected>Unten/);
 assert.match(html,/value="left" selected>Links/);
});

test('panel editor shows a separate pose field for each selected person and AI actions',()=>{
 const {context,nodes}=harness();
 vm.runInContext(`S.book.characters.push({id:'second',name:'Ivo'});S.selected='panel';
 S.scenes=[{panels:[{id:'panel',description:'Test',visual_prompt:'Test',characters:['char','second'],
 character_poses:{char:'Kneeling & looking down'},caption:'',bubbles:[],focus_x:.5,focus_y:.5}]}];renderEditor();`,context);
 const html=nodes.get('#panelEditor').innerHTML;
 assert.match(html,/data-pose-character="char"/);
 assert.match(html,/data-pose-character="second"/);
 assert.match(html,/Kneeling &amp; looking down/);
 assert.match(html,/data-action="generate-poses"/);
 assert.match(html,/data-action="generate-chapter-poses"/);
});

test('panel deletion uses the clicked panel, requires confirmation and respects running jobs',()=>{
 const {context}=harness();
 vm.runInContext(`S.scenes=[{panels:[{id:'a'},{id:'b'},{id:'c'}]}];S.selected='a';
 renderScenes=()=>{};renderEditor=()=>{};renderPreview=()=>{};dirty=()=>{S.dirty=true};confirm=()=>false;
 removePanel('b');`,context);
 assert.equal(vm.runInContext('allPanels().length',context),3);
 vm.runInContext(`confirm=()=>true;removePanel('b');`,context);
 assert.equal(vm.runInContext('allPanels().map(p=>p.id).join(",")',context),'a,c');
 assert.equal(vm.runInContext('S.selected',context),'a');
 vm.runInContext(`S.book.jobs=[{state:'running'}];removePanel('a');`,context);
 assert.equal(vm.runInContext('allPanels().length',context),2);
 vm.runInContext(`S.book.jobs=[];removePanel('a');`,context);
 assert.equal(vm.runInContext('S.selected',context),'c');
 vm.runInContext(`removePanel('c')`,context);
 assert.equal(vm.runInContext('S.scenes.length',context),0);
 assert.equal(vm.runInContext('S.selected',context),null);
});

test('clearing a chapter storyboard requires confirmation and keeps character data',()=>{
 const {context}=harness();
 vm.runInContext(`S.scenes=[{id:'scene',panels:[{id:'panel'}]}];S.selected='panel';
 renderScenes=()=>{};renderEditor=()=>{};renderPreview=()=>{};dirty=()=>{S.dirty=true};confirm=()=>false;
 clearStoryboard();`,context);
 assert.equal(vm.runInContext('S.scenes.length',context),1);
 vm.runInContext(`confirm=()=>true;S.book.jobs=[{state:'running'}];clearStoryboard();`,context);
 assert.equal(vm.runInContext('S.scenes.length',context),1);
 vm.runInContext(`S.book.jobs=[];clearStoryboard();`,context);
 assert.equal(vm.runInContext('S.scenes.length',context),0);
 assert.equal(vm.runInContext('S.book.characters[0].name',context),'Eira');
 assert.equal(vm.runInContext('S.dirty',context),true);
});

test('description generation saves current form before submitting image job',async()=>{
 const {context}=harness();
 vm.runInContext(`calls=[];api=async(url,options)=>{calls.push({url,options});return {id:'newchar'}};
 closeModal=()=>{};refreshProject=async()=>{};toast=()=>{};
 form={dataset:{id:'char'}};data=new Map([['name','Eira'],['description','New appearance'],['aliases',''],['file',{size:0}],['render_file',{size:0}]]);`,context);
 await vm.runInContext('saveCharacterForm(form,data,true)',context);
 assert.deepEqual(Array.from(context.calls,c=>c.url),['/api/projects/book/characters/char','/api/projects/book/characters/char/generate']);
 assert.equal(JSON.parse(context.calls[0].options.body).description,'New appearance');
 vm.runInContext(`calls=[];form={dataset:{id:''}}`,context);
 await vm.runInContext('saveCharacterForm(form,data,true)',context);
 assert.deepEqual(Array.from(context.calls,c=>c.url),['/api/projects/book/characters','/api/projects/book/characters/newchar/generate']);
});

test('description draft review needs no uploaded source or invented image analysis',()=>{
 const {context,nodes}=harness();
 vm.runInContext(`S.book.characters[0].manga_draft={origin:'description',image:'draft.png',description:'Silver hair'};characterModal('char')`,context);
 const html=nodes.get('#modalContent').innerHTML;
 assert.match(html,/name="file"/);
 assert.match(html,/name="render_file"/);
 assert.match(html,/data-action="generate-character-description"/);
 assert.match(html,/AUS BESCHREIBUNG ERZEUGT/);
 assert.match(html,/data-action="accept-character-render"/);
 assert.doesNotMatch(html,/URSPRÜNGLICHER RENDER|Erkannte Merkmale|useRenderDescription|assets\/undefined/);
});

test('book style suggestion stays separate from the current editable style',()=>{
 const {context,nodes}=harness();
 vm.runInContext(`S.book.style='Author style';S.book.title='Test book';S.book.style_draft={style:'Suggested style',rationale:'Aus dem Buch abgeleitet.',sections:3,base_style:'Author style'};bookSettingsModal();`,context);
 const html=nodes.get('#modalContent').innerHTML;
 assert.match(html,/>Author style<\/textarea>/);
 assert.match(html,/data-style-action="analyze"/);
 assert.match(html,/data-style-action="use"/);
 assert.match(html,/Suggested style/);
 assert.match(html,/erst|speicherst/);
 assert.equal(vm.runInContext('S.book.style',context),'Author style');
});

test('using a style draft only fills the field and rejects stale drafts',()=>{
 const {context,nodes}=harness();
 const field={value:'Unsaved manual style'};
 nodes.set('#bookSettingsForm',{dataset:{bookId:'book'},querySelector(){return field}});
 vm.runInContext(`toast=()=>{};S.book.style='Saved style';S.book.style_draft={style:'Suggested style'};useStyleDraft();`,context);
 assert.equal(field.value,'Suggested style');
 assert.equal(vm.runInContext('S.book.style',context),'Saved style');
 vm.runInContext('S.book.style_draft_stale=true',context);
 field.value='Manual correction';
 assert.throws(()=>vm.runInContext('useStyleDraft()',context),/nicht aktuell/);
 assert.equal(field.value,'Manual correction');
});

test('book deletion requires confirmation and exposes restoration in the library',async()=>{
 const {context,nodes}=harness();
 vm.runInContext(`S.book.title='Testbuch';S.book.style='Ink';S.book.chapters=[];S.books=[];bookSettingsModal();`,context);
 assert.match(nodes.get('#modalContent').innerHTML,/data-action="delete-book"/);
 vm.runInContext(`api=async()=>{throw Error('Must not delete without confirmation')};`,context);
 await vm.runInContext('deleteBook()',context);
 assert.equal(nodes.get('#bookDeleteConfirm').hidden,false);
 assert.match(nodes.get('#modalContent').innerHTML,/data-action="confirm-delete-book"/);
 assert.equal(vm.runInContext('S.book.title',context),'Testbuch');
 vm.runInContext('renderRail()',context);
 assert.match(nodes.get('#bookList').innerHTML,/data-action="deleted-books"/);
});

test('deleted books show title and restore action',async()=>{
 const {context,nodes}=harness();
 vm.runInContext(`api=async()=>[{id:'oldbook',title:'Old <book>'}];`,context);
 await vm.runInContext('deletedBooksModal()',context);
 const html=nodes.get('#modalContent').innerHTML;
 assert.match(html,/Old &lt;book&gt;/);
 assert.match(html,/data-action="restore-book" data-id="oldbook"/);
});

test('lettering editor exposes shapes, readable font sizing and direct page editing',()=>{
 const {context,nodes}=harness();
 vm.runInContext(`S.selected='p';S.scenes=[{panels:[{id:'p',description:'Test',visual_prompt:'Test',characters:[],bubbles:[{text:'Hallo',speaker:'Sam'}],caption:'',focus_x:.5,focus_y:.5}]}];renderEditor();`,context);
 const html=nodes.get('#panelEditor').innerHTML;
 assert.match(html,/data-bfield="shape"/);
 assert.match(html,/Gedanke/);assert.match(html,/Flüstern/);assert.match(html,/Schreien/);
 assert.match(html,/data-action="edit-lettering"/);
 assert.match(html,/data-bfield="font_size"/);
 assert.match(html,/data-field="page_break_before"/);
});

test('manual bubble fields preserve booleans, clamp bounds and leave image prompt untouched',()=>{
 const {context}=harness();
 vm.runInContext(`S.selected='p';S.scenes=[{panels:[{id:'p',visual_prompt:'Keep artwork',bubbles:[{text:'Hallo',x:.7,width:.2,y:.1,height:.2}]}]}];
 dirty=()=>{};renderPreview=()=>{};requestPagePreview=()=>{};
 updateBubbleField({dataset:{bi:'0',bfield:'width',percent:'true'},type:'number',value:'60'},panel());
 updateBubbleField({dataset:{bi:'0',bfield:'show_tail'},type:'checkbox',checked:false},panel());`,context);
 assert.equal(vm.runInContext('panel().bubbles[0].x',context),.4);
 assert.equal(vm.runInContext('panel().bubbles[0].width',context),.6);
 assert.equal(vm.runInContext('panel().bubbles[0].show_tail',context),false);
 assert.equal(vm.runInContext('panel().visual_prompt',context),'Keep artwork');
});

test('SVG preview uses shared geometry and prints dialogue without speaker prefix',()=>{
 const {context}=harness();
 context.testGeometry={width:200,height:200,bubbles:[{index:0,x:10,y:10,width:140,height:50,shape:'speech',font_size:10,
  points:[[10,10],[150,10],[150,60]],thought_dots:[],tail:null,lines:['Hallo!'],text_y:35,text_x:80}],caption:null,issues:[]};
 const html=vm.runInContext(`svgLettering({lettering:testGeometry},{id:'p',bubbles:[{speaker:'Sam',text:'Hallo!'}]})`,context);
 assert.match(html,/<svg/);assert.match(html,/Hallo!/);
 assert.doesNotMatch(html,/Sam: Hallo/);
});

test('dramaturgy review compares source and proposals without applying them implicitly',()=>{
 const {context}=harness();
 vm.runInContext(`S.chapter={dramaturgy_review:{id:'review',summaries:['Fund zeigen'],suggestions:[{
 id:'finding',status:'pending',stale:false,action:'replace',category:'missing_beat',panel_label:'P2',title:'Ein Fund',reason:'Besser sichtbar machen',
 source_start:2,source_end:2,source_excerpt:'Ein offenes Buch lag dort.',before:{description:'Steht',visual_prompt:'Standing',bubbles:[]},
 replacement:{description:'Liest',visual_prompt:'Reading',bubbles:[]}}]}}`,context);
 let html=vm.runInContext('dramaturgyHTML()',context);
 assert.match(html,/Vorher \/ Vorschlag/);assert.match(html,/Ein offenes Buch lag dort/);
 assert.match(html,/data-review-action="apply"/);assert.match(html,/data-review-action="dismiss"/);
 assert.match(html,/Standing/);assert.match(html,/Reading/);
 vm.runInContext('S.chapter.dramaturgy_review.suggestions[0].stale=true',context);
 html=vm.runInContext('dramaturgyHTML()',context);
 assert.match(html,/data-review-action="apply"[^>]*disabled/);
});

test('rejecting dramaturgy advice keeps unsaved scene edits',async()=>{
 const {context}=harness();
 vm.runInContext(`S.chapter={id:'chapter',dramaturgy_review:{id:'review'}};S.scenes=[{panels:[{id:'p',description:'Meine ungespeicherte Fassung'}]}];
 S.dirty=true;render=()=>{};renderRail=()=>{};toast=()=>{};
 api=async(url)=>url.includes('/dramaturgy/')?({dramaturgy_review:{id:'review',suggestions:[{id:'finding',status:'dismissed'}]}}):S.book;`,context);
 await vm.runInContext(`decideDramaturgy('dismiss','finding')`,context);
 assert.equal(vm.runInContext('S.scenes[0].panels[0].description',context),'Meine ungespeicherte Fassung');
 assert.equal(vm.runInContext('S.dirty',context),true);
 await assert.rejects(()=>vm.runInContext(`decideDramaturgy('apply','finding')`,context),/zuerst speichern/);
});

test('manual page splits, merges and boundary changes preserve exact panel sequence',()=>{
 const {context}=harness();
 vm.runInContext(`flowCurrent={plan:{pages:[{panels:['a','b','c'],turn:'none',layout:'balanced'},{panels:['d','e'],turn:'none',layout:'balanced'}]}};flowChanged=()=>{};splitFlowPage(0,1);`,context);
 assert.equal(vm.runInContext('flowCurrent.plan.pages.map(p=>p.panels.length).join(",")',context),'1,2,2');
 vm.runInContext('mergeFlowPages(0);moveFlowBoundary(0,"last-next")',context);
 assert.equal(vm.runInContext('flowCurrent.plan.pages.flatMap(p=>p.panels).join(",")',context),'a,b,c,d,e');
 assert.equal(vm.runInContext('flowCurrent.plan.pages.map(p=>p.panels.length).join(",")',context),'2,3');
});

test('page flow banner keeps proposal separate from active layout and blocks busy actions',()=>{
 const {context}=harness();
 vm.runInContext(`S.chapter={page_flow:{proposal:{status:'pending',stale:false},active:null}}`,context);
 let html=vm.runInContext('pageFlowBannerHTML()',context);
 assert.match(html,/Seitenvorschlag prüfen/);assert.doesNotMatch(html,/Aktiver Seitenplan:/);
 vm.runInContext(`S.book.jobs=[{state:'running'}]`,context);
 html=vm.runInContext('pageFlowBannerHTML()',context);
 assert.match(html,/data-flow-action="open" disabled/);
});


test('settings show the saved model with license and keep the preset outside the API form payload',async()=>{
 const {context,nodes}=harness();
 vm.runInContext(`api=async()=>({comfy_url:'http://127.0.0.1:8188',text_model:'text',vision_model:'vision',image_model:'flux-2-klein-9b-fp8.safetensors',image_encoder:'qwen_3_8b_fp8mixed.safetensors',image_vae:'vae',timeout:1800});`,context);
 await vm.runInContext('settingsModal()',context);
 const html=nodes.get('#modalContent').innerHTML;
 assert.match(html,/value="9b" selected/);
 assert.match(html,/FLUX Non-Commercial License/);
 assert.match(html,/gesonderte BFL-Lizenz/);
 assert.match(html,/id="settingsImagePreset"/);
 assert.doesNotMatch(html,/name="(?:image_preset|settingsImagePreset)"/);
 assert.match(html,/Erst Speichern aktiviert/);
});

test('selecting Klein 4B and 9B changes the model and matching encoder without saving or changing other settings',()=>{
 const {context,nodes}=harness();
 vm.runInContext(`S.settings={image_model:'flux-2-klein-9b-fp8.safetensors',image_vae:'keep-vae'};S.connection={image_models:['flux-2-klein-4b-fp8.safetensors','flux-2-klein-9b-fp8.safetensors']};`,context);
 context.document.querySelector('#settingsImageModel').value='flux-2-klein-9b-fp8.safetensors';
 vm.runInContext(`chooseImagePreset('4b')`,context);
 assert.equal(nodes.get('#settingsImageModel').value,'flux-2-klein-4b-fp8.safetensors');
 assert.equal(nodes.get('#settingsImageEncoder').value,'qwen_3_4b.safetensors');
 assert.match(nodes.get('#settingsModelLicense').innerHTML,/Apache 2.0/);
 assert.equal(vm.runInContext('S.settings.image_model',context),'flux-2-klein-9b-fp8.safetensors');
 assert.equal(vm.runInContext('S.settings.image_vae',context),'keep-vae');
 vm.runInContext(`chooseImagePreset('9b')`,context);
 assert.equal(nodes.get('#settingsImageEncoder').value,'qwen_3_8b_fp8mixed.safetensors');
 assert.match(nodes.get('#settingsModelLicense').innerHTML,/Non-Commercial/);
});

test('manual and base filenames never receive an automatic permissive model license',()=>{
 const {context,nodes}=harness();
 context.document.querySelector('#settingsImageModel').value='flux-2-klein-base-4b-fp8.safetensors';
 vm.runInContext('refreshModelLicense()',context);
 assert.equal(nodes.get('#settingsImagePreset').value,'custom');
 assert.match(nodes.get('#settingsModelLicense').innerHTML,/nicht automatisch zugeordnet/);
 context.document.querySelector('#settingsImageModel').value='my-custom-model.safetensors';
 vm.runInContext('refreshModelLicense()',context);
 assert.doesNotMatch(nodes.get('#settingsModelLicense').innerHTML,/kommerzielle Nutzung erlaubt/);
});


test('export dialog supports several variants, grayscale only for color, and explicit draft mode',()=>{
 const {context,nodes}=harness();
 vm.runInContext(`S.book.exports=[];S.book.monochrome=false;exportModal()`,context);
 let html=nodes.get('#modalContent').innerHTML;
 for(const kind of ['pdf','print_pdf','grayscale','pages','webcomic'])assert.match(html,new RegExp('value="'+kind+'"'));
 assert.match(html,/data-action="export-selected"/);
 assert.match(html,/id="exportDraft"/);
 assert.doesNotMatch(html,/value="grayscale" disabled/);
 vm.runInContext(`S.book.monochrome=true;exportModal()`,context);
 html=nodes.get('#modalContent').innerHTML;
 assert.match(html,/value="grayscale" disabled/);
});

test('multi-export submits all selected formats once and downloads a single bundle',async()=>{
 const {context,nodes}=harness();
 let clicked=0;
 context.document.body={appendChild(){}};
 context.document.createElement=()=>({click(){clicked++},remove(){}});
 context.document.querySelectorAll=()=>[{value:'pdf'},{value:'pages'},{value:'webcomic'},{value:'grayscale',disabled:true}];
 context.document.querySelector('#exportDraft').value='draft';
 vm.runInContext(`calls=[];savePlan=async()=>{};api=async(url,options)=>{if(!options?.body)return S.book;calls.push({url,data:JSON.parse(options.body)});return {path:'books/book/exports/run/bundle.zip',name:'bundle.zip',pages:2,files:[{path:'x.pdf',name:'x.pdf',label:'PDF'},{path:'pages.zip',name:'pages.zip',label:'Seitenbilder'}]}};`,context);
 const button={disabled:false};context.exportButton=button;
 await vm.runInContext('exportSelected(exportButton)',context);
 assert.equal(context.calls.length,1);
 assert.deepEqual(Array.from(context.calls[0].data.formats),['pdf','pages','webcomic']);
 assert.equal(context.calls[0].data.draft,true);
 assert.equal(clicked,1);
 assert.equal(button.disabled,false);
 assert.match(nodes.get('#exportResult').innerHTML,/bundle.zip/);
 context.document.querySelectorAll=()=>[];
 assert.throws(()=>vm.runInContext('selectedExportFormats()',context),/mindestens ein/);
});

test('standard pages escape saved text and persist settings without accepting a file path',async()=>{
 const {context,nodes}=harness();
 vm.runInContext(`S.book.publication={enabled:true,title:'<Title>',imprint:'<script>Test</script>',cover_image:'cover.png'};exportModal()`,context);
 const html=nodes.get('#modalContent').innerHTML;
 assert.match(html,/id="publicationEnabled" type="checkbox" checked/);
 assert.match(html,/&lt;script&gt;Test&lt;\/script&gt;/);
 assert.match(html,/id="publicationCover"/);
 assert.match(html,/4 Impressum/);
 context.document.querySelector('#publicationEnabled').checked=true;
 for(const [key,value] of Object.entries({Title:'Titel',Subtitle:'Band 1',Author:'Autor',Imprint:'Mein Impressum'}))context.document.querySelector('#publication'+key).value=value;
 vm.runInContext(`calls=[];api=async(url,options)=>{const data=JSON.parse(options.body);calls.push({url,data});return {...data,cover_image:'cover.png'}}`,context);
 await vm.runInContext('savePublication()',context);
 assert.equal(context.calls[0].url,'/api/projects/book/publication');
 assert.equal(context.calls[0].data.imprint,'Mein Impressum');
 assert.ok(!('cover_image' in context.calls[0].data));
 assert.equal(vm.runInContext('S.book.publication.cover_image',context),'cover.png');
});
