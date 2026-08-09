(()=>{
  'use strict';
  const $=id=>document.getElementById(id);
  let state={batches:[],diagnostics:null};
  let lastCredentials=[];
  let lastPassword='';
  const api=async(url,opt={})=>{const r=await fetch(url,{credentials:'same-origin',cache:'no-store',...opt});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||`Erreur ${r.status}`);return d};
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function notice(text,ok=false){const el=$('test-lab-notice');if(!el)return;el.textContent=text;el.className=`test-lab-notice ${ok?'ok':'error'}`}
  function download(name,text,type='text/plain'){
    const blob=new Blob([text],{type:`${type};charset=utf-8`});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),500);
  }
  function renderDiagnostics(){
    const box=$('test-lab-checks');if(!box)return;box.innerHTML='';
    const checks=state.diagnostics?.checks||[];
    checks.forEach(item=>{const row=document.createElement('div');row.className='test-check '+(item.ok?'ok':'bad');row.innerHTML=`<span>${item.ok?'✓':'!'}</span><strong>${esc(item.label)}</strong><small>${item.ok?'Opérationnel':'À vérifier'}</small>`;box.append(row)});
    const counts=state.diagnostics?.counts||{};
    const stats=$('test-lab-stats');if(stats)stats.innerHTML=`<div><span>Lots actifs</span><strong>${Number(state.diagnostics?.active_batches||0)}</strong></div><div><span>Comptes de test</span><strong>${Number(state.diagnostics?.test_accounts||0)}</strong></div><div><span>Messages</span><strong>${Number(counts.messages||0)}</strong></div><div><span>Jeux PiGame</span><strong>${Number(counts.generated_games||0)}</strong></div>`;
  }
  function renderBatches(){
    const box=$('test-lab-batches');if(!box)return;box.innerHTML='';
    const active=(state.batches||[]).filter(x=>x.status==='active');
    if(!active.length){box.innerHTML='<p class="muted">Aucun lot de test actif.</p>';return}
    active.forEach(batch=>{const card=document.createElement('article');card.className='test-batch-card';card.innerHTML=`<div><strong>${esc(batch.batch_code)}</strong><small>${esc(batch.created_at)} · préfixe ${esc(batch.prefix)}</small><span>${Number(batch.active_accounts||0)} compte(s) actif(s)</span></div><button type="button" class="mini bad">Supprimer ce lot</button>`;card.querySelector('button').addEventListener('click',()=>removeBatch(batch));box.append(card)});
  }
  function renderCredentials(result){
    lastCredentials=result.credentials||[];lastPassword=result.password||'';
    const section=$('test-lab-credentials');const body=$('test-lab-credentials-body');if(!section||!body)return;
    section.hidden=false;$('test-lab-shared-password').textContent=lastPassword;
    body.innerHTML='';lastCredentials.forEach(item=>{const tr=document.createElement('tr');tr.innerHTML=`<td><strong>${esc(item.username)}</strong></td><td>${esc(item.class_code)}</td><td>${esc(item.role)}</td><td><code>${esc(item.password)}</code></td>`;body.append(tr)});
  }
  async function load(){
    if(!$('test-lab-create-form'))return;
    try{state=await api('/api/admin/test-lab');renderDiagnostics();renderBatches();notice('Laboratoire prêt.',true)}catch(error){notice(error.message)}
  }
  async function create(event){
    event.preventDefault();const button=$('test-lab-create-button');button.disabled=true;notice('Création du lot et des données de démonstration…');
    try{
      const result=await api('/api/admin/test-lab/batches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_count:Number($('test-lab-count').value||20),prefix:$('test-lab-prefix').value.trim()||'test',password:$('test-lab-password').value,include_staff:$('test-lab-staff').checked,sample_data:$('test-lab-samples').checked})});
      renderCredentials(result);notice(`${result.account_count} comptes créés. Copie ou télécharge les identifiants maintenant.`,true);await load();
    }catch(error){notice(error.message)}finally{button.disabled=false}
  }
  async function removeBatch(batch){if(!confirm(`Supprimer les ${batch.active_accounts||0} comptes et toutes leurs données de test ?`))return;try{const result=await api(`/api/admin/test-lab/batches/${batch.id}`,{method:'DELETE'});notice(`${result.removed_accounts} compte(s) de test supprimé(s).`,true);await load()}catch(error){notice(error.message)}}
  async function cleanAll(){if(!confirm('Supprimer TOUS les lots de test actifs ? Les vrais comptes ne seront pas touchés.'))return;try{const result=await api('/api/admin/test-lab/batches',{method:'DELETE'});notice(`${result.removed_accounts} compte(s) de test supprimé(s).`,true);$('test-lab-credentials').hidden=true;await load()}catch(error){notice(error.message)}}
  async function sendDiagnostic(){const button=$('test-lab-send-message');button.disabled=true;try{const result=await api('/api/admin/test-lab/send-message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:'✅ Diagnostic PiChat 3.4 : le serveur accepte bien les messages.'})});notice(`Message de diagnostic envoyé dans le salon ${result.room_id}.`,true)}catch(error){notice(error.message)}finally{button.disabled=false}}
  async function simulateConnections(){const button=$('test-lab-simulate-connections');if(!button)return;button.disabled=true;try{const result=await api('/api/admin/test-lab/simulate-connections',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({count:12})});notice(`${result.simulated_connections} connexions de test simulées sur ${result.test_users} compte(s).`,true);await load()}catch(error){notice(error.message)}finally{button.disabled=false}}
  function copyCredentials(){if(!lastCredentials.length)return;const text=lastCredentials.map(x=>`${x.username}\t${x.password}\t${x.class_code}\t${x.role}`).join('\n');navigator.clipboard?.writeText(text).then(()=>notice('Identifiants copiés.',true)).catch(()=>download('identifiants_pichat_test.txt',text))}
  function downloadCredentials(){if(!lastCredentials.length)return;const rows=['pseudo,mot_de_passe,classe,role',...lastCredentials.map(x=>[x.username,x.password,x.class_code,x.role].map(v=>`"${String(v).replace(/"/g,'""')}"`).join(','))];download('identifiants_pichat_test.csv','\ufeff'+rows.join('\n'),'text/csv')}
  function bind(){
    $('test-lab-create-form')?.addEventListener('submit',create);$('test-lab-clean-all')?.addEventListener('click',cleanAll);$('test-lab-refresh')?.addEventListener('click',load);$('test-lab-send-message')?.addEventListener('click',sendDiagnostic);$('test-lab-simulate-connections')?.addEventListener('click',simulateConnections);$('test-lab-copy-credentials')?.addEventListener('click',copyCredentials);$('test-lab-download-credentials')?.addEventListener('click',downloadCredentials);document.querySelector('[data-tab="test-lab"]')?.addEventListener('click',load);load();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
  window.PiChatTestLab={load};
})();
