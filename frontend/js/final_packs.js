(()=>{
  'use strict';
  const $=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let modal=null;
  let settings=null;

  async function api(url,options={}){
    const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});
    let data={};try{data=await response.json()}catch{}
    if(!response.ok)throw new Error(data.detail||`Erreur ${response.status}`);
    return data;
  }
  function toast(message,ok=false){window.PiChatTrolls?.toast?.(message,ok);if(!window.PiChatTrolls)alert(message)}
  function initials(name){return String(name||'?').split(/\s+/).map(x=>x[0]||'').join('').slice(0,2).toUpperCase()||'?'}
  function prettyDate(value){if(!value)return '—';const iso=value.includes('T')?value:value.replace(' ','T')+'Z';const date=new Date(iso);return Number.isNaN(date.getTime())?value:date.toLocaleString()}

  function ensureModal(){
    if(modal)return modal;
    modal=document.createElement('div');
    modal.id='final-packs-modal';
    modal.className='modal-backdrop final-packs-modal';
    modal.innerHTML=`<section class="discord-modal wide-modal final-packs-card">
      <header><div><span class="eyebrow">PACKS FINAUX 2.2</span><h2>Social, planning et sécurité</h2><p>Amis, messages programmés et appareils connectés.</p></div><button class="modal-close" type="button">×</button></header>
      <nav class="final-pack-tabs">
        <button type="button" data-pack-tab="social" class="active">🤝 Amis</button>
        <button type="button" data-pack-tab="schedule">⏰ Programmer</button>
        <button type="button" data-pack-tab="sessions">🔐 Appareils</button>
      </nav>
      <div class="final-pack-panel active" data-pack-panel="social">
        <form id="social-search-form" class="final-pack-search"><input id="social-search-input" maxlength="40" placeholder="Rechercher un pseudo" required><button>Rechercher</button></form>
        <div id="social-search-results" class="final-pack-list compact"></div>
        <div class="final-pack-columns">
          <section><h3>Demandes reçues</h3><div id="social-incoming" class="final-pack-list"></div></section>
          <section><h3>Mes amis</h3><div id="social-friends" class="final-pack-list"></div></section>
          <section><h3>Demandes envoyées</h3><div id="social-outgoing" class="final-pack-list"></div></section>
          <section><h3>Comptes bloqués</h3><div id="social-blocked" class="final-pack-list"></div></section>
        </div>
      </div>
      <div class="final-pack-panel" data-pack-panel="schedule">
        <form id="schedule-message-form" class="schedule-form">
          <label>Message<textarea id="schedule-content" rows="4" maxlength="2000" required placeholder="Le message à envoyer plus tard"></textarea></label>
          <div class="schedule-grid"><label>Date et heure<input id="schedule-at" type="datetime-local" required></label><label>Salon<input id="schedule-room" readonly value="Salon actuel"></label></div>
          <button class="primary-action" type="submit">⏰ Programmer ce message</button>
        </form>
        <div class="final-pack-head"><h3>Mes messages en attente</h3><button id="schedule-refresh" type="button">Actualiser</button></div>
        <div id="scheduled-list" class="final-pack-list"></div>
      </div>
      <div class="final-pack-panel" data-pack-panel="sessions">
        <div class="final-pack-head"><div><h3>Appareils connectés</h3><p>Ferme les anciennes sessions sans changer ton mot de passe.</p></div><button id="sessions-revoke-others" type="button" class="danger-soft">Déconnecter les autres</button></div>
        <div id="sessions-list" class="final-pack-list"></div>
      </div>
    </section>`;
    document.body.append(modal);
    modal.querySelector('.modal-close').onclick=()=>close();
    modal.onclick=event=>{if(event.target===modal)close()};
    modal.querySelectorAll('[data-pack-tab]').forEach(button=>button.onclick=()=>selectTab(button.dataset.packTab));
    $('social-search-form').addEventListener('submit',searchUsers);
    $('schedule-message-form').addEventListener('submit',scheduleMessage);
    $('schedule-refresh').onclick=loadScheduled;
    $('sessions-revoke-others').onclick=revokeOtherSessions;
    const when=$('schedule-at');
    const minimum=new Date(Date.now()+60000);minimum.setSeconds(0,0);when.min=toLocalInput(minimum);when.value=toLocalInput(new Date(Date.now()+10*60000));
    return modal;
  }
  function toLocalInput(date){const local=new Date(date.getTime()-date.getTimezoneOffset()*60000);return local.toISOString().slice(0,16)}
  function selectTab(name){
    ensureModal().querySelectorAll('[data-pack-tab]').forEach(x=>x.classList.toggle('active',x.dataset.packTab===name));
    ensureModal().querySelectorAll('[data-pack-panel]').forEach(x=>x.classList.toggle('active',x.dataset.packPanel===name));
    if(name==='social')loadSocial();
    if(name==='schedule')loadScheduled();
    if(name==='sessions')loadSessions();
  }
  function open(tab='social'){
    ensureModal().classList.add('open');
    selectTab(tab);
  }
  function close(){modal?.classList.remove('open')}

  function userCard(user,actions=[]){
    const item=document.createElement('article');item.className='final-pack-item user';
    item.innerHTML=`<span class="final-pack-avatar" style="background:${esc(user.profile_color||'#5865f2')}">${esc(initials(user.username))}</span><div class="final-pack-main"><strong>${esc(user.username)}</strong><small>${esc(user.class_code||'Sans classe')}${user.status_message?' · '+esc(user.status_message):''}</small></div><div class="final-pack-actions"></div>`;
    const box=item.querySelector('.final-pack-actions');
    actions.forEach(action=>{const button=document.createElement('button');button.type='button';button.textContent=action.label;button.className=action.kind||'';button.onclick=action.run;box.append(button)});
    item.querySelector('.final-pack-main').onclick=()=>window.PiChatCommunity?.openPublicProfile?.(user.id);
    return item;
  }
  function empty(box,text){box.innerHTML=`<p class="final-pack-empty">${esc(text)}</p>`}

  async function loadSocial(){
    const incoming=$('social-incoming'),friends=$('social-friends'),outgoing=$('social-outgoing'),blocked=$('social-blocked');
    [incoming,friends,outgoing,blocked].forEach(x=>x.innerHTML='<p class="final-pack-empty">Chargement…</p>');
    try{
      const data=await api('/api/social');
      renderUsers(incoming,data.incoming,'Aucune demande reçue.',u=>[
        {label:'Accepter',kind:'good',run:()=>respondRequest(u.friendship_id,true)},
        {label:'Refuser',kind:'bad',run:()=>respondRequest(u.friendship_id,false)}
      ]);
      renderUsers(friends,data.friends,'Aucun ami pour le moment.',u=>[
        {label:'Profil',run:()=>window.PiChatCommunity?.openPublicProfile?.(u.id)},
        {label:'Retirer',kind:'bad',run:()=>removeFriend(u.id)},
        {label:'Bloquer',kind:'danger-soft',run:()=>block(u.id)}
      ]);
      renderUsers(outgoing,data.outgoing,'Aucune demande envoyée.',()=>[]);
      renderUsers(blocked,data.blocked,'Aucun compte bloqué.',u=>[{label:'Débloquer',run:()=>unblock(u.id)}]);
    }catch(error){[incoming,friends,outgoing,blocked].forEach(x=>empty(x,error.message))}
  }
  function renderUsers(box,items,emptyText,actionFactory){box.innerHTML='';if(!items?.length){empty(box,emptyText);return}items.forEach(user=>box.append(userCard(user,actionFactory(user))))}
  async function searchUsers(event){
    event.preventDefault();const query=$('social-search-input').value.trim();const box=$('social-search-results');
    if(query.length<2)return;box.innerHTML='<p class="final-pack-empty">Recherche…</p>';
    try{
      const data=await api('/api/social/search?q='+encodeURIComponent(query));box.innerHTML='';
      if(!data.users.length){empty(box,'Aucun compte trouvé.');return}
      data.users.forEach(user=>{
        const actions=[];
        if(user.relation==='none')actions.push({label:'Ajouter',kind:'good',run:()=>requestFriend(user.id)});
        if(user.relation==='incoming')actions.push({label:'Voir la demande',run:()=>loadSocial()});
        if(user.relation==='outgoing')actions.push({label:'Déjà envoyée',run:()=>{}});
        if(user.relation==='friend')actions.push({label:'Déjà ami',run:()=>{}});
        if(user.relation==='blocked')actions.push({label:'Débloquer',run:()=>unblock(user.id)});
        if(user.relation!=='blocked')actions.push({label:'Bloquer',kind:'danger-soft',run:()=>block(user.id)});
        box.append(userCard(user,actions));
      });
    }catch(error){empty(box,error.message)}
  }
  async function requestFriend(userId){try{const data=await api('/api/social/request',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:userId})});toast(data.accepted?'Vous êtes maintenant amis ✓':'Demande envoyée ✓',true);await loadSocial()}catch(error){toast(error.message)}}
  async function respondRequest(id,accept){try{await api(`/api/social/requests/${id}/respond`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({accept})});toast(accept?'Demande acceptée ✓':'Demande refusée.',accept);await loadSocial()}catch(error){toast(error.message)}}
  async function removeFriend(id){if(!confirm('Retirer ce compte de tes amis ?'))return;try{await api(`/api/social/friends/${id}`,{method:'DELETE'});await loadSocial()}catch(error){toast(error.message)}}
  async function block(id){if(!confirm('Bloquer ce compte ? Les messages privés seront aussi bloqués.'))return;try{await api(`/api/social/block/${id}`,{method:'POST'});toast('Compte bloqué.',true);await loadSocial()}catch(error){toast(error.message)}}
  async function unblock(id){try{await api(`/api/social/block/${id}`,{method:'DELETE'});toast('Compte débloqué.',true);await loadSocial()}catch(error){toast(error.message)}}

  async function loadScheduled(){
    const box=$('scheduled-list');if(!box)return;box.innerHTML='<p class="final-pack-empty">Chargement…</p>';
    const room=(window.CURRENT_ROOMS||[]).find(r=>Number(r.id)===Number(window.currentRoomId));
    $('schedule-room').value=room?`# ${room.name}`:'Aucun salon sélectionné';
    try{
      const data=await api('/api/scheduled-messages');box.innerHTML='';
      if(!data.messages.length){empty(box,'Aucun message programmé.');return}
      data.messages.forEach(message=>{
        const item=document.createElement('article');item.className='final-pack-item scheduled';
        item.innerHTML=`<div class="final-pack-main"><strong>#${esc(message.room_name)} · ${esc(prettyDate(message.send_at))}</strong><p>${esc(message.content)}</p><small>État : ${esc(message.status)}</small></div><div class="final-pack-actions"><button type="button" class="bad">Annuler</button></div>`;
        item.querySelector('button').onclick=()=>cancelScheduled(message.id);box.append(item);
      });
    }catch(error){empty(box,error.message)}
  }
  async function scheduleMessage(event){
    event.preventDefault();
    if(!window.currentRoomId){toast('Choisis d’abord un salon.');return}
    const local=$('schedule-at').value;if(!local){toast('Choisis une date et une heure.');return}
    const button=event.submitter||event.currentTarget.querySelector('button[type="submit"]');button.disabled=true;
    try{
      await api('/api/scheduled-messages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({room_id:Number(window.currentRoomId),content:$('schedule-content').value.trim(),send_at:new Date(local).toISOString()})});
      $('schedule-content').value='';toast('Message programmé ✓',true);await loadScheduled();
    }catch(error){toast(error.message)}finally{button.disabled=false}
  }
  async function cancelScheduled(id){if(!confirm('Annuler ce message programmé ?'))return;try{await api(`/api/scheduled-messages/${id}`,{method:'DELETE'});await loadScheduled()}catch(error){toast(error.message)}}

  function deviceLabel(agent){const text=String(agent||'');if(/iPhone|iPad/i.test(text))return '📱 iPhone / iPad';if(/Android/i.test(text))return '📱 Android';if(/Macintosh|Mac OS/i.test(text))return '💻 Mac';if(/Windows/i.test(text))return '💻 Windows';return '🌐 Navigateur'}
  async function loadSessions(){
    const box=$('sessions-list');box.innerHTML='<p class="final-pack-empty">Chargement…</p>';
    try{
      const data=await api('/api/my-sessions');box.innerHTML='';
      data.sessions.forEach(session=>{
        const item=document.createElement('article');item.className='final-pack-item session'+(session.current?' current':'');
        item.innerHTML=`<div class="final-pack-main"><strong>${esc(deviceLabel(session.user_agent))}${session.current?' · Cet appareil':''}</strong><small>IP : ${esc(session.ip_address)} · dernière activité ${esc(prettyDate(session.last_seen_at))}</small><details><summary>Détails</summary><code>${esc(session.user_agent)}</code></details></div><div class="final-pack-actions"></div>`;
        if(!session.current){const button=document.createElement('button');button.type='button';button.className='bad';button.textContent='Déconnecter';button.onclick=()=>revokeSession(session.id);item.querySelector('.final-pack-actions').append(button)}
        box.append(item);
      });
      if(!data.sessions.length)empty(box,'Aucune session active.');
    }catch(error){empty(box,error.message)}
  }
  async function revokeSession(id){try{await api(`/api/my-sessions/${id}`,{method:'DELETE'});toast('Session déconnectée.',true);await loadSessions()}catch(error){toast(error.message)}}
  async function revokeOtherSessions(){if(!confirm('Déconnecter tous les autres appareils ?'))return;try{const data=await api('/api/my-sessions',{method:'DELETE'});toast(`${data.revoked} session(s) déconnectée(s).`,true);await loadSessions()}catch(error){toast(error.message)}}

  async function boot(){
    try{const data=await api('/api/final-packs/status');settings=data.settings}catch{return}
    const opener=$('open-final-packs');if(opener){opener.hidden=!(settings.social_enabled||settings.scheduled_messages_enabled||settings.session_manager_enabled);opener.addEventListener('click',()=>open('social'))}
    const composer=$('message-form');
    if(composer&&settings.scheduled_messages_enabled&&!$('schedule-message-button')){
      const button=document.createElement('button');button.type='button';button.id='schedule-message-button';button.className='composer-icon';button.title='Programmer un message';button.textContent='⏰';button.onclick=()=>open('schedule');
      const emoji=$('emoji-button');composer.insertBefore(button,emoji||composer.lastElementChild);
    }
  }
  document.addEventListener('DOMContentLoaded',boot);
  window.PiChatFinalPacks={open,loadSocial,loadScheduled,loadSessions};
})();
