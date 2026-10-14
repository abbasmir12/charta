// theme + palette + SSE + keyboard (J/K/A/R/E/Z) + review actions
// + native-feel guards, custom dropdowns, custom folder picker.
(function(){
const root=document.documentElement;
const saved=localStorage.getItem('charta-theme');
if(saved)root.dataset.theme=saved;
else if(matchMedia('(prefers-color-scheme: light)').matches)root.dataset.theme='light';
window.toggleTheme=()=>{root.dataset.theme=root.dataset.theme==='light'?'dark':'light';
localStorage.setItem('charta-theme',root.dataset.theme||'dark');};

// --- native-feel: take the browser's own chrome shortcuts away --------------
// Charta ships as a window, not a web page. Re-enable everything with --debug.
const DEBUG=!!window.__CHARTA_DEBUG__;
if(!DEBUG){
 document.addEventListener('contextmenu',e=>e.preventDefault());
 document.addEventListener('keydown',e=>{
  const k=(e.key||'').toLowerCase(),mod=e.ctrlKey||e.metaKey;
  const blocked=e.key==='F5'||e.key==='F12'
   ||(mod&&!e.shiftKey&&['r','f','p'].includes(k))          // reload / find / print
   ||(mod&&e.shiftKey&&['i','j','c'].includes(k));           // devtools, console, inspect
  if(blocked){e.preventDefault();e.stopPropagation();}
 },true);
}

document.addEventListener('keydown',e=>{
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openPalette();}
 if(e.key==='/'&&document.activeElement.tagName!=='TEXTAREA'&&document.activeElement.tagName!=='INPUT'){e.preventDefault();openPalette();}
 if(e.key==='Escape'){closePalette();closePicker();}
});
window.openPalette=()=>{document.getElementById('palette').style.display='flex';
document.getElementById('palInput').focus();};
window.closePalette=()=>{const p=document.getElementById('palette');if(p)p.style.display='none';};
window.palFilter=(q)=>{document.querySelectorAll('#palList button').forEach(b=>{
b.style.display=b.textContent.toLowerCase().includes(q.toLowerCase())?'':'none';});};
window.toast=(msg,undo)=>{const t=document.createElement('div');t.className='toast';t.setAttribute('role','status');
t.innerHTML=msg+(undo?` <button class="btn" onclick="undoLast()">Undo</button>`:'');document.body.appendChild(t);
setTimeout(()=>t.remove(),8000);};
window.undoLast=async()=>{const f=folder();await fetch('/api/undo?folder='+encodeURIComponent(f),{method:'POST'});location.reload();};
window.folder=()=>new URLSearchParams(location.search).get('folder')||'';
async function api(p,o){const r=await fetch(p,o);if(!r.ok)throw new Error(await r.text());return r.json();}
window.approveOne=async(src)=>{await api('/api/approve?folder='+encodeURIComponent(folder()),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files:[src]})});toast('Approved '+src,true);};
window.rejectOne=async(src)=>{await api('/api/reject?folder='+encodeURIComponent(folder()),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files:[src]})});location.reload();};

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
 catch(err){document.getElementById('fsNote').textContent='Could not read that folder.';return;}
 PICKER.path=j.path;
 document.getElementById('fsPath').textContent=j.path;
 const ul=document.getElementById('fsList');ul.innerHTML='';
 (j.roots||[]).filter(d=>d!==j.path).forEach(d=>ul.appendChild(fsRow('💽 '+d,()=>fsList(d))));
 (j.dirs||[]).forEach(name=>ul.appendChild(fsRow('📁 '+name,()=>fsList(joinPath(j.path,name)))));
 if(!j.dirs.length)ul.appendChild(fsRow('(no subfolders)',null));
 const use=document.getElementById('fsUse');
 use.disabled=!!j.protected;
 document.getElementById('fsUp').disabled=!j.parent;
 document.getElementById('fsUp').onclick=()=>j.parent&&fsList(j.parent);
 document.getElementById('fsNote').textContent=j.protected
  ?'Charta protects system folders — pick a folder inside your documents instead.'
  :(j.error||'');
}
function fsRow(label,go){
 const li=document.createElement('li');li.textContent=label;li.tabIndex=0;
 if(go){li.onclick=go;li.onkeydown=e=>{if(e.key==='Enter')go();};}else{li.className='muted';}
 return li;
}
window.openPicker=()=>{document.getElementById('fsPicker').hidden=false;
 const start=document.getElementById('folder').value||folder()||'';
 fsList(start);document.getElementById('fsUp').focus();};
window.closePicker=()=>{const p=document.getElementById('fsPicker');if(p)p.hidden=true;};
window.usePickedFolder=()=>{const use=document.getElementById('fsUse');
 if(!use||use.disabled)return;
 document.getElementById('folder').value=PICKER.path;
 const c=document.getElementById('fchip');if(c)c.textContent=PICKER.path;
 closePicker();};

// --- setup: staged progress, protected refusal, then start watching --------
window.createCharter=async()=>{
 const field=document.getElementById('folder');
 const dir=((field&&field.value)||folder()||'.').trim();
 const purpose=document.getElementById('purpose').value;
 const dd=document.querySelector('.dd[data-name=mode]');
 const mode=dd?dd.dataset.value:'suggest';
 const out=document.getElementById('out');
 const stages=['Understanding your purpose','Drafting rules','Scanning existing files'];
 out.innerHTML='<div class="skel">'+stages.join(' … ')+'</div>';
 try{
  const r=await fetch('/api/charter?folder='+encodeURIComponent(dir),{method:'POST',
   headers:{'Content-Type':'application/json'},body:JSON.stringify({purpose,mode})});
  const j=await r.json();
  if(r.status===403||j.error==='protected'){
   location.href='/protected?folder='+encodeURIComponent(dir)+'&reason='+encodeURIComponent(j.message||'');
   return;}
  out.innerHTML='<div class="card"><h3>Charter ready</h3><p class="mono">mode: '+j.mode+'</p>'
   +'<pre class="mono">'+JSON.stringify(j,null,2)+'</pre>'
   +'<a class="btn btn-primary" href="/overview?folder='+encodeURIComponent(dir)+'">Start watching →</a></div>';
 }catch(err){out.innerHTML='<div class="card">Could not create the charter. '+(err.message||'')+'</div>';}
};

// review keyboard
let sel=0;
document.addEventListener('keydown',e=>{
 const cards=[...document.querySelectorAll('.prop-card')];if(!cards.length)return;
 if(e.key==='j'||e.key==='J'){sel=Math.min(sel+1,cards.length-1);cards[sel].scrollIntoView({block:'center'});}
 if(e.key==='k'||e.key==='K'){sel=Math.max(sel-1,0);cards[sel].scrollIntoView({block:'center'});}
});
// SSE live
try{const es=new EventSource('/api/events');es.onmessage=e=>{const el=document.getElementById('thinking');
if(el)el.textContent=e.data;};}catch(_){}
// mic (Web Speech API if present, else file upload hint)
window.toggleMic=(taId)=>{const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
const ta=document.getElementById(taId);if(!SR){toast('No browser STT here — local Whisper runs in desktop/CLI.');return;}
const r=new SR();r.onresult=ev=>{ta.value+=(ta.value?' ':'')+ev.results[0][0].transcript;};r.start();
document.getElementById('micBtn')?.classList.add('rec');r.onend=()=>document.getElementById('micBtn')?.classList.remove('rec');};
initDropdowns();
})();
