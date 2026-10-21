// Charta renderer: shell behaviour, review flow, outputs grid, ask, picker.
// Desktop-aware: when desktop/preload.js is present we hand the native title bar
// and shortcut handling to Electron instead of the browser.
(function(){
'use strict';
const root=document.documentElement;
const saved=localStorage.getItem('charta-theme');
if(saved)root.dataset.theme=saved;
else if(matchMedia('(prefers-color-scheme: dark)').matches)root.dataset.theme='dark';
const DESKTOP=!!(window.charta&&window.charta.desktop);
const DEBUG=!!window.__CHARTA_DEBUG__;

// One icon language: the server ships the Lucide bodies, we wrap them here.
const icon=(name,size=18)=>{const body=(window.__ICONS__||{})[name];if(!body)return '';
 return '<svg viewBox="0 0 24 24" width="'+size+'" height="'+size+'" fill="none" stroke="currentColor"'
  +' stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+body+'</svg>';};
const escHtml=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function paintThemeIcon(){
 const dark=root.dataset.theme==='dark';
 const i=document.querySelector('[data-theme-icon]');if(i)i.innerHTML=icon(dark?'sun':'moon');
}
window.toggleTheme=()=>{
 root.dataset.theme=root.dataset.theme==='light'?'dark':'light';
 localStorage.setItem('charta-theme',root.dataset.theme||'light');
 if(DESKTOP)window.charta.setTheme(root.dataset.theme); // keep the native title bar in sync
 paintThemeIcon();
};
if(DESKTOP)window.charta.setTheme(root.dataset.theme||'light');
paintThemeIcon();

// --- native-feel: take the browser's own chrome shortcuts away --------------
// Electron also blocks these at the window level (desktop/main.js); this covers
// the plain-browser case. `--debug` gives everything back.
if(!DEBUG){
 document.addEventListener('contextmenu',e=>e.preventDefault());
 document.addEventListener('keydown',e=>{
  const k=(e.key||'').toLowerCase(),mod=e.ctrlKey||e.metaKey;
  const blocked=e.key==='F5'||e.key==='F12'
   ||(mod&&!e.shiftKey&&['r','f','p'].includes(k))
   ||(mod&&e.shiftKey&&['i','j','c'].includes(k));
  if(blocked){e.preventDefault();e.stopPropagation();}
 },true);
}

document.addEventListener('keydown',e=>{
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openPalette();}
 if(e.key==='/'&&!/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)){e.preventDefault();openPalette();}
 if(e.key==='Escape'){closePalette();closePicker();}
});
window.openPalette=()=>{const p=document.getElementById('palette');if(!p)return;p.style.display='flex';
 const i=document.getElementById('palInput');if(i){i.value='';palFilter('');i.focus();}};
window.closePalette=()=>{const p=document.getElementById('palette');if(p)p.style.display='none';};
window.openSettings=()=>{location.href='/settings?folder='+encodeURIComponent(folder());};
window.palFilter=q=>{document.querySelectorAll('#palList button').forEach(b=>{
 b.style.display=b.textContent.toLowerCase().includes((q||'').toLowerCase())?'':'none';});};
window.toast=(msg,undo)=>{const t=document.createElement('div');t.className='toast';t.setAttribute('role','status');
t.innerHTML=String(msg)+(undo?' <button class="btn" onclick="undoLast()">Undo</button>':'');document.body.appendChild(t);
setTimeout(()=>t.remove(),8000);};
window.folder=()=>new URLSearchParams(location.search).get('folder')||'';
async function api(p,o){const r=await fetch(p,o);if(!r.ok)throw new Error(await r.text());return r.json();}
const post=(path,body)=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})}).catch(e=>{toast('Something went wrong: '+e.message,false);throw e;});
window.undoLast=async()=>{await post('/api/undo?folder='+encodeURIComponent(folder()));location.reload();};
window.startWatching=async()=>{await post('/api/watch?folder='+encodeURIComponent(folder()));location.reload();};
window.stopWatching=async()=>{await post('/api/unwatch?folder='+encodeURIComponent(folder()));location.reload();};
window.scanNow=async()=>{await post('/api/scan?folder='+encodeURIComponent(folder()));location.reload();};
window.scanFolder=async(f)=>{
 const j=await post('/api/scan?folder='+encodeURIComponent(f));
 await pollScan(j.job);
 location.reload();
};
// Poll a running scan so a folder with hundreds of files shows its progress.
async function pollScan(job){
 if(!job)return;
 const bar=document.getElementById('scanProgress');
 while(true){
  let s;
  try{s=await api('/api/scan/status?job='+encodeURIComponent(job));}catch(e){return;}
  if(s.state==='done'||s.state==='failed'){
   if(bar)bar.innerHTML='';
   if(s.state==='failed'&&bar)bar.innerHTML='<div class="banner warn">The scan stopped: '
    +escHtml(s.error||'unknown error')+'</div>';
   return;
  }
  if(bar){
   const pct=s.total?Math.round((s.done/s.total)*100):0;
   bar.innerHTML='<div class="card"><div class="row"><span class="mono">'+escHtml(s.current||'starting…')+'</span>'
    +'<span class="spacer"></span><span class="chip">'+s.done+' / '+(s.total||'?')+'</span></div>'
    +'<div class="conf"><span style="width:'+pct+'%"></span></div></div>';
  }
  await new Promise(r=>setTimeout(r,400));
 }
}
window.watchFolder=async(f)=>{await post('/api/watch?folder='+encodeURIComponent(f));location.reload();};
window.unwatchFolder=async(f)=>{await post('/api/unwatch?folder='+encodeURIComponent(f));location.reload();};
// Switch one folder between suggest and auto mode.
window.setMode=async(f,mode)=>{
 try{
  await post('/api/mode?folder='+encodeURIComponent(f)+'&mode='+encodeURIComponent(mode));
  location.reload();
 }catch(err){toast('Could not change the mode for that folder.',false);}
};
// Ask a question about one specific folder from the Folders page.
window.askIn=async(f,id,q)=>{
 const box=document.getElementById(id);
 const input=document.getElementById(id+'-input');
 const question=(q||(input?input.value:'')).trim();
 if(!box||!question)return;
 if(input)input.value='';
 box.innerHTML='<div class="msg ai skel" style="min-width:200px">reading the folder…</div>';
 try{
  const j=await post('/api/ask?folder='+encodeURIComponent(f),{q:question});
  if(j.error){box.innerHTML='<div class="msg ai">'+escHtml(j.message||'Could not answer that.')+'</div>';return;}
  const cites=(j.citations||[]).map(c=>'<span class="chip cite mono">'+escHtml(c.file)+' p'+c.page+'</span>').join(' ');
  const meta=j.files?(' · '+j.files+' file(s)'+(j.cached?' (already read)':'')+' · '+escHtml(j.model||'')):'';
  box.innerHTML='<div class="msg ai"><div>'+escHtml(j.answer||'No answer.')+'</div>'
   +(meta?'<p class="muted" style="margin:var(--s2) 0 0;font-size:var(--fs-label)">'+meta+'</p>':'')+cites+'</div>';
 }catch(err){
  box.innerHTML='<div class="msg ai">Something went wrong: '+escHtml((err&&err.message)||'unknown error')+'</div>';
 }
};
// Open a file with the system's default app (PDF viewer, editor…).
window.openFile=async(f,rel)=>{
 try{
  await post('/api/file/open?folder='+encodeURIComponent(f),{path:rel});
  toast('Opened '+rel);
 }catch(err){toast('Could not open that file here.',false);}
};
// Show a file in Explorer / the file manager.
window.revealFile=async(f,rel)=>{
 try{await post('/api/file/reveal?folder='+encodeURIComponent(f),{path:rel});}
 catch(err){toast('Could not show that file.',false);}
};
// Ask about one specific file: open the Ask page with the question ready.
window.askAbout=(f,rel)=>{
 const q='What is in '+rel+'?';
 location.href='/ask?folder='+encodeURIComponent(f)+'&q='+encodeURIComponent(q);
};
// Read a file from the Files page: text, PDF, DOCX or a vision summary.
window.readFile=async(f,rel)=>{
 const holder=document.getElementById('reader');
 if(!holder)return;
 holder.innerHTML='<div class="card"><div class="skel" style="height:60px">reading…</div></div>';
 try{
  const j=await api('/api/file/read?folder='+encodeURIComponent(f)+'&path='+encodeURIComponent(rel));
  const body=(j.text||'').trim();
  holder.innerHTML='<div class="card fadein"><div class="card-head"><h3 class="mono">'
   +escHtml(j.file||rel)+'</h3><span class="chip">'+escHtml(j.method||'text')+' · '+j.pages+' page(s)</span></div>'
   +'<pre class="mono" style="white-space:pre-wrap;max-height:420px;overflow:auto">'
   +escHtml(body||'(no text)')+'</pre></div>';
 }catch(err){
  holder.innerHTML='<div class="card"><p class="muted">Could not read that file.</p></div>';
 }
};
// Edit a text file in place. The old version is kept as <name>.charta-old.
window.editFile=async(f,rel)=>{
 const holder=document.getElementById('reader');
 if(!holder)return;
 holder.innerHTML='<div class="card"><div class="skel" style="height:60px">loading…</div></div>';
 let text='';
 try{
  const j=await api('/api/file/read?folder='+encodeURIComponent(f)+'&path='+encodeURIComponent(rel));
  text=j.text||'';
 }catch(err){text='';}
 holder.innerHTML='<div class="card fadein"><div class="card-head"><h3 class="mono">'
  +escHtml(rel)+'</h3><span class="chip">editing — the old version is kept</span></div>'
  +'<textarea id="editArea" rows="14" style="width:100%">'+escHtml(text)+'</textarea>'
  +'<div class="row"><button type="button" class="btn btn-primary" onclick="saveFile('
  +JSON.stringify(f)+','+JSON.stringify(rel)+')">Save</button>'
  +'<button type="button" class="btn" onclick="readFile('+JSON.stringify(f)+','+JSON.stringify(rel)+')">Cancel</button>'
  +'</div></div>';
};
window.saveFile=async(f,rel)=>{
 const area=document.getElementById('editArea');
 const holder=document.getElementById('reader');
 try{
  const j=await post('/api/file/write?folder='+encodeURIComponent(f),{path:rel,text:area?area.value:''});
  toast('Saved '+rel+(j.backup?' (old version kept as '+j.backup+')':''));
  location.reload();
 }catch(err){
  if(holder)holder.innerHTML='<div class="card"><p class="muted">Could not save that file.</p></div>';
 }
};
// "Delete" means move aside: the file stays in .charta/trash and can come back.
window.trashFile=async(f,rel)=>{
 try{
  const j=await post('/api/file/trash?folder='+encodeURIComponent(f),{path:rel});
  toast('Moved '+rel+' to Charta\'s trash (not deleted)');
  location.reload();
 }catch(err){toast('Could not move that file to the trash.',false);}
};
window.restoreFile=async(f,rel)=>{
 try{
  await post('/api/file/restore?folder='+encodeURIComponent(f),{path:rel});
  toast('Brought back from the trash');
  location.reload();
 }catch(err){toast('Could not bring that file back.',false);}
};
window.approveOne=async(src)=>{await post('/api/approve?folder='+encodeURIComponent(folder()),{files:[src]});
 const card=document.querySelector('.prop-card');if(card)card.style.opacity='0.4';toast('Approved '+src,true);};
