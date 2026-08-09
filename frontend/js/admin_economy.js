(() => {
  const $ = id => document.getElementById(id);
  let dashboard = null;
  let searchTimer = null;

  function esc(v){return String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function fmt(v){return new Intl.NumberFormat('fr-FR').format(Number(v||0));}
  async function api(url,options={}){const r=await fetch(url,{credentials:'same-origin',...options});let d=null;try{d=await r.json()}catch{}if(!r.ok)throw new Error(d?.detail||`Erreur ${r.status}`);return d;}
  function toast(text,ok=false){const el=$(ok?'success-message':'error-message');if(!el){alert(text);return}el.textContent=text;el.classList.add('visible');setTimeout(()=>el.classList.remove('visible'),4000);}
  function button(label,cls,handler){const b=document.createElement('button');b.type='button';b.textContent=label;b.className=cls;b.onclick=handler;return b;}

  async function loadEconomy(){
    try{
      const q=$('eco-user-search')?.value.trim()||'';
      dashboard=await api('/api/admin/economy?q='+encodeURIComponent(q));
      render();
    }catch(e){toast(e.message);}
  }

  function render(){
    if(!dashboard)return;
    const s=dashboard.stats||{};
    $('eco-stat-total').textContent=fmt(s.total_coins);
    $('eco-stat-average').textContent=fmt(s.average_coins);
    $('eco-stat-credit').textContent='+'+fmt(s.credited_24h);
    $('eco-stat-spent').textContent='−'+fmt(s.spent_24h);
    $('eco-stat-ops').textContent=fmt(s.operations_24h);
    $('eco-stat-users').textContent=fmt(s.users);
    renderUsers();renderSettings();renderRich();renderTransactions();renderPromos();
  }

  function renderUsers(){
    const body=$('eco-users-body');if(!body)return;body.innerHTML='';
    const rows=dashboard.users||[];
    if(!rows.length){body.innerHTML='<tr><td colspan="4" class="economy-empty">Aucun compte trouvé.</td></tr>';return;}
    rows.forEach(u=>{
      const tr=document.createElement('tr');
      const role=u.is_admin?'ADMIN':u.is_moderator?'MODO':'JOUEUR';
      tr.innerHTML=`<td><strong>${esc(u.username)}</strong><small>${role}${u.is_banned?' · BANNI':''}</small></td><td>${esc(u.class_code||'—')}</td><td><span class="coin-balance">🪙 ${fmt(u.coins)}</span></td><td><div class="coin-actions"></div></td>`;
      const actions=tr.querySelector('.coin-actions');
      actions.append(
        button('+','mini good',()=>adjust(u,'credit')),
        button('−','mini bad',()=>adjust(u,'debit')),
        button('Fixer','mini',()=>adjust(u,'set'))
      );
      body.append(tr);
    });
  }

  async function adjust(u,operation){
    const labels={credit:'Ajouter des PyCoins',debit:'Retirer des PyCoins',set:'Fixer le solde'};
    const raw=prompt(`${labels[operation]} pour ${u.username}\nSolde actuel : ${u.coins}`,operation==='set'?String(u.coins):'100');
    if(raw===null)return;
    const amount=Number(raw);
    if(!Number.isInteger(amount)||amount<0){toast('Montant invalide.');return;}
    const reason=prompt('Motif inscrit dans l’historique :',operation==='credit'?'Récompense administrateur':operation==='debit'?'Correction administrateur':'Solde fixé par un administrateur');
    if(reason===null)return;
    if(!confirm(`${labels[operation]} : ${fmt(amount)} PyCoins pour ${u.username} ?`))return;
    try{
      const d=await api(`/api/admin/economy/users/${u.id}/balance`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operation,amount,reason})});
      toast(`${u.username} : ${d.delta>=0?'+':''}${fmt(d.delta)} PyCoins · nouveau solde ${fmt(d.balance)}`,true);await loadEconomy();
    }catch(e){toast(e.message);}
  }

  function renderSettings(){
    const s=dashboard.settings||{};
    $('eco-daily-reward').value=s.daily_reward??25;
    $('eco-transfer-max').value=s.transfer_max??500;
    $('eco-server-create-cost').value=s.server_creation_cost??100;
    $('eco-server-edit-cost').value=s.server_customization_cost??10;
    $('eco-code-cost').value=s.code_cost??5;
    $('eco-max-servers').value=s.max_owned_servers??3;
    $('eco-transfers-enabled').checked=!!s.transfers_enabled;
  }

  function renderRich(){
    const list=$('eco-rich-list');if(!list)return;list.innerHTML='';
    (dashboard.richest||[]).forEach((u,i)=>{const row=document.createElement('div');row.className='economy-rich-row';row.innerHTML=`<span class="rank">${i+1}</span><span><strong>${esc(u.username)}</strong><small>${esc(u.class_code||'Sans classe')}</small></span><b class="coin-balance">🪙 ${fmt(u.coins)}</b>`;list.append(row);});
  }

  function renderTransactions(){
    const body=$('eco-transactions-body');if(!body)return;body.innerHTML='';
    const rows=dashboard.transactions||[];
    if(!rows.length){body.innerHTML='<tr><td colspan="5" class="economy-empty">Aucune transaction.</td></tr>';return;}
    rows.forEach(x=>{const tr=document.createElement('tr');const sign=Number(x.amount)>=0?'+':'';tr.innerHTML=`<td>${esc(x.created_at)}</td><td><strong>${esc(x.username)}</strong><small>${esc(x.class_code||'')}</small></td><td class="coin-delta ${x.amount>0?'plus':x.amount<0?'minus':'zero'}">${sign}${fmt(x.amount)}</td><td>${esc((x.kind||'').replaceAll('_',' '))}<small>${esc(x.details||'')}</small></td><td>${fmt(x.balance_after)}</td>`;body.append(tr);});
  }

  function renderPromos(){
    const list=$('eco-promo-list');if(!list)return;list.innerHTML='';
    const rows=dashboard.promo_codes||[];
    if(!rows.length){list.innerHTML='<p class="muted">Aucun code promo.</p>';return;}
    rows.forEach(p=>{const card=document.createElement('article');card.className='promo-admin-card'+(p.active?'':' inactive');const exp=p.expires_at?` · expire ${p.expires_at}`:'';card.innerHTML=`<div><code>${esc(p.code)}</code><strong> · ${fmt(p.amount)} PyCoins</strong><small>${fmt(p.uses)}/${fmt(p.max_uses)} utilisation(s)${exp}${p.note?' · '+esc(p.note):''}</small></div><div class="promo-actions"></div>`;card.querySelector('.promo-actions').append(button(p.active?'Désactiver':'Réactiver',p.active?'mini bad':'mini good',()=>togglePromo(p)));list.append(card);});
  }

  async function togglePromo(p){try{await api(`/api/admin/economy/promo-codes/${p.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({active:!p.active})});toast(`Code ${p.code} ${p.active?'désactivé':'réactivé'}.`,true);await loadEconomy();}catch(e){toast(e.message);}}

  async function saveSettings(e){e.preventDefault();const data={daily_reward:Number($('eco-daily-reward').value),transfer_max:Number($('eco-transfer-max').value),transfers_enabled:$('eco-transfers-enabled').checked,server_creation_cost:Number($('eco-server-create-cost').value),server_customization_cost:Number($('eco-server-edit-cost').value),code_cost:Number($('eco-code-cost').value),max_owned_servers:Number($('eco-max-servers').value)};try{await api('/api/admin/economy/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});toast('Réglages de l’économie enregistrés.',true);await loadEconomy();}catch(err){toast(err.message);}}

  async function bulk(e){e.preventDefault();const scope=$('eco-bulk-scope').value;const operation=$('eco-bulk-operation').value;const amount=Number($('eco-bulk-amount').value);const class_code=$('eco-bulk-class').value.trim().toUpperCase();const reason=$('eco-bulk-reason').value.trim();const cible=scope==='all'?'tous les comptes':`la classe ${class_code}`;if(!confirm(`${operation==='credit'?'Ajouter':'Retirer'} ${fmt(amount)} PyCoins à ${cible} ?`))return;try{const d=await api('/api/admin/economy/bulk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope,operation,amount,class_code,reason})});toast(`${d.changed} compte(s) modifié(s)${d.skipped?` · ${d.skipped} ignoré(s)`:''}.`,true);await loadEconomy();}catch(err){toast(err.message);}}

  async function createPromo(e){e.preventDefault();const expiry=$('eco-promo-expiry').value;const data={code:$('eco-promo-code').value.trim().toUpperCase(),amount:Number($('eco-promo-amount').value),max_uses:Number($('eco-promo-uses').value),expires_at:expiry?new Date(expiry).toISOString():null,note:$('eco-promo-note').value.trim()};try{const d=await api('/api/admin/economy/promo-codes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});toast(`Code ${d.code} créé.`,true);e.target.reset();$('eco-promo-amount').value=100;$('eco-promo-uses').value=25;await loadEconomy();}catch(err){toast(err.message);}}

  function updateBulkClass(){const isClass=$('eco-bulk-scope').value==='class';$('eco-bulk-class-wrap').style.display=isClass?'grid':'none';$('eco-bulk-class').required=isClass;}

  function bind(){
    document.querySelectorAll('.nav-item[data-tab="economy"]').forEach(b=>b.addEventListener('click',loadEconomy));
    $('economy-refresh')?.addEventListener('click',loadEconomy);
    $('eco-user-search')?.addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(loadEconomy,280);});
    $('eco-settings-form')?.addEventListener('submit',saveSettings);
    $('eco-bulk-form')?.addEventListener('submit',bulk);
    $('eco-bulk-scope')?.addEventListener('change',updateBulkClass);
    $('eco-promo-form')?.addEventListener('submit',createPromo);
    $('refresh-all')?.addEventListener('click',()=>{if(document.querySelector('[data-panel="economy"]')?.classList.contains('active'))loadEconomy();});
    updateBulkClass();
    if(location.hash==='#economy')setTimeout(loadEconomy,100);
  }
  document.addEventListener('DOMContentLoaded',bind);
})();
