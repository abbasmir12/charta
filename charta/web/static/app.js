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
window.scanFolder=async(f)=>{await post('/api/scan?folder='+encodeURIComponent(f));location.reload();};
window.watchFolder=async(f)=>{await post('/api/watch?folder='+encodeURIComponent(f));location.reload();};
window.unwatchFolder=async(f)=>{await post('/api/unwatch?folder='+encodeURIComponent(f));location.reload();};
// Ask a question about one specific folder from the Folders page.
window.askIn=async(f,id,q)=>{
 const box=document.getElementById(id);
 const input=document.getElementById(id+'-input');
 const question=(q||(input?input.value:'')).trim();
 if(!box||!question)return;
 if(input)input.value='';
 box.innerHTML='<div class="msg ai skel" style="min-width:200px">searching…</div>';
 try{
  const j=await post('/api/ask?folder='+encodeURIComponent(f),{q:question});
  const cites=(j.citations||[]).map(c=>'<span class="chip cite mono">'+escHtml(c.file)+' p'+c.page+'</span>').join(' ');
  box.innerHTML='<div class="msg ai"><div>'+escHtml(j.answer||'No answer.')+'</div>'+cites+'</div>';
 }catch(err){box.innerHTML='<div class="msg ai">Could not answer that right now.</div>';}
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
  try{await fetch('/api/watch?folder='+encodeURIComponent(dir),{method:'POST'});}catch(_){}
  const fields=(j.fields||[]).map(f=>'<span class="chip">'+f+'</span>').join(' ');
  out.innerHTML='<div class="card fadein"><div class="card-head"><h3>Charter ready — watching</h3>'
   +'<span class="chip pill-auto">'+(j.mode==='auto'?'Auto mode':'Suggest mode')+'</span></div>'
   +'<p class="muted">Preset <span class="mono">'+j.preset+'</span> · fields: '+(fields||'—')+'</p>'
   +'<p class="mono muted">'+j.purpose+'</p>'
   +'<p class="muted">Charta is scanning existing files now — open the overview to watch it fill in.</p>'
   +'<div class="row"><a class="btn btn-primary" href="/overview?folder='+encodeURIComponent(dir)+'">Open overview</a>'
   +'<a class="btn" href="/review?folder='+encodeURIComponent(dir)+'">Review proposals</a></div></div>';
 }catch(err){out.innerHTML='<div class="card">Could not create the charter. '+(err.message||'')+'</div>';}
};

// --- ask the folder --------------------------------------------------------
function renderAnswer(j){
 const log=document.getElementById('log');
 const cites=(j.citations||[]).map(c=>'<button class="chip cite mono" onclick="this.scrollIntoView()">'+c.file+' p'+c.page+'</button>').join(' ');
 const msg=document.createElement('div');
 msg.className='msg ai fadein';
 msg.innerHTML='<div>'+(j.answer||'No answer.')+'</div>'+cites;
 log.appendChild(msg);msg.scrollIntoView({block:'end'});
}
window.askFolder=async(question)=>{
 const input=document.getElementById('q');
 const q=typeof question==='string'&&question?question:(input.value||'').trim();
 if(!q)return;
 if(input)input.value='';
 const log=document.getElementById('log');
 const mine=document.createElement('div');mine.className='msg me';mine.textContent=q;log.appendChild(mine);
 const pending=document.createElement('div');pending.className='msg ai skel';pending.style.minWidth='220px';pending.textContent='searching…';
 log.appendChild(pending);pending.scrollIntoView({block:'end'});
 try{const j=await post('/api/ask?folder='+encodeURIComponent(folder()),{q});pending.remove();renderAnswer(j);}
 catch(err){pending.remove();}
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
