(()=>{
const $=id=>document.getElementById(id);const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api=async(url,options={})=>{const r=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||`Erreur ${r.status}`);return d};
const duration=s=>{s=Math.max(0,Number(s)||0);const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return d?`${d} j ${h} h`:h?`${h} h ${m} min`:`${m} min`};
function toast(text,bad=false){const el=$('pro-state');if(!el)return;el.textContent=text;el.classList.toggle('pro-error',!!bad);setTimeout(()=>{if(el.textContent===text)el.textContent=''},4500)}
function set(id,value){const el=$(id);if(el)el.textContent=value}
function render(d){const stats=d.stats||{},db=d.database||{},st=d.storage||{},b=d.backup||{},ai=d.api||{},pub=d.public||{},auto=d.automod||{},launch=d.launch||{};
 set('pro-version',`PiChat ${d.version} · ${d.edition||'FREE ONLINE'}`);set('pro-score',`${launch.score||0}/100`);set('pro-ready-label',launch.ready?'Prêt pour la mise en ligne':'Vérifications restantes');set('pro-uptime',duration(d.uptime_seconds));
 set('pro-online',stats.online_users||0);set('pro-users',stats.users||0);set('pro-messages',stats.messages_today||0);set('pro-mps',Number(stats.messages_per_second||0).toFixed(3));set('pro-rooms',stats.rooms||0);set('pro-disk',`${st.backend||'—'} · ${st.uploads_human||'0 o'}`);set('pro-server',d.server?.state==='online'?'En ligne':'À vérifier');
 set('pro-db',`${db.backend||'—'} · ${db.size_human||'0 o'}`);set('pro-uploads',`${st.objects||0} fichier(s) · ${st.uploads_human||'0 o'}`);set('pro-backups',`${b.count||0} · ${b.size_human||'0 o'}`);set('pro-backup-latest',b.latest?`${b.latest}${b.age_hours!=null?' · '+b.age_hours+' h':''}`:'Aucun backup');
 const cloud=$('pro-cloud');if(cloud)cloud.innerHTML=pub.https?`<span class="pro-dot ok"></span>${esc(pub.url||'HTTPS actif')}`:`<span class="pro-dot"></span>${esc(pub.url||'URL non définie')}`;
 const ap=$('pro-api');if(ap)ap.innerHTML=ai.configured?`<span class="pro-dot ${ai.last_test_status==='ok'?'ok':'warn'}"></span>${esc(ai.model||ai.provider||'API')}`:`<span class="pro-dot"></span>Non configurée (facultatif)`;
 const checks=$('pro-checks');if(checks)checks.innerHTML=(launch.checks||[]).map(c=>`<div class="pro-check ${c.ok?'ok':'missing'}"><span>${c.ok?'✓':'!'}</span><div><strong>${esc(c.label)}</strong><small>${c.ok?'OK':'À corriger'}</small></div><b>${c.weight}</b></div>`).join('');
 const health=$('pro-health');if(health)health.innerHTML=[['Base '+(db.backend||''),db.ok,db.status||db.detail],['HTTPS public',pub.https,pub.url||'Non défini'],['API IA',!!ai.configured,ai.configured?(ai.last_test_status||'configurée'):'Facultative'],['AutoModo',auto.ok,auto.enabled?'Actif':'Désactivé'],['Stockage persistant',['database','s3'].includes(st.backend),st.backend||'—']].map(([l,ok,x])=>`<div class="pro-health-row"><span class="pro-dot ${ok?'ok':''}"></span><div><strong>${esc(l)}</strong><small>${esc(x)}</small></div></div>`).join('');
 set('pro-system',`${d.platform||''} · Python ${d.python||''}`);
}
async function load(){try{render(await api('/api/admin/pro'))}catch(e){toast(e.message,true)}}
async function backup(){const el=$('pro-backup-now');if(el)el.disabled=true;try{const d=await api('/api/admin/pro/backup',{method:'POST'});render(d.overview);toast(`Backup créé : ${d.name}`)}catch(e){toast(e.message,true)}finally{if(el)el.disabled=false}}
async function bundle(){const el=$('pro-bundle');if(el)el.disabled=true;try{const d=await api('/api/admin/pro/support-bundle',{method:'POST'});toast('Diagnostic créé');location.href=d.download_url}catch(e){toast(e.message,true)}finally{if(el)el.disabled=false}}
function bind(){$('pro-refresh')?.addEventListener('click',load);$('pro-backup-now')?.addEventListener('click',backup);$('pro-bundle')?.addEventListener('click',bundle);document.querySelector('[data-tab="pro"]')?.addEventListener('click',load);if(location.hash==='#pro')load()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
})();
