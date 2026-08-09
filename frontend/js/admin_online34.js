(() => {
 const $=id=>document.getElementById(id);
 async function api(url){const r=await fetch(url,{credentials:'same-origin',cache:'no-store'}),d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||`Erreur ${r.status}`);return d}
 const duration=s=>{s=Number(s)||0;const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return d?`${d} j ${h} h`:h?`${h} h ${m} min`:`${m} min`};
 function render(d){
   const launch=d.launch||{},pub=d.public||{},db=d.database||{},storage=d.storage||{},ai=d.api||{},automod=d.automod||{};
   $('online34-score').textContent=`${launch.score||0}/100`;$('online34-ready').textContent=launch.ready?'Prêt à partager':'Corrections recommandées';
   $('online34-url').textContent=pub.url||'Non définie';$('online34-https').textContent=pub.https?'Actif ✓':'À activer';$('online34-server').textContent=`${d.server?.state||'online'} · PiChat ${d.version||''}`;
   $('online34-db').textContent=`${db.backend||'—'}${db.size_human?' · '+db.size_human:''}`;$('online34-storage').textContent=`${storage.backend||'—'}${storage.total_human?' · '+storage.total_human:''}`;
   $('online34-api').textContent=ai.configured?`${ai.provider||'OpenAI'} · configurée`:'Facultative';$('online34-automod').textContent=automod.enabled?'Actif':'Désactivé';$('online34-uptime').textContent=duration(d.uptime_seconds);
   $('online34-checks').innerHTML=(launch.checks||[]).map(c=>`<div class="online34-check ${c.ok?'ok':'bad'}"><span>${c.label}</span><b>${c.ok?'OK':'À corriger'}</b></div>`).join('')||'<p class="muted">Aucun diagnostic disponible.</p>';
 }
 async function load(){try{render(await api('/api/admin/pro'))}catch(e){const box=$('online34-checks');if(box)box.innerHTML=`<p class="error-message">${e.message}</p>`}}
 function bind(){$('online34-refresh')?.addEventListener('click',load);document.querySelector('[data-tab="online34"]')?.addEventListener('click',load);if(location.hash==='#online34')load()}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
})();