window.rejectOne=async(src)=>{await post('/api/reject?folder='+encodeURIComponent(folder()),{files:[src]});location.reload();};

// --- custom dropdowns (native <select> can't be themed or animated) --------
function initDropdowns(){
 document.querySelectorAll('.dd').forEach(dd=>{
  if(dd.dataset.wired)return;dd.dataset.wired='1';
  const btn=dd.querySelector('.dd-btn'),menu=dd.querySelector('.dd-menu');
  const opts=[...menu.querySelectorAll('li')],hidden=dd.querySelector('input[type=hidden]');
  const open=v=>{menu.hidden=!v;btn.setAttribute('aria-expanded',String(v));
   if(v){(opts.find(o=>o.getAttribute('aria-selected')==='true')||opts[0]).focus();}};
  const pick=li=>{opts.forEach(o=>{const on=o===li;o.setAttribute('aria-selected',String(on));o.classList.toggle('sel',on);});
   dd.dataset.value=li.dataset.value;if(hidden)hidden.value=li.dataset.value;
   btn.textContent=li.textContent;open(false);btn.focus();
   dd.dispatchEvent(new CustomEvent('dd:change',{detail:li.dataset.value,bubbles:true}));};
  opts.forEach(li=>{li.tabIndex=-1;li.addEventListener('click',ev=>{ev.stopPropagation();pick(li);});});
  btn.addEventListener('click',ev=>{ev.stopPropagation();open(menu.hidden);});
  dd.addEventListener('keydown',e=>{
   const i=opts.indexOf(document.activeElement);
   if(e.key==='ArrowDown'){e.preventDefault();(opts[i+1]||opts[0]).focus();}
   else if(e.key==='ArrowUp'){e.preventDefault();(opts[i-1]||opts[opts.length-1]).focus();}
   else if(e.key==='Enter'||e.key===' '){if(i>-1){e.preventDefault();pick(opts[i]);}}
   else if(e.key==='Escape'){open(false);btn.focus();}
  });
 });
 document.addEventListener('click',()=>document.querySelectorAll('.dd-menu').forEach(m=>{m.hidden=true;}));
}

