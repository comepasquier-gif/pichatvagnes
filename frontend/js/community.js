(() => {
  const $=(id)=>document.getElementById(id);
  let features={games_enabled:true,arcade_enabled:true,tutor_enabled:true,reactions_enabled:true,reports_enabled:true,member_panel:true,gaming_profiles_enabled:true};
  let myProfile=null;

  function modal(id,open=true){const el=$(id);if(!el)return;el.classList.toggle('open',open)}
  function closeAll(){document.querySelectorAll('.modal-backdrop.open').forEach(x=>x.classList.remove('open'))}
  function toast(text){window.PiChatTrolls?.toast?.(text)||alert(text)}
  function escapeHtml(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
  function initials(name){return (name||'?').slice(0,2).toUpperCase()}

  async function loadFeatures(){try{const r=await fetch('/api/community/features',{credentials:'same-origin'});if(r.ok)features=await r.json()}catch{};applyFeatures()}
  function applyFeatures(){
    const tutor=$('open-tutor');const qt=$('quick-tutor');const games=$('open-games');const members=$('toggle-members');const gaming=$('open-gaming-profile');
    if(tutor)tutor.style.display=features.tutor_enabled?'':'none';if(qt)qt.style.display=features.tutor_enabled?'':'none';if(games)games.style.display=features.arcade_enabled?'':'none';if(members)members.style.display=features.member_panel?'':'none';if(gaming)gaming.style.display=features.gaming_profiles_enabled?'':'none';
  }

  async function refreshMembers(){
    if(!features.member_panel||!window.currentRoomId)return;
    try{const r=await fetch(`/api/rooms/${window.currentRoomId}/members`,{credentials:'same-origin',cache:'no-store'});if(!r.ok)return;renderMembers(await r.json())}catch{}
  }
  function renderMembers(members){
    const list=$('member-list');if(!list)return;list.innerHTML='';
    const groups=[['EN LIGNE',members.filter(x=>x.online)],['HORS LIGNE',members.filter(x=>!x.online)]];
    for(const [label,xs] of groups){if(!xs.length)continue;const title=document.createElement('div');title.className='member-group-title';title.textContent=`${label} — ${xs.length}`;list.append(title);xs.forEach(m=>{const row=document.createElement('div');row.className='member-row';row.onclick=()=>openPublicProfile(m.id);const a=document.createElement('span');a.className='avatar'+(m.online?'':' offline');a.textContent=initials(m.username);a.style.background=m.color||'#5865f2';const txt=document.createElement('span');const strong=document.createElement('strong');strong.textContent=m.username;const small=document.createElement('small');small.textContent=m.presence_status||m.role_label||m.status_message||m.class_code||'Membre';if(m.presence_kind==='admin_scheming')row.classList.add('admin-scheming');txt.append(strong,small);row.append(a,txt);list.append(row)})}
  }

  async function loadMyProfile(){
    try{const r=await fetch('/api/profile/me',{credentials:'same-origin',cache:'no-store'});if(!r.ok)return;myProfile=await r.json();fillProfile(myProfile)}catch{}
  }
  function fillProfile(p){
    if(!p)return;
    $('profile-preview-avatar').textContent=initials(p.username);
    $('profile-preview-avatar').style.background=p.color||'#5865f2';
    $('profile-preview-name').textContent=p.username;
    $('profile-preview-role').textContent=p.role_label||'Grade masqué';
    $('profile-status').value=p.status_message||'';
    $('profile-bio').value=p.bio||'';
    $('profile-color').value=p.color||'#5865f2';
    $('grade-visibility').value=p.grade_visibility||'full';
    window.PiChatGamingProfiles?.renderProfile?.(p);
  }
  async function saveProfile(){
    try{
      let d;
      if(window.PiChatGamingProfiles?.saveProfile){
        d=await window.PiChatGamingProfiles.saveProfile();
      }else{
        const data={status_message:$('profile-status').value.trim(),profile_bio:$('profile-bio').value.trim(),profile_color:$('profile-color').value,grade_visibility:$('grade-visibility').value};
        const r=await fetch('/api/profile/me',{method:'PATCH',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify(data)});d=await r.json();if(!r.ok)throw new Error(d.detail||'Erreur');
      }
      myProfile=d;fillProfile(d);if($('me-avatar'))$('me-avatar').style.background=d.color;if($('me-status'))$('me-status').textContent=d.status_message||d.role_label||'En ligne';toast('Profil et jeux enregistrés ✓');refreshMembers();
    }catch(e){toast(e.message)}
  }

  async function openPublicProfile(userId){
    try{const r=await fetch(`/api/profiles/${userId}`,{credentials:'same-origin'});if(!r.ok)return;const p=await r.json();let pop=document.getElementById('public-profile-pop');if(pop)pop.remove();pop=document.createElement('div');pop.id='public-profile-pop';pop.className='modal-backdrop open';pop.innerHTML=`<section class="discord-modal profile-modal"><header><div><span class="eyebrow">CARTE DE PROFIL</span><h2>${escapeHtml(p.username)}</h2></div><button class="modal-close">×</button></header><div class="profile-card-preview" style="border-top-color:${escapeHtml(p.color)}"><span class="avatar avatar-xl" style="background:${escapeHtml(p.color)}">${escapeHtml(initials(p.username))}</span><div><h3>${escapeHtml(p.username)}</h3>${p.role_label?`<span class="profile-role-chip">${escapeHtml(p.role_label)}</span>`:''}<p>${escapeHtml(p.status_message||'')}</p></div></div><p>${escapeHtml(p.bio||'Aucune bio.')}</p><div class="profile-stats"><div><b>${escapeHtml(p.class_code||'—')}</b><small>CLASSE</small></div><div><b>${p.coins||0}</b><small>PICOINS</small></div><div><b>${(p.badges||[]).length}</b><small>BADGES</small></div><div><b>${(p.games||[]).length}</b><small>JEUX</small></div></div>${window.PiChatGamingProfiles?.publicSections?.(p)||''}</section>`;document.body.append(pop);pop.querySelector('.modal-close').onclick=()=>pop.remove();pop.onclick=e=>{if(e.target===pop)pop.remove()}}
    catch{}
  }

  async function askTutor(){
    const prompt=$('tutor-prompt').value.trim();if(!prompt){toast('Ajoute ton exercice ou ta question.');return}
    const data={subject:$('tutor-subject').value,mode:$('tutor-mode').value,prompt,student_answer:$('tutor-student-answer').value.trim()};$('tutor-loading').hidden=false;$('tutor-answer').hidden=true;$('tutor-send').disabled=true;
    try{const r=await fetch('/api/tutor/ask',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify(data)});const d=await r.json();if(!r.ok)throw new Error(d.detail||'PiTutor indisponible');$('tutor-answer').textContent=d.answer;$('tutor-answer').hidden=false;$('tutor-answer').dataset.provider=d.provider||'local'}catch(e){$('tutor-answer').textContent='⚠️ '+e.message;$('tutor-answer').hidden=false}finally{$('tutor-loading').hidden=true;$('tutor-send').disabled=false}
  }

  function openChannels(open=true){$('channel-panel')?.classList.toggle('open',open);$('mobile-overlay')?.classList.toggle('open',open)}
  function openMembers(open=true){if(!features.member_panel)return;$('member-panel')?.classList.toggle('open',open);$('mobile-overlay')?.classList.toggle('open',open);if(open)refreshMembers()}
  function sendOrPrefill(command,send){const input=$('message-input');if(!input)return;if(send){window.sendChatContent?.(command);closeAll()}else{input.value=command;input.focus();closeAll()}}


  async function uploadSelectedFile(){
    const input=$('file-input'),status=$('file-status');const file=input?.files?.[0];if(!file||!window.currentRoomId)return;
    if(file.size>12*1024*1024){toast('Fichier trop volumineux : maximum 12 Mo.');input.value='';return}
    const form=new FormData();form.append('file',file);if(status)status.textContent=`Envoi de ${file.name}…`;if($('file-button'))$('file-button').disabled=true;
    try{
      const r=await fetch(`/api/rooms/${window.currentRoomId}/files`,{method:'POST',credentials:'same-origin',body:form});let d={};try{d=await r.json()}catch{}
      if(!r.ok)throw new Error(d.detail||`Erreur ${r.status}`);if(status)status.textContent='Fichier envoyé ✓';setTimeout(()=>{if(status)status.textContent=''},2200);
    }catch(e){if(status)status.textContent='';toast(e.message||'Envoi impossible.')}finally{input.value='';if($('file-button'))$('file-button').disabled=false}
  }

  function bind(){
    document.querySelectorAll('.modal-backdrop').forEach(back=>{back.addEventListener('click',e=>{if(e.target===back)back.classList.remove('open')});back.querySelectorAll('.modal-close').forEach(b=>b.onclick=()=>back.classList.remove('open'))});
    $('help-button').onclick=()=>modal('help-modal');$('open-games').onclick=()=>modal('games-modal');$('open-tutor').onclick=()=>modal('tutor-modal');$('quick-tutor').onclick=()=>modal('tutor-modal');$('open-profile').onclick=async()=>{await loadMyProfile();modal('profile-modal')};$('open-gaming-profile')?.addEventListener('click',async()=>{await loadMyProfile();modal('profile-modal')});$('dock-profile-button').onclick=async()=>{await loadMyProfile();modal('profile-modal')};$('save-profile').onclick=saveProfile;
    $('tutor-send').onclick=askTutor;$('tutor-mode').onchange=()=>{$('student-answer-wrap').style.display=$('tutor-mode').value==='check'?'block':'none'};
    document.querySelectorAll('[data-game-command]').forEach(b=>b.onclick=()=>sendOrPrefill(b.dataset.gameCommand,true));document.querySelectorAll('[data-prefill]').forEach(b=>b.onclick=()=>sendOrPrefill(b.dataset.prefill,false));
    $('composer-plus').onclick=()=>modal('help-modal');$('emoji-button').onclick=e=>{const fake={currentTarget:e.currentTarget};window.showEmojiComposer?.(fake)};if($('file-button'))$('file-button').onclick=()=>$('file-input')?.click();if($('file-input'))$('file-input').onchange=uploadSelectedFile;
    $('open-channels').onclick=()=>openChannels(true);$('close-channels').onclick=()=>openChannels(false);$('toggle-members').onclick=()=>openMembers(!$('member-panel').classList.contains('open'));$('close-members').onclick=()=>openMembers(false);$('mobile-overlay').onclick=()=>{openChannels(false);openMembers(false)};
    document.querySelectorAll('#mobile-bottom-nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#mobile-bottom-nav button').forEach(x=>x.classList.remove('active'));b.classList.add('active');const a=b.dataset.mobile;if(a==='channels')openChannels(true);if(a==='chat'){openChannels(false);openMembers(false)}if(a==='tutor')modal('tutor-modal');if(a==='profile')loadMyProfile().then(()=>modal('profile-modal'))});
    const personalize=()=>{const btn=document.getElementById('ui-personalize-button');if(btn)btn.click();else document.getElementById('ui-personalize-modal')?.classList.add('open')};$('open-personalization').onclick=personalize;$('ui-personalize-inline').onclick=personalize;
    document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeAll();openChannels(false);openMembers(false)}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();modal('help-modal')}});
  }

  async function init(){await loadFeatures();bind();await loadMyProfile();await refreshMembers();setInterval(()=>{if(!document.hidden)refreshMembers()},15000)}
  window.PiChatCommunity={refreshMembers,onRoomChanged:async()=>{openChannels(false);await refreshMembers()},openPublicProfile};
  window.addEventListener('pichat:user-ready',init,{once:true});
  if(window.CURRENT_USER)init();
})();
