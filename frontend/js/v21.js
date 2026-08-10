(() => {
  const $ = id => document.getElementById(id);
  const toast = text => window.PiChatTrolls?.toast?.(text) || alert(text);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const modal = (id, open=true) => $(id)?.classList.toggle('open', open);
  const initials = name => (name || '?').slice(0,2).toUpperCase();
  let activeDM = null;
  let dmReply = null;
  let dmTimer = null;
  let latestTutorResponse = null;

  async function api(url, options={}) {
    const response = await fetch(url, {credentials:'same-origin', cache:'no-store', ...options});
    let data = null;
    try { data = await response.json(); } catch { data = {}; }
    if (!response.ok) throw new Error(data.detail || `Erreur ${response.status}`);
    return data;
  }

  // ------------------------------------------------------------------
  // Messages privés
  // ------------------------------------------------------------------
  async function openDM(userId=null) {
    modal('dm-modal');
    await Promise.all([loadDMConversations(), loadDMUsers()]);
    if (userId) await selectDM(Number(userId));
    if (!dmTimer) dmTimer = setInterval(() => {
      if ($('dm-modal')?.classList.contains('open')) {
        loadDMConversations();
        if (activeDM) loadDMHistory(activeDM.id, false);
      }
    }, 5000);
  }

  async function loadDMConversations() {
    try {
      const items = await api('/api/dm/conversations');
      const box = $('dm-conversations');
      if (!box) return;
      box.innerHTML = items.length ? '' : '<p class="muted">Aucune conversation.</p>';
      let total = 0;
      items.forEach(item => {
        total += Number(item.unread || 0);
        const b = document.createElement('button');
        b.className = 'dm-conversation' + (activeDM?.id === item.user.id ? ' active' : '');
        b.innerHTML = `<span class="avatar" style="background:${esc(item.user.profile_color)}">${esc(initials(item.user.username))}</span><span><strong>${esc(item.user.username)}</strong><small>${esc(item.last_message || 'Nouvelle conversation')}</small></span>${item.unread ? `<b>${item.unread}</b>` : ''}`;
        b.onclick = () => selectDM(item.user.id, item.user);
        box.append(b);
      });
      const badge = $('dm-unread-badge');
      if (badge) { badge.textContent = total; badge.hidden = total <= 0; }
      if (navigator.setAppBadge) navigator.setAppBadge(total || 0).catch(()=>{});
    } catch (e) { console.warn(e); }
  }

  async function loadDMUsers() {
    try {
      const users = await api('/api/dm/users');
      const q = ($('dm-user-search')?.value || '').toLowerCase();
      const box = $('dm-user-list'); if (!box) return;
      box.innerHTML = '';
      users.filter(u => !q || u.username.toLowerCase().includes(q)).forEach(u => {
        const b = document.createElement('button');
        b.className = 'dm-user-choice';
        b.innerHTML = `<span class="avatar" style="background:${esc(u.profile_color)}">${esc(initials(u.username))}</span><span><strong>${esc(u.username)}</strong><small>${esc(u.class_code || u.status_message || 'Membre')}</small></span>`;
        b.onclick = () => selectDM(u.id, u);
        box.append(b);
      });
    } catch (e) { console.warn(e); }
  }

  async function selectDM(userId, user=null) {
    if (!user) {
      const users = await api('/api/dm/users');
      user = users.find(x => Number(x.id) === Number(userId)) || {id:userId, username:'Utilisateur', profile_color:'#5865f2'};
    }
    activeDM = user;
    $('dm-empty').hidden = true; $('dm-active').hidden = false;
    $('dm-active-name').textContent = user.username;
    $('dm-active-status').textContent = user.status_message || user.class_code || 'Membre';
    $('dm-active-avatar').textContent = initials(user.username); $('dm-active-avatar').style.background = user.profile_color || '#5865f2';
    await loadDMHistory(user.id, true);
    await loadDMConversations();
  }

  async function loadDMHistory(otherId, scroll=true) {
    try {
      const data = await api(`/api/dm/${otherId}/messages?limit=100`);
      const box = $('dm-message-list'); if (!box) return;
      const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 100;
      box.innerHTML = '';
      data.messages.forEach(renderDMMessage);
      if (scroll || nearBottom) requestAnimationFrame(() => box.scrollTop = box.scrollHeight);
    } catch (e) { toast(e.message); }
  }

  function renderDMMessage(message) {
    const row = document.createElement('article');
    row.className = 'dm-message ' + (message.mine ? 'mine' : 'theirs');
    row.dataset.dmId = message.id;
    if (message.reply) {
      const reply = document.createElement('div'); reply.className = 'dm-message-reply';
      reply.textContent = `↪ ${message.reply.username}: ${message.reply.content}`; row.append(reply);
    }
    const content = document.createElement('div'); content.className = 'dm-bubble'; content.textContent = message.content; row.append(content);
    const meta = document.createElement('small'); meta.textContent = `${message.sender_username} · ${new Date(message.created_at.replace(' ','T')+'Z').toLocaleString()}${message.edited_at?' · modifié':''}`; row.append(meta);
    const actions = document.createElement('div'); actions.className = 'dm-actions';
    const replyBtn = document.createElement('button'); replyBtn.textContent = '↩'; replyBtn.title = 'Répondre'; replyBtn.onclick = () => setDMReply(message); actions.append(replyBtn);
    if (message.mine) {
      const edit = document.createElement('button'); edit.textContent = '✎'; edit.onclick = () => editDM(message); actions.append(edit);
    }
    const del = document.createElement('button'); del.textContent = '🗑'; del.onclick = () => deleteDM(message); actions.append(del);
    row.append(actions); $('dm-message-list').append(row);
  }

  function setDMReply(message) {
    dmReply = message; $('dm-reply-bar').hidden = false;
    $('dm-reply-user').textContent = message.sender_username;
    $('dm-reply-preview').textContent = message.content;
    $('dm-input').focus();
  }
  function clearDMReply() { dmReply = null; if ($('dm-reply-bar')) $('dm-reply-bar').hidden = true; }
  async function sendDM(event) {
    event.preventDefault(); if (!activeDM) return;
    const input = $('dm-input'); const content = input.value.trim(); if (!content) return;
    try {
      await api(`/api/dm/${activeDM.id}/messages`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content,reply_to_id:dmReply?.id||null})});
      input.value=''; clearDMReply(); await loadDMHistory(activeDM.id, true); await loadDMConversations();
    } catch(e) { toast(e.message); }
  }
  async function editDM(message) {
    const content = prompt('Modifier :', message.content); if (content === null || !content.trim()) return;
    try { await api(`/api/dm/messages/${message.id}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:content.trim()})}); await loadDMHistory(activeDM.id, false); } catch(e) { toast(e.message); }
  }
  async function deleteDM(message) {
    if (!confirm('Retirer ce message de ta conversation ?')) return;
    try { await api(`/api/dm/messages/${message.id}`, {method:'DELETE'}); await loadDMHistory(activeDM.id, false); await loadDMConversations(); } catch(e) { toast(e.message); }
  }

  // ------------------------------------------------------------------
  // Recherche, épingles
  // ------------------------------------------------------------------
  function resultCard(message, pinned=false) {
    const card = document.createElement('article'); card.className='search-result-card';
    card.innerHTML = `<div><strong>${esc(message.username)}</strong><small>${esc(message.created_at)}${message.edited_at?' · modifié':''}</small></div><p>${esc(message.content)}</p>`;
    const actions = document.createElement('div');
    const jump = document.createElement('button'); jump.textContent='Voir dans le salon'; jump.onclick=async()=>{modal(pinned?'pins-modal':'search-modal',false);await window.switchRoom(message.room_id);setTimeout(()=>{const el=document.querySelector(`[data-message-id="${message.id}"]`);if(el){el.scrollIntoView({behavior:'smooth',block:'center'});el.classList.add('message-focus')}} ,500)};actions.append(jump);
    card.append(actions); return card;
  }
  async function doSearch(event) {
    event.preventDefault(); const q=$('message-search-input').value.trim(); if(q.length<2)return;
    const box=$('message-search-results');box.innerHTML='<p class="muted">Recherche…</p>';
    try { const data=await api(`/api/messages/search?room_id=${window.currentRoomId}&q=${encodeURIComponent(q)}&author=${encodeURIComponent($('message-search-author').value.trim())}`);box.innerHTML='';if(!data.messages.length)box.innerHTML='<p class="muted">Aucun résultat.</p>';data.messages.forEach(m=>box.append(resultCard(m))); } catch(e){box.innerHTML=`<p class="error">${esc(e.message)}</p>`}
  }
  async function openPins(){modal('pins-modal');const box=$('pinned-message-list');box.innerHTML='<p class="muted">Chargement…</p>';try{const d=await api(`/api/rooms/${window.currentRoomId}/pins`);box.innerHTML='';if(!d.messages.length)box.innerHTML='<p class="muted">Aucun message épinglé.</p>';d.messages.forEach(m=>box.append(resultCard(m,true)))}catch(e){box.innerHTML=`<p class="error">${esc(e.message)}</p>`}}

  // ------------------------------------------------------------------
  // PiTutor+
  // ------------------------------------------------------------------
  async function askTutorPlus() {
    const promptText=$('tutor-prompt').value.trim();if(!promptText){toast('Ajoute un exercice ou un sujet.');return}
    const payload={subject:$('tutor-subject').value,mode:$('tutor-mode').value,prompt:promptText,student_answer:$('tutor-student-answer').value.trim(),difficulty:$('tutor-difficulty').value,count:Number($('tutor-count').value||5)};
    $('tutor-loading').hidden=false;$('tutor-answer').hidden=true;$('tutor-send').disabled=true;
    try{const d=await api('/api/tutor/v2/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});latestTutorResponse=d;$('tutor-answer').textContent=d.answer;$('tutor-answer').hidden=false;$('tutor-save-set').hidden=!((d.study_items||[]).length||['revision','similar'].includes(d.mode));await loadTutorData()}catch(e){$('tutor-answer').textContent='⚠️ '+e.message;$('tutor-answer').hidden=false}finally{$('tutor-loading').hidden=true;$('tutor-send').disabled=false}
  }
  async function loadTutorData(){
    try{const [dash,sets,history]=await Promise.all([api('/api/tutor/v2/dashboard'),api('/api/tutor/v2/sets'),api('/api/tutor/v2/history')]);$('tutor-dashboard').innerHTML=`<strong>Progression</strong><div class="tutor-metrics"><span><b>${dash.questions}</b> questions</span><span><b>${dash.study_sets}</b> fiches</span><span><b>${dash.attempts}</b> sessions</span><span><b>${dash.average_score}%</b> moyenne</span></div>`;renderStudySets(sets);renderTutorHistory(history.slice(0,15))}catch(e){console.warn(e)}
  }
  function renderStudySets(sets){const box=$('tutor-study-sets');box.innerHTML=sets.length?'':'<p class="muted">Aucune fiche enregistrée.</p>';sets.forEach(s=>{const a=document.createElement('article');a.innerHTML=`<div><strong>${esc(s.title)}</strong><small>${esc(s.subject)} · ${s.kind} · ${s.item_count} éléments</small></div><span>${s.best_percent||0}%</span>`;a.onclick=()=>openStudySet(s.id);box.append(a)})}
  function renderTutorHistory(items){const box=$('tutor-history');box.innerHTML=items.length?'':'<p class="muted">Aucun historique.</p>';items.forEach(h=>{const a=document.createElement('article');a.innerHTML=`<strong>${esc(h.subject)} · ${esc(h.mode)}</strong><p>${esc(h.prompt.slice(0,120))}</p><small>${esc(h.created_at)}</small>`;a.onclick=()=>{$('tutor-answer').textContent=h.tutor_answer;$('tutor-answer').hidden=false};box.append(a)})}
  async function saveTutorSet(){if(!latestTutorResponse)return;let items=latestTutorResponse.study_items||[];if(!items.length)items=[{title:latestTutorResponse.mode,content:latestTutorResponse.answer}];const title=prompt('Nom de la fiche :',`${latestTutorResponse.subject} — ${latestTutorResponse.mode}`);if(!title)return;try{await api('/api/tutor/v2/sets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,subject:latestTutorResponse.subject,kind:latestTutorResponse.mode==='quiz'?'quiz':latestTutorResponse.mode==='flashcards'?'flashcards':'notes',items})});toast('Fiche enregistrée ✓');await loadTutorData()}catch(e){toast(e.message)}}
  async function openStudySet(id){try{const s=await api(`/api/tutor/v2/sets/${id}`);const lines=(s.items||[]).map((x,i)=>x.front?`${i+1}. ${x.front}\n→ ${x.back}`:`${i+1}. ${x.question||x.title||''}\n→ ${x.answer||x.content||''}`).join('\n\n');$('tutor-answer').textContent=`${s.title}\n\n${lines}`;$('tutor-answer').hidden=false}catch(e){toast(e.message)}}

  function bind() {
    $('open-direct-messages')?.addEventListener('click',()=>openDM());$('open-dm-header')?.addEventListener('click',()=>openDM());
    $('dm-form')?.addEventListener('submit',sendDM);$('dm-user-search')?.addEventListener('input',loadDMUsers);$('dm-cancel-reply')?.addEventListener('click',clearDMReply);
    $('open-search')?.addEventListener('click',()=>modal('search-modal'));$('message-search-form')?.addEventListener('submit',doSearch);$('open-pins')?.addEventListener('click',openPins);
    if($('tutor-send'))$('tutor-send').onclick=askTutorPlus;$('tutor-save-set')?.addEventListener('click',saveTutorSet);$('tutor-refresh-sets')?.addEventListener('click',loadTutorData);$('tutor-mode')?.addEventListener('change',()=>{$('student-answer-wrap').style.display=$('tutor-mode').value==='check'?'block':'none'});
    $('open-tutor')?.addEventListener('click',loadTutorData);$('quick-tutor')?.addEventListener('click',loadTutorData);
    window.addEventListener('pichat:dm-event',event=>{loadDMConversations();if(activeDM && Number(event.detail.message?.other_user_id)===Number(activeDM.id))loadDMHistory(activeDM.id,false);else toast(`Nouveau message privé de ${event.detail.message?.sender_username||'quelqu’un'}`)});
    document.querySelectorAll('#dm-modal .modal-close').forEach(b=>b.addEventListener('click',()=>modal('dm-modal',false)));
  }

  document.addEventListener('DOMContentLoaded', bind);
  window.PiChatV21={openDM,loadTutorData};
})();