// --- custom folder picker (folders only; protected paths not selectable) ---
const PICKER={path:''};
const joinPath=(a,b)=>/[\\/]$/.test(a)?a+b:a+(a.includes('\\')?'\\':'/')+b;
async function fsList(path){
 let j;
 try{const r=await fetch('/api/fs/list'+(path?'?path='+encodeURIComponent(path):''));j=await r.json();}
 catch(err){const n=document.getElementById('fsNote');if(n)n.textContent='Could not read that folder.';return;}
 PICKER.path=j.path;
 const pathEl=document.getElementById('fsPath');if(pathEl)pathEl.textContent=j.path;
 const ul=document.getElementById('fsList');ul.innerHTML='';
 (j.roots||[]).filter(d=>d!==j.path).forEach(d=>ul.appendChild(fsRow('drive',d,()=>fsList(d))));
 (j.dirs||[]).forEach(name=>ul.appendChild(fsRow('folder',name,()=>fsList(joinPath(j.path,name)))));
 if(!j.dirs.length)ul.appendChild(fsRow('empty','(no subfolders)',null));
 const use=document.getElementById('fsUse');if(use)use.disabled=!!j.protected;
 const up=document.getElementById('fsUp');
 if(up){up.disabled=!j.parent;up.onclick=()=>j.parent&&fsList(j.parent);}
 const note=document.getElementById('fsNote');
 if(note)note.textContent=j.protected
  ?'Charta protects system folders — pick a folder inside your documents instead.'
  :(j.error||'');
}
function fsRow(iconName,label,go){
 const li=document.createElement('li');
 li.innerHTML='<span class="icon">'+icon(iconName,16)+'</span><span>'+escHtml(label)+'</span>';
 li.tabIndex=0;
 if(go){li.onclick=go;li.onkeydown=e=>{if(e.key==='Enter')go();};}else{li.className='muted';}
 return li;
}
window.openPicker=()=>{const p=document.getElementById('fsPicker');if(!p)return;p.hidden=false;
 const start=(document.getElementById('folder')||{}).value||folder()||'';
 fsList(start);const up=document.getElementById('fsUp');if(up)up.focus();};
