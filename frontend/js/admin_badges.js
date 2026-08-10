(() => {
  const $=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let badgeCatalog=[];
  let adminUsers=[];

  async function api2(url,options={}){
    const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});
    let data={};try{data=await response.json()}catch{}
    if(!response.ok)throw new Error(data.detail||`Erreur ${response.status}`);
    return data;
  }
  function flash(text,ok=true){if(typeof window.msg==='function')window.msg(text,ok);else alert(text)}
  function userLabel(user){return `${user.username}${user.class_code?` [${user.class_code}]`:''}`}
  function selectedUserId(){return Number($('badge-user-select')?.value||0)}
  function fillSelects(){
    const userSelect=$('badge-user-select'),badgeSelect=$('badge-award-select');if(!userSelect||!badgeSelect)return;
    const previous=userSelect.value;
    userSelect.innerHTML=adminUsers.filter(u=>!u.is_bot).map(u=>`<option value="${u.id}">${esc(userLabel(u))}</option>`).join('');
    if(previous&&adminUsers.some(u=>String(u.id)===previous))userSelect.value=previous;
    badgeSelect.innerHTML=badgeCatalog.filter(b=>b.is_active&&!b.is_system).map(b=>`<option value="${b.id}">${esc(b.icon)} ${esc(b.name)}</option>`).join('');
  }
  function renderCatalog(){
    const box=$('badge-catalog');if(!box)return;box.innerHTML='';
    badgeCatalog.forEach(b=>{
      const card=document.createElement('article');card.className='admin-badge-card'+(b.is_active?'':' inactive');card.style.setProperty('--badge-color',b.color||'#f0b232');
      card.innerHTML=`<span class="admin-badge-icon">${esc(b.icon||'🏅')}</span><div><strong>${esc(b.name)}</strong><em>${esc(b.is_system?'SYSTÈME':b.category||'CUSTOM')}</em><small>${esc(b.description||'Aucune description')}</small><small>${b.awarded_count||0} attribution(s) · code ${esc(b.code)}</small></div><div class="admin-badge-actions"></div>`;
      const actions=card.querySelector('.admin-badge-actions');
      if(!b.is_system){
        const edit=document.createElement('button');edit.className='mini brand';edit.textContent='Modifier';edit.onclick=()=>editBadge(b);
        const toggle=document.createElement('button');toggle.className=b.is_active?'mini bad':'mini good';toggle.textContent=b.is_active?'Désactiver':'Réactiver';toggle.onclick=()=>toggleBadge(b);
        actions.append(edit,toggle);
      }else actions.innerHTML='<span class="state-badge state-active">Auto</span>';
      box.append(card);
    });
  }
  async function editBadge(b){
    const name=prompt('Nom du badge :',b.name);if(name===null||!name.trim())return;
    const description=prompt('Description :',b.description||'');if(description===null)return;
    const icon=prompt('Icône emoji :',b.icon||'🏅');if(icon===null||!icon.trim())return;
    const color=prompt('Couleur #RRGGBB :',b.color||'#f0b232');if(color===null)return;
    try{await api2(`/api/admin/badges/${b.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name.trim(),description:description.trim(),icon:icon.trim(),color:color.trim()})});flash('Badge modifié.',true);await load()}
    catch(e){flash(e.message,false)}
  }
  async function toggleBadge(b){
    if(!confirm(`${b.is_active?'Désactiver':'Réactiver'} le badge ${b.name} ?`))return;
    try{await api2(`/api/admin/badges/${b.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({is_active:!b.is_active})});flash('État du badge modifié.',true);await load()}
    catch(e){flash(e.message,false)}
  }
  async function loadSelectedUser(){
    const userId=selectedUserId(),box=$('badge-user-current');if(!userId||!box)return;
    box.innerHTML='<p class="muted">Chargement…</p>';
    try{
      const data=await api2(`/api/admin/users/${userId}/gaming-profile`);
      const user=adminUsers.find(u=>u.id===userId);
      box.innerHTML=`<div class="admin-user-badge-head"><div><strong>${esc(user?.username||'Compte')}</strong><small>${esc(user?.class_code||'Sans classe')}</small></div><span>${(data.badges||[]).length} badge(s) · ${(data.games||[]).length} jeu(x)</span></div><div class="admin-user-badge-list"></div><h3>Pseudos de jeux</h3><div class="admin-user-games"></div>`;
      const badgesBox=box.querySelector('.admin-user-badge-list');
      if(!(data.badges||[]).length)badgesBox.innerHTML='<span class="muted">Aucun badge.</span>';
      (data.badges||[]).forEach(b=>{const chip=document.createElement('span');chip.className='admin-user-badge';chip.style.setProperty('--badge-color',b.color||'#f0b232');chip.innerHTML=`<span>${esc(b.icon)}</span><strong>${esc(b.name)}</strong>${b.is_system?'':`<button title="Retirer">×</button>`}`;chip.querySelector('button')?.addEventListener('click',()=>removeBadge(userId,b));badgesBox.append(chip)});
      const gamesBox=box.querySelector('.admin-user-games');
      if(!(data.games||[]).length)gamesBox.innerHTML='<span class="muted">Aucun pseudo de jeu.</span>';
      (data.games||[]).forEach(g=>{const row=document.createElement('div');row.className='admin-user-game';row.innerHTML=`<span>${esc(g.icon||'🎮')}</span><div><strong>${esc(g.game_name)} · ${esc(g.username)}</strong><small>${esc(g.platform||'Plateforme non précisée')} · ${g.is_public?'Public':'Privé'}</small></div><button title="Supprimer ce profil de jeu">×</button>`;row.querySelector('button').onclick=()=>deleteGame(userId,g);gamesBox.append(row)});
    }catch(e){box.innerHTML=`<p class="muted">${esc(e.message)}</p>`}
  }
  async function removeBadge(userId,b){if(!confirm(`Retirer le badge ${b.name} ?`))return;try{await api2(`/api/admin/users/${userId}/badges/${b.id}`,{method:'DELETE'});flash('Badge retiré.',true);await Promise.all([load(),loadSelectedUser()])}catch(e){flash(e.message,false)}}
  async function deleteGame(userId,g){if(!confirm(`Supprimer le pseudo ${g.username} pour ${g.game_name} ?`))return;try{await api2(`/api/admin/users/${userId}/games/${g.id}`,{method:'DELETE'});flash('Profil de jeu supprimé.',true);await loadSelectedUser()}catch(e){flash(e.message,false)}}
  async function createBadge(event){event.preventDefault();try{await api2('/api/admin/badges',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('badge-name').value.trim(),code:$('badge-code').value.trim(),icon:$('badge-icon').value.trim()||'🏅',color:$('badge-color').value,category:$('badge-category').value.trim()||'custom',description:$('badge-description').value.trim()})});event.target.reset();$('badge-icon').value='🏅';$('badge-color').value='#f0b232';$('badge-category').value='custom';flash('Badge créé.',true);await load()}catch(e){flash(e.message,false)}}
  async function award(event){event.preventDefault();const userId=selectedUserId(),badgeId=Number($('badge-award-select').value||0);if(!userId||!badgeId){flash('Choisis un utilisateur et un badge.',false);return}try{await api2(`/api/admin/users/${userId}/badges/${badgeId}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:$('badge-award-reason').value.trim(),showcased:$('badge-showcased').checked})});$('badge-award-reason').value='';flash('Badge attribué.',true);await Promise.all([load(),loadSelectedUser()])}catch(e){flash(e.message,false)}}
  async function load(){
    if(!$('badge-catalog'))return;
    try{[badgeCatalog,adminUsers]=await Promise.all([api2('/api/admin/badges'),api2('/api/admin/users')]);fillSelects();renderCatalog();await loadSelectedUser()}catch(e){flash(e.message,false)}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    $('badge-create-form')?.addEventListener('submit',createBadge);
    $('badge-award-form')?.addEventListener('submit',award);
    $('badge-user-select')?.addEventListener('change',loadSelectedUser);
    $('badge-refresh')?.addEventListener('click',load);
    document.querySelector('[data-tab="badges"]')?.addEventListener('click',load);
    if(location.hash==='#badges')load();
    window.PiChatAdminBadges={openForUser:async userId=>{document.querySelector('[data-tab="badges"]')?.click();await load();if($('badge-user-select')){$('badge-user-select').value=String(userId);await loadSelectedUser()}}};
  });
})();
