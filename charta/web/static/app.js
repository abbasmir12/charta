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
// The same streamed flow as the Ask page, but the work block and the answer
// render inside this folder's own box.
window.askIn=async(f,id,q)=>{
 const box=document.getElementById(id);
 const input=document.getElementById(id+'-input');
 const question=(q||(input?input.value:'')).trim();
 if(!box||!question)return;
 if(input)input.value='';
 // Borrow the Ask page machinery by pointing its "log" at this box.
 const realLog=document.getElementById('log');
 if(realLog)realLog.id='log-off';
 box.id='log';
 try{
  await askOnce('','/api/ask?folder='+encodeURIComponent(f),question,f);
 }finally{
  box.id=id;
  if(realLog)realLog.id='log';
 }
 if(!box.querySelector('.msg.ai')){
  box.innerHTML='<div class="msg ai">No answer came back — open the Ask page for the full timeline.</div>';
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
// The model's answer arrives as Markdown. Render it locally (no CDN): escape
// everything first, then apply a small, known-safe set of patterns — plus
// Charta touches: [file pN] citations become buttons, dates and amounts are
// highlighted.
function mdInline(t){
 t=t.replace(/\[([^\[\]\n]+?)\s+p(\d+)\]/g,(m,f,p)=>
  '<button class="chip cite mono" onclick="revealCite(\''+encodeURIComponent(f)+'\',\''+p+'\')">'
  +escHtml(f)+' p'+p+'</button>');
 t=t.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
 t=t.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g,'$1<em>$2</em>');
 t=t.replace(/`([^`\n]+)`/g,'<code>$1</code>');
 t=t.replace(/\b(20\d{2}-\d{2}-\d{2})\b/g,'<span class="hl-date">$1</span>');
 t=t.replace(/(\d+([.,]\d+)?)\s?(EUR|USD|GBP|INR|€|\$|£|₹)\b/g,
  '<span class="hl-amount">$1 $3</span>');
 t=t.replace(/\b(https?:\/\/[^\s<)]+)/g,
  m=>'<a href="'+m+'" target="_blank" rel="noopener noreferrer">'+m+'</a>');
 return t;
}
function mdSplitRow(line){
 return line.trim().replace(/^\||\|$/g,'').split('|').map(c=>c.trim());
}
function md(text){
 text=(text||'').replace(/\r/g,'');
 const fences=[];
 text=text.replace(/```[\w+-]*\n?([\s\S]*?)```/g,(m,body)=>{
  fences.push(body);return '\x00F'+(fences.length-1)+'\x00';});
 const code=[];
 text=text.replace(/`([^`\n]+)`/g,(m,body)=>{code.push(body);return '\x00C'+(code.length-1)+'\x00';});
 text=escHtml(text);
 const lines=text.split('\n');const out=[];let inList=false;
 const flushList=()=>{if(inList){out.push('</ul>');inList=false;}};
 for(let i=0;i<lines.length;i++){
  const L=lines[i];
  if(/^\s*\|.*\|\s*$/.test(L)&&i+1<lines.length&&/^\s*\|[\s:|-]+\|\s*$/.test(lines[i+1])){
   flushList();
   const head=mdSplitRow(L);i+=2;const body=[];
   while(i<lines.length&&/^\s*\|.*\|\s*$/.test(lines[i])){body.push(mdSplitRow(lines[i]));i++;}
   i--;
   out.push('<div class="tblwrap"><table><thead><tr>'
    +head.map(h=>'<th>'+mdInline(h)+'</th>').join('')+'</tr></thead><tbody>'
    +body.map(r=>'<tr>'+r.map(c=>'<td>'+mdInline(c)+'</td>').join('')+'</tr>').join('')
    +'</tbody></table></div>');
   continue;
  }
  const h=L.match(/^\s*(#{1,6})\s*(.+)$/);
  if(h){flushList();
   // # and ## are big headline material; ### and deeper are section headers.
   // Every level gets its own visible style — a heading must never fall back
   // to looking like plain text with the hashes still in it.
   const lv=h[1].length<=2?3:h[1].length===3?4:5;
   out.push('<h'+lv+'>'+mdInline(h[2].replace(/\*+/g,''))+'</h'+lv+'>');continue;}
  // Models often write "headings" as a fully bolded line; give them that.
  const boldLine=L.match(/^\s*\*\*([^*]+)\*\*\s*$/);
  if(boldLine){flushList();out.push('<h4>'+mdInline(boldLine[1])+'</h4>');continue;}
  if(/^\s*[-*]\s+/.test(L)){if(!inList){out.push('<ul>');inList=true;}out.push('<li>'+mdInline(L.replace(/^\s*[-*]\s+/,''))+'</li>');continue;}
  if(/^\s*\d+\.\s+/.test(L)){if(!inList){out.push('<ul>');inList=true;}out.push('<li>'+mdInline(L.replace(/^\s*\d+\.\s+/,''))+'</li>');continue;}
  flushList();
  if(!L.trim()){continue;}
  out.push('<p>'+mdInline(L)+'</p>');
 }
 flushList();
 let html=out.join('\n');
 // Restore code after escaping: the fence content was captured pre-escape.
 html=html.replace(/\x00C(\d+)\x00/g,(m,i)=>'<code>'+code[+i]+'</code>');
 html=html.replace(/\x00F(\d+)\x00/g,(m,i)=>'<pre class="mono">'+fences[+i]+'</pre>');
 return html;
}
window.revealCite=(b64,p)=>{
 const name=decodeURIComponent(b64);
 toast('Opening '+name);
 const f=(askOnce.f!==undefined&&askOnce.f)?askOnce.f:folder();
 if(window.revealFile&&f)revealFile(f,name);
};
// The model's work, shown as it happens: a collapsible block inside the chat
// where every tool call appears the moment the model makes it (streamed),
// then collapses into a one-line summary above the answer.
function makeWork(){
 const log=document.getElementById('log');
 const el=document.createElement('div');el.className='work open fadein';
 el.innerHTML='<button type="button" class="work-head" onclick="toggleWork(this)">'
  +'<span class="w-ico w-run">'+icon('scan',15)+'</span>'
  +'<span class="work-title">thinking…</span>'
  +'<span class="spacer"></span><span class="w-n"></span><span class="w-chev">'+icon('arrow-right',13)+'</span></button>'
  +'<div class="work-body"></div>';
 log.appendChild(el);
 const body=el.querySelector('.work-body');
 const title=el.querySelector('.work-title');
 const counter=el.querySelector('.w-n');
 const icons={work:'info',model:'sparkles',tool:'search','tool-done':'check',
              done:'check',warn:'alert'};
 let done=false;
 const add=(kind,text)=>{
  if(kind!=='tool-done'&&kind!=='done'){
   const lastRow=body.querySelector('.work-row.live');
   if(lastRow)lastRow.classList.replace('live','dim');
  }
  const raw=text.split('\n')[0].trim();
  const row=document.createElement('div');
  row.className='work-row '+(kind==='tool'?'live':kind==='tool-done'?'done':kind);
  row.innerHTML='<span class="icon">'+icon(icons[kind]||'info',14)+'</span>'
   +'<span class="mono">'+escHtml(raw)+'</span>';
  if(kind==='tool')row.classList.add('live');
  if(kind==='tool-done'||kind==='done')row.classList.add('done');
  body.appendChild(row);
  title.textContent=raw;
  counter.textContent=body.children.length;
 };
 const finish=(state)=>{
  done=true;
  const n=body.children.length;
  const ico=el.querySelector('.w-ico');
  if(state==='failed'){
   ico.innerHTML=icon('alert',15);title.textContent='stopped';
  }else{
   ico.innerHTML=icon('check',15);
   title.textContent=n>0?('read the index · '+n+' step'+(n===1?'':'s')+' of work'):'answered';
  }
  counter.textContent='';
  el.classList.remove('open');
 };
 return {el,add,finish};
}
window.toggleWork=btn=>{
 const block=btn.closest('.work');
 block.classList.toggle('open');
};
// The stream: each step is pushed by the server the moment it happens.
function streamJob(job,work){
 return new Promise(resolve=>{
  let es;
  try{es=new EventSource('/api/ask/stream?job='+encodeURIComponent(job));}
  catch(e){resolve(null);return;}
  es.addEventListener('step',e=>{try{const s=JSON.parse(e.data);work.add(s.kind,s.text);}catch(err){}});
  es.addEventListener('done',e=>{es.close();try{resolve(JSON.parse(e.data));}catch(err){resolve(null);}});
  es.onerror=()=>{es.close();resolve(null);};
 });
}
// Fallback when SSE is unavailable: poll, feeding the same work block.
async function watchJob(job,work){
 for(;;){
  let s;
  try{s=await api('/api/ask/status?job='+encodeURIComponent(job));}catch(e){break;}
  (s.steps||[]).forEach(step=>work.add(step.kind,step.text));
  work.el.classList.remove('open');
  if(s.state==='done'||s.state==='failed'){work.finish(s.state);return s;}
 }
 return null;
}
function renderAnswer(j){
 const log=document.getElementById('log');
 const cites=(j.citations||[]).map(c=>'<button class="chip cite mono" '
  +'onclick="revealCite(\''+encodeURIComponent(c.file)+'\',\''+c.page+'\')">'
  +escHtml(c.file)+' p'+c.page+'</button>').join(' ');
 const msg=document.createElement('div');
 msg.className='msg ai fadein rich';
 const meta=j.files?(' · '+j.files+' file(s)'+(j.cached?' (already read)':'')+' · '+escHtml(j.model||'')):'';
 const body=(j.answer||'').trim();
 msg.innerHTML=(body?md(body):'<p>No answer came back — expand the work above to see where it stopped.</p>')
  +(meta?'<p class="muted" style="margin:var(--s2) 0 0;font-size:var(--fs-label)">'+meta+'</p>':'')
  +(cites?'<div class="row" style="margin-top:var(--s2)">'+cites+'</div>':'');
 log.appendChild(msg);msg.scrollIntoView({block:'end',behavior:'smooth'});
}
function showFailure(done){
 const log=document.getElementById('log');
 const bad=document.createElement('div');bad.className='msg ai fadein';
 bad.innerHTML='<div><strong>I stopped:</strong> '+escHtml(done.error||'unknown reason')+'</div>'
  +(done.steps&&done.steps.length
    ?'<p class="muted" style="margin:var(--s2) 0 0;font-size:var(--fs-label)">Last step: '
     +escHtml(done.steps[done.steps.length-1].text)+'</p>':'');
 log.appendChild(bad);bad.scrollIntoView({block:'end'});
}
// One shared question flow for the Ask page and the per-folder ask boxes:
// post the job, stream the work into an inline block, then render the answer.
async function askOnce(boxEl,endpoint,q,folderOverride){
 askOnce.f=folderOverride;
 const work=makeWork();
 let j;
 try{j=await post(endpoint,{q});}
 catch(err){
  const log=document.getElementById(boxEl?boxEl:'log');
  const bad=document.createElement('div');bad.className='msg ai';
  bad.textContent='Something went wrong: '+(err&&err.message?err.message:'unknown error');
  log.appendChild(bad);return;
 }
 if(j.error){
  work.finish('failed');
  const log=document.getElementById('log');
  const bad=document.createElement('div');bad.className='msg ai';
  bad.innerHTML='<div>'+escHtml(j.message||'Could not answer that.')+'</div>';
  log.appendChild(bad);return;
 }
 let done=await streamJob(j.job,work);
 if(!done)done=await watchJob(j.job,work);
 window.__lastAsk=done;
 work.finish(done?done.state:'failed');
 if(!done)return;
 if(done.state==='failed'){showFailure(done);return;}
 renderAnswer(done);
}
window.askFolder=async(question)=>{
 const input=document.getElementById('q');
 const q=typeof question==='string'&&question?question:(input.value||'').trim();
 if(!q)return;
 if(input)input.value='';
 const log=document.getElementById('log');
 const mine=document.createElement('div');mine.className='msg me';mine.textContent=q;log.appendChild(mine);
 await askOnce('log','/api/ask?folder='+encodeURIComponent(folder()),q,folder());
};
// --- keep the page in step with the server --------------------------------
// The backend can be updated while this window is open (a `git pull`, a
// restart). The page then runs yesterday's JavaScript against today's API,
// which looks like a mysterious failure. So: compare the build stamp — the
// footer under the answer says which revision is serving this page.
const CHARTA_BUILD=window.__CHARTA_BUILD__||'';
async function checkBuild(){
 if(!CHARTA_BUILD)return;
 let v;
 try{v=await api('/api/version');}catch(e){return;}
 if(v&&v.build&&v.build!==CHARTA_BUILD&&!checkBuild.warned){
  checkBuild.warned=true;
  toast('Charta was updated — reload the window for the new version.',false);
  const foot=document.querySelector('.askbuild');
  if(foot)foot.innerHTML='<button class="chip" onclick="location.reload()">Reload — new version running</button>';
 }
}
setInterval(checkBuild,30000);
window.addEventListener('load',()=>{checkBuild();});

// One click that collects everything needed to diagnose a broken answer.
window.copyDiag=async()=>{
 const out={page_build:CHARTA_BUILD,url:location.href,ask:window.__lastAsk||null};
 try{out.server=await api('/api/version');}catch(e){out.server=String(e);}
 await navigator.clipboard.writeText(JSON.stringify(out,null,2));
 toast('Diagnostics copied — paste them back.',true);
};


// --- outputs: one card per output kind, each telling its own story ----------
window.outToggle=btn=>{
 const html=btn.innerHTML;
 const body=btn.closest('.card').querySelector('.outpreview');
 const hide=html.includes('Hide preview');
 body.style.display=hide?'none':'';
 btn.innerHTML=hide
  ?'<span class="icon">'+icon('empty',16)+'</span> Show preview'
  :'<span class="icon">'+icon('empty',16)+'</span> Hide preview';
};
window.outShow=async btn=>{
 const card=btn.closest('.card');
 const folder=card.dataset.folder;
 const data=card.dataset.file||'';
 if(!data){toast('This output has no file yet — press Rebuild.',false);return;}
 const rel='.charta/outputs/'+data;
 try{await post('/api/file/open?folder='+encodeURIComponent(folder),{path:rel});
  toast('Opened '+data);}
 catch(err){toast('Could not open the file.',false);}
};
window.outRebuild=async btn=>{
 const card=btn.closest('.card');
 await loadCard(card,true);
};
async function loadCard(card,rebuild){
 const folder=card.dataset.folder;
 const kind=card.dataset.kind;
 const box=card.querySelector('.outpreview');
 const meta=card.querySelector('.outmeta');
 const state=card.querySelector('.outstate');
 box.innerHTML='<div class="skel" style="height:64px">reading the folder…</div>';
 meta.textContent='';state.textContent='building…';
 let d;
 try{d=await api('/api/outputs/rows?folder='+encodeURIComponent(folder)
  +'&kind='+kind+(rebuild?'&refresh=1':'')+'&t='+Date.now());}
 catch(err){box.innerHTML='<div class="empty">Could not build this. '+(err&&err.message||'')+'</div>';return;}
 if(d.error){
  box.innerHTML='<div class="banner warn"><span class="icon">'+icon('alert',16)+'</span>'+escHtml(d.error)+'</div>';
  state.textContent='failed';meta.textContent='';return;
 }
 card.dataset.file=d.file||'';
 const n=d.total||0;
 state.textContent=n?n+(n===1?' item':' items'):'nothing yet';
 state.className='chip outstate '+(n?'pill-auto':'');
 const how=d.file?('.charta/outputs/'+escHtml(d.file)+(d.xlsx?' + '+escHtml(d.xlsx):'')
  +(' · built '+escHtml(d.modified||''))):'';
 meta.innerHTML=how;
 const cols=d.columns||[];
 if(!n){
  box.innerHTML='<div class="empty"><div class="glyph">'+icon('empty',24)+'</div>'
   +'<h3>Nothing to show</h3><p>Rebuild after this folder has files with text '
   +'(txt, md, csv, pdf).</p></div>';
  return;
 }
 if(kind==='study'){
  box.innerHTML='<div class="outtext mono">'+escHtml(String(d.rows[0][0]).slice(0,3000))+'</div>';
  return;
 }
 box.innerHTML='<div style="max-height:260px;overflow:auto"><table class="grid"><thead><tr>'
 box.innerHTML='<div style="max-height:260px;overflow:auto"><table class="grid"><thead><tr>'
  +cols.map(c=>'<th scope="col">'+escHtml(c)+'</th>').join('')
  +'</tr></thead><tbody>'
  +d.rows.map(r=>'<tr>'+cols.map((c,i)=>'<td>'+escHtml(r[i]||'')+'</td>').join('')+'</tr>').join('')
  +'</tbody></table></div>';
}
window.loadOutput=async()=>{
 const cards=[...document.querySelectorAll('.outcard')];
 await Promise.all(cards.map(c=>loadCard(c,false)));
};

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
window.loadOutput&&document.querySelector('.outcard')&&window.loadOutput();
})();