window.closePicker=()=>{const p=document.getElementById('fsPicker');if(p)p.hidden=true;};
window.usePickedFolder=()=>{const use=document.getElementById('fsUse');
 if(!use||use.disabled)return;
 const field=document.getElementById('folder');if(field)field.value=PICKER.path;
 const chip=document.getElementById('fchip');if(chip)chip.textContent=PICKER.path;
 closePicker();};

// --- setup: staged progress, protected refusal, then start watching --------
window.createCharter=async()=>{
 const field=document.getElementById('folder');
 const dir=((field&&field.value)||folder()||'.').trim();
 const purpose=(document.getElementById('purpose')||{}).value||'';
 const dd=document.querySelector('.dd[data-name=mode]');
 const mode=dd?dd.dataset.value:'suggest';
 const out=document.getElementById('out');
 out.innerHTML='<div class="skel" style="height:64px">Understanding your purpose … drafting rules … scanning existing files</div>';
 try{
  const r=await fetch('/api/charter?folder='+encodeURIComponent(dir),{method:'POST',
   headers:{'Content-Type':'application/json'},body:JSON.stringify({purpose,mode})});
  const j=await r.json();
  if(r.status===403||j.error==='protected'){
   location.href='/protected?folder='+encodeURIComponent(dir)+'&reason='+encodeURIComponent(j.message||'');
   return;}
  const fields=(j.fields||[]).map(f=>'<span class="chip">'+f+'</span>').join(' ');
  const watching=j.watching!==false;
  out.innerHTML='<div class="card fadein"><div class="card-head"><h3>'+(watching?'Charter ready — watching':'Charter ready')
   +'</h3><span class="chip pill-auto">'+(j.mode==='auto'?'Auto mode':'Suggest mode')+'</span></div>'
   +'<p class="muted">Preset <span class="mono">'+j.preset+'</span> · fields: '+(fields||'—')+'</p>'
   +'<p class="mono muted">'+escHtml(j.purpose||'')+'</p>'
   +(watching
     ?'<p class="muted">Charta is watching this folder. Empty is fine — drop files in and they will be organised.</p>'
     :'<p class="muted">The charter is saved, but the watcher did not start. Press Watch this folder on the overview.</p>')
   +'<div class="row"><a class="btn btn-primary" href="/overview?folder='+encodeURIComponent(dir)+'">Open overview</a>'
   +'<a class="btn" href="/review?folder='+encodeURIComponent(dir)+'">Review proposals</a></div></div>';
 }catch(err){out.innerHTML='<div class="card">Could not create the charter. '+(err.message||'')+'</div>';}
};

