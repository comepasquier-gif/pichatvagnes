(()=>{
  const $=id=>document.getElementById(id);
  const api=async(url,options={})=>{const r=await fetch(url,{credentials:'same-origin',...options});let data={};try{data=await r.json()}catch{}if(!r.ok)throw new Error(data.detail||`Erreur HTTP ${r.status}`);return data};
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let state=null;
  function switchTab(name){document.querySelector(`.nav-item[data-tab="${name}"]`)?.click()}
  function scoreClass(score){return score>=90?'excellent':score>=75?'good':score>=55?'medium':'bad'}
  function render(data){
    state=data;
    const score=$('launch31-score'); if(score){score.textContent=`${data.score}/100`;score.className=`launch31-score ${scoreClass(data.score)}`}
    const badge=$('launch31-ready'); if(badge){badge.textContent=data.ready?'PRÊT POUR LE LANCEMENT':'À VÉRIFIER';badge.className=`launch31-ready ${data.ready?'ready':'not-ready'}`}
    const url=$('launch31-url'); if(url){url.textContent=data.cloud.public_url||'Aucune URL publique';url.href=data.cloud.public_url||'#';url.classList.toggle('disabled',!data.cloud.public_url)}
    const checks=$('launch31-checks'); if(checks)checks.innerHTML=(data.checks||[]).map(x=>`<article class="launch31-check ${x.ok?'ok':'ko'}"><span>${x.ok?'✓':'!'}</span><div><strong>${esc(x.label)}</strong><small>${x.critical?'Contrôle important':'Contrôle recommandé'}</small></div></article>`).join('')||'<p class="muted">Aucun contrôle disponible.</p>';
    const mods=$('launch31-modules'); if(mods)mods.innerHTML=(data.modules||[]).map(x=>`<article class="launch31-module ${x.enabled?'on':'off'}"><span>${esc(x.icon)}</span><div><strong>${esc(x.label)}</strong><small>${x.enabled?'Actif':'Inactif'}</small></div></article>`).join('');
    const rec=$('launch31-recommendations'); if(rec)rec.innerHTML=(data.recommendations||[]).map(x=>`<article class="launch31-rec ${esc(x.level)}"><strong>${esc(x.title)}</strong><p>${esc(x.text)}</p></article>`).join('');
    const stats=$('launch31-stats'); if(stats){const s=data.stats||{};stats.innerHTML=`<div><span>Comptes</span><strong>${s.users??0}</strong></div><div><span>Messages</span><strong>${s.messages??0}</strong></div><div><span>Sessions</span><strong>${s.sessions??0}</strong></div><div><span>Jeux Studio</span><strong>${s.games??0}</strong></div>`}
    const apiState=$('launch31-api-state'); if(apiState)apiState.innerHTML=`<strong>${data.api.configured?'Configurée':'Non configurée'}</strong><small>${data.api.configured?`Modèle : ${esc(data.api.model||'—')} · Test : ${esc(data.api.last_test_status)}`:'PiAI local reste disponible sans clé.'}</small>`;
    const cloudState=$('launch31-cloud-state'); if(cloudState){const rail=data.railway?.railway_mode;cloudState.innerHTML=`<strong>${data.cloud.running?'En ligne':'Hors ligne'}</strong><small>${data.cloud.running?esc(data.cloud.public_url):rail?'Railway sans domaine public':'Railway recommandé · Cloudflare facultatif'}</small>`;}
    const labState=$('launch31-lab-state'); if(labState)labState.innerHTML=`<strong>${data.lab.test_accounts} compte(s) de test</strong><small>${data.lab.active_batches} lot(s) actif(s)</small>`;
  }
  async function load(){const target=$('launch31-refresh');if(target)target.disabled=true;try{render(await api('/api/admin/launch31'))}catch(e){$('launch31-error').textContent=e.message;$('launch31-error').hidden=false}finally{if(target)target.disabled=false}}
  async function prepare(){const btn=$('launch31-prepare');if(btn){btn.disabled=true;btn.textContent='Préparation…'}try{const data=await api('/api/admin/launch31/prepare',{method:'POST'});render(data);$('launch31-action-state').textContent=`✓ Backup ${data.backup_created} créé · contrôle terminé.`}catch(e){$('launch31-action-state').textContent=`Erreur : ${e.message}`}finally{if(btn){btn.disabled=false;btn.textContent='🛡 Backup + préflight'}}}
  async function quickCloud(){const btn=$('launch31-cloud-quick');btn.disabled=true;try{let c=await api('/api/admin/cloud');if(!c.installed){$('launch31-action-state').textContent='Installation de cloudflared…';await api('/api/admin/cloud/install',{method:'POST'})}const result=await api('/api/admin/cloud/quick/start',{method:'POST'});$('launch31-action-state').textContent=`✓ HTTPS actif : ${result.public_url||''}`;await load()}catch(e){$('launch31-action-state').textContent=`Cloud : ${e.message}`}finally{btn.disabled=false}}
  function copyUrl(){const url=state?.cloud?.public_url;if(!url)return;navigator.clipboard?.writeText(url).then(()=>{$('launch31-action-state').textContent='Adresse copiée ✓'}).catch(()=>{})}
  function bind(){
    $('launch31-refresh')?.addEventListener('click',load);
    $('launch31-prepare')?.addEventListener('click',prepare);
    $('launch31-cloud-quick')?.addEventListener('click',quickCloud);
    $('launch31-copy-url')?.addEventListener('click',copyUrl);
    document.querySelectorAll('[data-launch31-tab]').forEach(btn=>btn.addEventListener('click',()=>switchTab(btn.dataset.launch31Tab)));
    document.querySelector('.nav-item[data-tab="launch31"]')?.addEventListener('click',load);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
})();
