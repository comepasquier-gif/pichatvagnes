(() => {
  const $ = id => document.getElementById(id);
  let features = {};
  let wallet = null;
  let servers = [];

  function toast(text){ window.PiChatTrolls?.toast?.(text); if(!window.PiChatTrolls) console.log(text); }
  function esc(v){ return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  async function api(url, options={}){
    const r = await fetch(url, {credentials:'same-origin', ...options});
    let d = null; try{ d = await r.json(); }catch{}
    if(!r.ok) throw new Error(d?.detail || `Erreur ${r.status}`);
    return d;
  }
  function openModal(id){ $(id)?.classList.add('open'); }
  function closeModal(id){ $(id)?.classList.remove('open'); }

  function setupSupportBanner(){
    const user = window.CURRENT_USER;
    const banner = $('support-mode-banner');
    if(!banner || !user?.support_mode) return;
    banner.hidden = false;
    $('support-target-name').textContent = user.username;
    document.body.classList.add('support-mode-active');
  }

  async function loadFeatures(){
    try{ features = await api('/api/community/features'); }catch{ features = {}; }
    if($('open-economy')) $('open-economy').style.display = (features.pycoins_enabled || features.custom_servers_enabled) ? '' : 'none';
    if($('open-code-lab')) $('open-code-lab').style.display = features.code_lab_enabled ? '' : 'none';
  }

  async function loadEconomy(){
    $('custom-server-list').innerHTML = '<p class="muted">Chargement…</p>';
    try{
      const results = await Promise.all([
        features.pycoins_enabled ? api('/api/pycoins/wallet') : Promise.resolve({balance:0,transactions:[],daily_available:false}),
        features.custom_servers_enabled ? api('/api/custom-servers') : Promise.resolve([]),
      ]);
      wallet = results[0]; servers = results[1]; renderEconomy();
    }catch(e){ $('custom-server-list').innerHTML = `<p class="error-text">${esc(e.message)}</p>`; }
  }

  function renderEconomy(){
    $('pycoin-balance').textContent = wallet?.balance ?? 0;
    $('claim-daily').disabled = !wallet?.daily_available;
    $('claim-daily').textContent = wallet?.daily_available ? `🎁 Bonus quotidien +${wallet?.daily_reward ?? 25}` : '✓ Bonus déjà récupéré';
    $('code-lab-cost').textContent = `${wallet?.code_cost ?? 5} PyCoins`;
    if($('pycoin-amount')) $('pycoin-amount').max = wallet?.transfer_max ?? 500;
    const transferButton=$('pycoin-transfer-form')?.querySelector('button'); if(transferButton) transferButton.disabled=!wallet?.transfers_enabled;
    const createTitle=$('custom-server-form')?.closest('article')?.querySelector('h3'); if(createTitle) createTitle.textContent=`Créer un serveur · ${wallet?.server_creation_cost ?? 100} PyCoins`;
    const tx = $('pycoin-transactions'); tx.innerHTML = '';
    const rows = wallet?.transactions || [];
    if(!rows.length) tx.innerHTML = '<p class="muted">Aucune opération.</p>';
    rows.forEach(x => {
      const row = document.createElement('div'); row.className = 'transaction-row';
      row.innerHTML = `<span><strong>${esc(x.kind.replaceAll('_',' '))}</strong><small>${esc(x.details || x.created_at)}</small></span><b class="${x.amount >= 0 ? 'coin-plus' : 'coin-minus'}">${x.amount >= 0 ? '+' : ''}${x.amount}</b>`;
      tx.append(row);
    });
    const list = $('custom-server-list'); list.innerHTML = '';
    if(!servers.length) list.innerHTML = `<div class="empty-economy">Aucun serveur personnel. Limite actuelle : ${wallet?.max_owned_servers ?? 3}.</div>`;
    servers.forEach(server => {
      const card = document.createElement('article'); card.className = 'custom-server-card';
      const invite = server.is_owner ? `<code>${esc(server.invite_code || '—')}</code>` : '<span>Membre</span>';
      card.innerHTML = `<button class="server-card-open"><span class="server-card-icon">${esc(server.icon || '💬')}</span><span><strong>${esc(server.name)}</strong><small>${esc(server.description || 'Serveur personnel')}</small></span></button><div class="server-card-meta"><span>Invitation : ${invite}</span><span>${server.is_owner ? 'PROPRIÉTAIRE' : 'MEMBRE'}</span></div><div class="server-card-actions"></div>`;
      card.querySelector('.server-card-open').onclick = () => { closeModal('economy-modal'); window.switchRoom?.(server.id); };
      const actions = card.querySelector('.server-card-actions');
      const make = (label, fn, cls='') => { const b=document.createElement('button'); b.textContent=label; b.className=cls; b.onclick=fn; actions.append(b); };
      if(server.is_owner || window.CURRENT_USER?.is_admin){
        make('Copier le code', async()=>{ try{await navigator.clipboard.writeText(server.invite_code);toast('Code copié ✓')}catch{prompt('Code :',server.invite_code)} });
        make('Ajouter un membre', async()=>{ const username=prompt('Pseudo à ajouter :'); if(!username)return; try{await api(`/api/custom-servers/${server.id}/members`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username})});toast('Membre ajouté ✓')}catch(e){toast(e.message)} });
        make(`Modifier · ${wallet?.server_customization_cost ?? 10}`, async()=>{ const name=prompt('Nouveau nom :',server.name);if(!name)return;const description=prompt('Description :',server.description||'')??server.description;const icon=prompt('Emoji / icône :',server.icon||'💬')??server.icon;try{await api(`/api/custom-servers/${server.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,description,icon})});await reloadAll();toast('Serveur modifié ✓')}catch(e){toast(e.message)} });
        make('Supprimer', async()=>{ if(!confirm(`Supprimer définitivement ${server.name} ?`))return;try{await api(`/api/custom-servers/${server.id}`,{method:'DELETE'});await reloadAll();toast('Serveur supprimé')}catch(e){toast(e.message)} },'danger');
      }else{
        make('Quitter', async()=>{if(!confirm(`Quitter ${server.name} ?`))return;try{await api(`/api/custom-servers/${server.id}/leave`,{method:'POST'});await reloadAll()}catch(e){toast(e.message)}},'danger');
      }
      list.append(card);
    });
  }

  async function reloadAll(){
    await loadEconomy();
    await window.loadRoomList?.();
  }

  async function claimDaily(){ try{const d=await api('/api/pycoins/daily',{method:'POST'});toast(`+${d.reward} PyCoins 🎉`);await loadEconomy();window.PiChatCommunity?.openPublicProfile && null;}catch(e){toast(e.message)} }
  async function transferCoins(event){ event.preventDefault(); try{const d=await api('/api/pycoins/transfer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('pycoin-recipient').value.trim(),amount:Number($('pycoin-amount').value)})});toast(`${d.amount} PyCoins envoyés à ${d.recipient}`);$('pycoin-recipient').value='';await loadEconomy()}catch(e){toast(e.message)} }

  async function redeemPromo(event){
    event.preventDefault();
    const code=$('pycoin-promo-code').value.trim();
    if(!code)return;
    try{
      const d=await api('/api/pycoins/redeem',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});
      toast(`Code validé : +${d.reward} PyCoins 🎉`);
      $('pycoin-promo-code').value='';
      await loadEconomy();
    }catch(e){toast(e.message)}
  }

  async function createServer(event){ event.preventDefault(); try{const server=await api('/api/custom-servers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('custom-server-name').value.trim(),description:$('custom-server-description').value.trim(),icon:$('custom-server-icon').value.trim()||'💬'})});toast(`Serveur ${server.name} créé ✓`);event.target.reset();$('custom-server-icon').value='💬';await reloadAll()}catch(e){toast(e.message)} }
  async function joinServer(event){ event.preventDefault(); try{const server=await api('/api/custom-servers/join',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({invite_code:$('join-server-code').value.trim()})});toast(`Bienvenue dans ${server.name} ✓`);$('join-server-code').value='';await reloadAll()}catch(e){toast(e.message)} }

  async function generateCode(event){
    event.preventDefault();
    const promptText = $('code-lab-prompt').value.trim(); if(!promptText) return;
    const button = $('code-lab-submit'); button.disabled = true; $('code-lab-status').textContent = 'PiCode réfléchit et vérifie la sécurité du code…';
    try{
      await api('/api/code-lab/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({room_id:window.currentRoomId,prompt:promptText,title:$('code-lab-title').value.trim()||'Mini-code Python'})});
      $('code-lab-status').textContent = 'Code publié dans le salon ✓'; $('code-lab-prompt').value=''; closeModal('code-lab-modal');
    }catch(e){ $('code-lab-status').textContent = '⚠️ '+e.message; }
    finally{ button.disabled=false; loadEconomy().catch(()=>{}); }
  }

  function bind(){
    $('open-economy')?.addEventListener('click',()=>{openModal('economy-modal');loadEconomy()});
    $('open-code-lab')?.addEventListener('click',()=>openModal('code-lab-modal'));
    $('claim-daily')?.addEventListener('click',claimDaily);
    $('pycoin-transfer-form')?.addEventListener('submit',transferCoins);
    $('pycoin-promo-form')?.addEventListener('submit',redeemPromo);
    $('custom-server-form')?.addEventListener('submit',createServer);
    $('join-server-form')?.addEventListener('submit',joinServer);
    $('code-lab-form')?.addEventListener('submit',generateCode);
    ['economy-modal','code-lab-modal'].forEach(id=>{const modal=$(id);modal?.querySelector('.modal-close')?.addEventListener('click',()=>closeModal(id));modal?.addEventListener('click',e=>{if(e.target===modal)closeModal(id)})});
  }

  async function init(){ setupSupportBanner(); await loadFeatures(); bind(); }
  window.addEventListener('pichat:user-ready', init, {once:true});
  if(window.CURRENT_USER) init();
})();