// --- ask the folder --------------------------------------------------------
function renderAnswer(j){
 const log=document.getElementById('log');
 const cites=(j.citations||[]).map(c=>'<button class="chip cite mono" onclick="this.scrollIntoView()">'+escHtml(c.file)+' p'+c.page+'</button>').join(' ');
 const msg=document.createElement('div');
 msg.className='msg ai fadein';
 const meta=j.files?(' · '+j.files+' file(s)'+(j.cached?' (already read)':'')+' · '+escHtml(j.model||'')):'';
 const body=(j.answer||'').trim()||'No answer came back — the steps above say where it stopped.';
 msg.innerHTML='<div>'+escHtml(body)+'</div>'+(meta?'<p class="muted" style="margin:var(--s2) 0 0;font-size:var(--fs-label)">'+meta+'</p>':'')+cites;
 log.appendChild(msg);msg.scrollIntoView({block:'end'});
}
// The steps of a running job, shown as a timeline while it works.
function renderSteps(steps,state){
 const box=document.getElementById('steps');
 if(!box)return;
 const icons={work:'scan',model:'sparkles',tool:'search','tool-done':'check',done:'check',warn:'alert'};
 box.innerHTML='<div class="steps">'+steps.map((s,i)=>{
  const last=i===steps.length-1&&state==='running';
  const kind=s.kind==='tool'?'tool '+(last?'active':''):(s.kind==='tool-done'?'done':s.kind);
  return '<div class="step '+kind+'">'
   +'<span class="icon">'+icon(icons[s.kind]||'info',15)+'</span>'
   +'<span class="step-text">'+escHtml(s.text)+'</span></div>';
 }).join('')+'</div>';
}
async function watchJob(job,onDone){
 for(;;){
  let s;
  try{s=await api('/api/ask/status?job='+encodeURIComponent(job));}catch(e){return;}
  renderSteps(s.steps||[],s.state);
  if(s.state==='done'||s.state==='failed'){
   if(s.state==='failed'){toast(s.error||'Something went wrong.',false);}
   onDone(s);return;
  }
  await new Promise(r=>setTimeout(r,350));
 }
}
// --- keep the page in step with the server --------------------------------
// The backend can be updated while this window is open (a `git pull`, a
// restart). The page then runs yesterday's JavaScript against today's API,
// which looks like a mysterious failure. So: compare the build stamp, and
// offer a reload when they differ.
const CHARTA_BUILD=window.__CHARTA_BUILD__||'';
async function checkBuild(){
 if(!CHARTA_BUILD)return;
 let v;
 try{v=await api('/api/version');}catch(e){return;}
 if(v&&v.build&&v.build!==CHARTA_BUILD){
  const bar=document.getElementById('updateBar');
  if(bar&&!bar.dataset.shown){
   bar.dataset.shown='1';
   bar.hidden=false;
   bar.innerHTML='<span class="icon">'+icon('alert',15)+'</span> Charta was updated while this '
    +'window was open — reload to get the new version.'
    +'<button class="btn btn-primary" onclick="location.reload()">Reload</button>';
  }
 }
}
setInterval(checkBuild,15000);
window.addEventListener('load',()=>{checkBuild();});

