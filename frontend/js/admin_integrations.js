(() => {
  const $=id=>document.getElementById(id);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function api(url,options={}){const r=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||`Erreur ${r.status}`);return d}
  function message(text,ok=false){const el=$('integration-message');if(!el)return;el.textContent=text;el.className=`integration-message visible ${ok?'success':'error'}`}
  function render(items){
    const box=$('integration-list34');if(!box)return;
    const state=$('integration-state');if(state){state.classList.toggle('connected',items.some(x=>x.enabled&&x.configured));state.querySelector('small').textContent=`${items.length} intégration(s) · clés masquées`;}
    if(!items.length){box.innerHTML='<p class="muted">Aucune API configurée.</p>';return}
    box.innerHTML=items.map(i=>`<article class="integration-item34" data-id="${i.id}"><div><strong>${esc(i.name)}</strong><small>${esc(i.provider)}</small></div><div><strong>${esc(i.model)}</strong><small class="integration-key34">${esc(i.key_hint||'clé absente')}</small></div><div><strong>${i.enabled?'Active':'Désactivée'}</strong><small>${esc(i.last_test_status||'never')} ${i.last_test_message?`· ${esc(i.last_test_message)}`:''}</small></div><div class="toolbar"><button class="mini test" type="button">Tester</button><button class="mini toggle" type="button">${i.enabled?'Désactiver':'Activer'}</button><button class="mini bad remove" type="button">Supprimer</button></div></article>`).join('');
    box.querySelectorAll('[data-id]').forEach(card=>{const id=Number(card.dataset.id),item=items.find(x=>x.id===id);card.querySelector('.test').onclick=()=>test(id);card.querySelector('.toggle').onclick=()=>toggle(id,!item.enabled);card.querySelector('.remove').onclick=()=>remove(id,item.name)});
  }
  async function load(){try{const d=await api('/api/admin/integrations');render(d.items||[])}catch(e){message(e.message)}}
  async function add(event){event.preventDefault();try{await api('/api/admin/integrations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('integration-name').value.trim(),provider:$('integration-provider').value,api_key:$('integration-api-key').value.trim(),model:$('integration-model').value.trim()})});$('integration-api-key').value='';message('API enregistrée côté serveur.',true);await load();window.PiGameStudioAdmin?.load?.()}catch(e){message(e.message)}}
  async function test(id){try{const d=await api(`/api/admin/integrations/${id}/test`,{method:'POST'});message(d.message||'Connexion réussie.',true);await load()}catch(e){message(e.message);await load()}}
  async function toggle(id,enabled){try{await api(`/api/admin/integrations/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled})});message(enabled?'API activée.':'API désactivée.',true);await load()}catch(e){message(e.message)}}
  async function remove(id,name){if(!confirm(`Supprimer l’intégration « ${name} » ?`))return;try{await api(`/api/admin/integrations/${id}`,{method:'DELETE'});message('API supprimée.',true);await load()}catch(e){message(e.message)}}
  function bind(){$('integration-add-form')?.addEventListener('submit',add);$('integration-refresh')?.addEventListener('click',load);document.querySelector('[data-tab="integrations"]')?.addEventListener('click',load);load()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
  window.PiChatIntegrations={load};
})();
