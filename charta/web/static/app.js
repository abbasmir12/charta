// theme + palette + SSE + keyboard (J/K/A/R/E/Z) + review actions
(function(){
const root=document.documentElement;
const saved=localStorage.getItem('charta-theme');
if(saved)root.dataset.theme=saved;
else if(matchMedia('(prefers-color-scheme: light)').matches)root.dataset.theme='light';
window.toggleTheme=()=>{root.dataset.theme=root.dataset.theme==='light'?'dark':'light';
localStorage.setItem('charta-theme',root.dataset.theme||'dark');};
document.addEventListener('keydown',e=>{
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openPalette();}
 if(e.key==='/'&&document.activeElement.tagName!=='TEXTAREA'&&document.activeElement.tagName!=='INPUT'){e.preventDefault();openPalette();}
});
window.openPalette=()=>{document.getElementById('palette').style.display='flex';
document.getElementById('palInput').focus();};
window.closePalette=()=>{document.getElementById('palette').style.display='none';};
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
})();