window.askFolder=async(question)=>{
 const input=document.getElementById('q');
 const q=typeof question==='string'&&question?question:(input.value||'').trim();
 if(!q)return;
 if(input)input.value='';
 const log=document.getElementById('log');
 const mine=document.createElement('div');mine.className='msg me';mine.textContent=q;log.appendChild(mine);
 const steps=document.getElementById('steps');
 if(steps)steps.innerHTML='<div class="steps"><div class="step active"><span class="icon">'
  +icon('scan',15)+'</span><span class="step-text">starting…</span></div></div>';
 try{
  const j=await post('/api/ask?folder='+encodeURIComponent(folder()),{q});
  if(j.error){toast(j.message||'Could not answer that.',false);
   if(steps)steps.innerHTML='';return;}
  await watchJob(j.job,(done)=>{
   renderAnswer({answer:done.answer,citations:done.citations,files:done.files,
    cached:done.cached,model:done.model});
  });
 }catch(err){
  if(steps)steps.innerHTML='';
  const note=document.createElement('div');note.className='msg ai';
  note.textContent='Something went wrong: '+(err&&err.message?err.message:'unknown error');
  log.appendChild(note);
 }
};

// --- outputs grid (sortable, sticky header) ---------------------------------
const SORT={key:null,dir:1};
window.loadOutput=async(button,kind)=>{
 if(button){document.querySelectorAll('.tabbar button').forEach(b=>b.setAttribute('aria-selected',String(b===button)));}
 const grid=document.getElementById('outGrid');
 if(!grid)return;
 grid.innerHTML='<div class="skel" style="height:88px">loading outputs…</div>';
 const sort=(typeof kind==='string'&&kind)?kind:(grid.dataset.kind||'receipts');
 grid.dataset.kind=sort;
 let data;
 try{data=await api('/api/outputs/rows?folder='+encodeURIComponent(folder())+'&kind='+sort+'&t='+Date.now());}
 catch(err){grid.innerHTML='<div class="empty"><div class="glyph">'+icon('empty',28)+'</div><h3>No output yet</h3><p>Press Rebuild now.</p></div>';return;}
 if(data.error){grid.innerHTML='<div class="banner warn"><span class="icon">'+icon('alert',16)+'</span>'+escHtml(data.error)+'</div>';return;}
 if(!data.rows||!data.rows.length){
  grid.innerHTML='<div class="empty"><div class="glyph">'+icon('outputs',28)+'</div><h3>Nothing here yet</h3>'
   +'<p>No rows in <span class="mono">'+escHtml(sort)+'</span>. Approve a file or press Rebuild now.</p></div>';return;}
 const cols=data.columns||[];
 let rows=data.rows.slice();
 if(SORT.key!==null&&sort===grid.dataset.sortKind){const i=SORT.key;
  rows.sort((a,b)=>String(a[i]||'').localeCompare(String(b[i]||''),undefined,{numeric:true})*SORT.dir);}
 grid.dataset.sortKind=sort;
 grid.innerHTML='<div class="row" style="margin-bottom:var(--s2)"><span class="chip">'+rows.length+' rows</span>'
  +'<span class="muted caption">'+sort+'</span><span class="spacer"></span>'
  +'<span class="muted caption">click a header to sort</span></div>'
  +'<div style="max-height:420px;overflow:auto;border:1px solid var(--border);border-radius:var(--r-in)"><table class="grid"><thead><tr>'
  +cols.map((c,i)=>'<th scope="col"><button class="sort-btn" onclick="sortOutput('+i+')">'+escHtml(c)+' <span class="icon">'+icon('sort',13)+'</span></button></th>').join('')
  +'</tr></thead><tbody>'+rows.map(r=>'<tr>'+cols.map(c=>'<td>'+(r[cols.indexOf(c)]||'')+'</td>').join('')+'</tr>').join('')
  +'</tbody></table></div>';
};
window.sortOutput=(i)=>{SORT.dir=(SORT.key===i)?-SORT.dir:1;SORT.key=i;loadOutput(null);};

// --- review keyboard -------------------------------------------------------
let sel=0;
function paintSelection(cards){
 cards.forEach((c,i)=>c.classList.toggle('focus',i===sel));
 if(cards[sel])cards[sel].scrollIntoView({block:'center'});
}
document.addEventListener('keydown',e=>{
 const cards=[...document.querySelectorAll('.prop-card')];if(!cards.length)return;
 if(/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName))return;
 if(e.key==='j'||e.key==='J'){sel=Math.min(sel+1,cards.length-1);paintSelection(cards);}
 if(e.key==='k'||e.key==='K'){sel=Math.max(sel-1,0);paintSelection(cards);}
 if(e.key==='a'||e.key==='A'){const b=cards[sel]&&cards[sel].querySelector('.btn-primary');if(b)b.click();}
 if(e.key==='r'||e.key==='R'){const b=cards[sel]&&cards[sel].querySelectorAll('.btn')[1];if(b)b.click();}
});

// --- live updates ----------------------------------------------------------
try{const es=new EventSource('/api/events');es.onmessage=e=>{
 const el=document.getElementById('thinking');if(el)el.textContent=e.data;};}catch(_){}
document.addEventListener('visibilitychange',()=>{
 if(!document.hidden&&DESKTOP&&window.charta.notify)window.charta.notify('ready');});

// mic: Web Speech where available; the CLI/desktop uses local Whisper
window.toggleMic=(taId)=>{const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
const ta=document.getElementById(taId);if(!SR){toast('No browser speech engine here — local Whisper runs in the desktop/CLI.');return;}
const r=new SR();r.onresult=ev=>{ta.value+=(ta.value?' ':'')+ev.results[0][0].transcript;};r.start();
document.getElementById('micBtn')?.classList.add('rec');r.onend=()=>document.getElementById('micBtn')?.classList.remove('rec');};

initDropdowns();
window.loadOutput&&document.getElementById('outGrid')&&window.loadOutput(null);
})();
