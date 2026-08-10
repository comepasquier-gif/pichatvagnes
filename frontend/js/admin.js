let requests=[],rooms=[],users=[],bots=[],aiSettings=null,auditLogs=[],profanitySettings=null,uiSettings=null,featureSettings=null,reports=[],automodSettings=null,automodIncidents=[];
const $=id=>document.getElementById(id);
function token(){return document.cookie.split(';').map(x=>x.trim()).find(x=>x.startsWith(''))}
async function api(url,options={}){const r=await fetch(url,{credentials:'same-origin',...options});if(!r.ok){let d={};try{d=await r.json()}catch{};throw new Error(d.detail||`Erreur ${r.status}`)}if(r.status===204)return null;return r.json()}
function msg(text,ok=false){const e=$(ok?'success-message':'error-message');e.textContent=text;e.classList.add('visible');setTimeout(()=>e.classList.remove('visible'),3500)}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
document.addEventListener('DOMContentLoaded',async()=>{try{const me=await api('/api/me');if(!me.is_admin){location.href='/';return}startAdminPresence();bindNav();bindForms();restoreSimpleMode();await refreshAll();const tab=location.hash.replace('#','');if(tab&&document.querySelector(`.nav-item[data-tab="${tab}"]`))openTab(tab,document.querySelector(`.nav-item[data-tab="${tab}"]`).textContent.trim())}catch{location.href='/login'}});
function bindNav(){document.querySelectorAll('.nav-item').forEach(b=>b.onclick=()=>openTab(b.dataset.tab,b.textContent.trim()));$('refresh-all').onclick=refreshAll;$('simple-mode').onchange=()=>{localStorage.setItem('pichat-simple',$('simple-mode').checked?'1':'0');applySimple()};$('request-filter').onchange=loadRequests;$('request-select-all').onchange=e=>document.querySelectorAll('.request-check').forEach(c=>c.checked=e.target.checked);$('bulk-approve').onclick=()=>bulkRequests('approve');$('bulk-reject').onclick=()=>bulkRequests('reject');$('user-role-filter').onchange=renderUsers;$('refresh-audit').onclick=loadAudit;if($('refresh-reports'))$('refresh-reports').onclick=loadReports;if($('refresh-automod'))$('refresh-automod').onclick=loadAutoModIncidents;if($('automod-incident-filter'))$('automod-incident-filter').onchange=loadAutoModIncidents}
function startAdminPresence(){const ping=()=>fetch('/api/presence/admin',{method:'POST',credentials:'same-origin',keepalive:true}).catch(()=>{});ping();const timer=setInterval(ping,15000);window.addEventListener('pagehide',()=>{clearInterval(timer);try{navigator.sendBeacon('/api/presence/admin/leave',new Blob(['{}'],{type:'application/json'}))}catch{fetch('/api/presence/admin/leave',{method:'POST',credentials:'same-origin',keepalive:true}).catch(()=>{})}})}
function openTab(name,title){document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.tab===name));document.querySelectorAll('.tab-panel').forEach(x=>x.classList.toggle('active',x.dataset.panel===name));$('page-title').textContent=title.replace(/\d+$/,'').trim();history.replaceState(null,'','#'+name);if(name==='backups')window.PiChatBackupStudio?.load()}
function restoreSimpleMode(){$('simple-mode').checked=localStorage.getItem('pichat-simple')==='1';applySimple()}function applySimple(){document.body.classList.toggle('simple-active',$('simple-mode').checked);if($('simple-mode').checked){const active=document.querySelector('.nav-item.active');if(active&&active.classList.contains('advanced-only'))openTab('overview',"Vue d'ensemble")}}
function bindForms(){$('create-room-form').onsubmit=createRoom;$('create-bot-form').onsubmit=createBot;$('user-search').oninput=renderUsers;$('terminal-form').onsubmit=e=>{e.preventDefault();runConsole($('terminal-input').value)};document.querySelectorAll('[data-cmd]').forEach(b=>b.onclick=()=>runConsole(b.dataset.cmd));if($('terminal-copy-all'))$('terminal-copy-all').onclick=copyWholeConsole;if($('terminal-copy-users'))$('terminal-copy-users').onclick=copyUserCommandExamples;if($('terminal-download'))$('terminal-download').onclick=downloadConsoleHistory;if($('terminal-clear-button'))$('terminal-clear-button').onclick=()=>runConsole('clear');if($('ai-form'))$('ai-form').onsubmit=saveAI;if($('profanity-form'))$('profanity-form').onsubmit=saveProfanity;if($('ui-settings-form'))$('ui-settings-form').onsubmit=saveUISettings;if($('ui-reset'))$('ui-reset').onclick=resetUISettings;if($('features-form'))$('features-form').onsubmit=saveFeatures;if($('automod-form'))$('automod-form').onsubmit=saveAutoMod;['ui-app-name','ui-app-subtitle','ui-logo-text','ui-theme-preset','ui-primary-color','ui-secondary-color','ui-accent-color'].forEach(id=>{const el=$(id);if(el)el.addEventListener('input',renderUIPreview)})}
async function refreshAll(){try{const h=await api('/api/health');$('version-chip').textContent=`PiChat ${h.version}`;[requests,rooms,users,bots,aiSettings,profanitySettings,auditLogs,uiSettings,featureSettings,reports,automodSettings,automodIncidents]=await Promise.all([api('/api/admin/registration-requests?status_filter='+encodeURIComponent($('request-filter').value)),api('/api/rooms'),api('/api/admin/users'),api('/api/admin/bots'),api('/api/admin/ai'),api('/api/admin/moderation-settings'),api('/api/admin/audit?limit=120'),api('/api/admin/ui-settings'),api('/api/admin/features'),api('/api/admin/reports'),api('/api/admin/automod'),api('/api/admin/automod/incidents?status='+encodeURIComponent(($('automod-incident-filter')?.value)||'open'))]);renderAll()}catch(e){msg(e.message)}}
async function loadRequests(){try{requests=await api('/api/admin/registration-requests?status_filter='+encodeURIComponent($('request-filter').value));renderRequests()}catch(e){msg(e.message)}}
async function loadAudit(){try{auditLogs=await api('/api/admin/audit?limit=120');renderAudit()}catch(e){msg(e.message)}}
function renderAll(){renderRequests();renderRooms();renderUsers();renderBots();renderAI();renderProfanity();renderAudit();renderUISettings();renderFeatures();renderReports();renderAutoMod();$('pending-count').textContent=requests.filter(x=>x.status==='pending').length;$('stat-users').textContent=users.filter(u=>!u.is_bot).length;$('stat-pending').textContent=requests.filter(x=>x.status==='pending').length;$('stat-mods').textContent=users.filter(u=>u.role==='moderator').length;$('stat-rooms').textContent=rooms.length;$('overview-list').innerHTML=`<div class="overview-item"><span>Comptes bannis</span><strong>${users.filter(u=>u.is_banned).length}</strong></div><div class="overview-item"><span>PiAI</span><strong>${aiSettings&&aiSettings.enabled?aiSettings.provider.toUpperCase():'OFF'}</strong></div><div class="overview-item"><span>AutoModo</span><strong>${automodSettings&&automodSettings.enabled?'ON':'OFF'}</strong></div><div class="overview-item"><span>Incidents à revoir</span><strong>${automodIncidents.filter(x=>x.status==='open').length}</strong></div><div class="overview-item"><span>Classes actives</span><strong>${new Set(users.map(u=>u.class_code).filter(Boolean)).size}</strong></div><div class="overview-item"><span>Filtre gros mots</span><strong>${profanitySettings&&profanitySettings.enabled?'ON':'OFF'}</strong></div>`}
function renderRequests(){const body=$('requests-table-body');body.innerHTML=requests.length?'':'<tr><td colspan="6" class="muted">Aucune demande.</td></tr>';requests.forEach(x=>{const tr=document.createElement('tr');const pending=x.status==='pending';tr.innerHTML=`<td>${pending?'<input class="request-check" type="checkbox" data-id="'+x.id+'">':''}</td><td><strong>${esc(x.username)}</strong></td><td><span class="class-badge">${esc(x.class_code)}</span></td><td><span class="state-badge ${x.status==='rejected'?'state-banned':'state-active'}">${esc(x.status)}</span></td><td>${esc(x.created_at)}</td><td class="action-row"></td>`;if(pending)tr.lastElementChild.append(btn('Accepter','mini good',()=>approve(x)),btn('Refuser','mini bad',()=>rejectReq(x)));body.append(tr)})}
async function approve(x){if(!confirm(`Accepter ${x.username} en ${x.class_code} ?`))return;try{await api(`/api/admin/registration-requests/${x.id}/approve`,{method:'POST'});msg('Compte accepté.',true);await refreshAll()}catch(e){msg(e.message)}}
async function rejectReq(x){const note=prompt('Motif du refus (facultatif) :','');if(note===null)return;try{await api(`/api/admin/registration-requests/${x.id}/reject`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({note})});msg('Demande refusée.',true);await refreshAll()}catch(e){msg(e.message)}}
async function bulkRequests(action){const ids=[...document.querySelectorAll('.request-check:checked')].map(x=>Number(x.dataset.id));if(!ids.length){msg('Sélectionne au moins une demande.');return}let note='';if(action==='reject'){note=prompt('Motif commun du refus (facultatif) :','');if(note===null)return}if(!confirm(`${action==='approve'?'Accepter':'Refuser'} ${ids.length} demande(s) ?`))return;let ok=0,fail=0;for(const id of ids){try{await api(`/api/admin/registration-requests/${id}/${action}`,{method:'POST',headers:action==='reject'?{'Content-Type':'application/json'}:{},body:action==='reject'?JSON.stringify({note}):undefined});ok++}catch{fail++}}msg(`${ok} traitée(s)${fail?`, ${fail} erreur(s)`:''}.`,fail===0);await refreshAll()}
function roleClass(u){return u.role==='admin'?'role-badge role-admin':u.role==='moderator'?'role-badge role-mod':'role-badge role-user'}
function renderUsers(){const q=$('user-search').value.trim().toLowerCase(),filter=$('user-role-filter').value,body=$('users-table-body');body.innerHTML='';users.filter(u=>{if(q&&!u.username.toLowerCase().includes(q)&&!(u.class_code||'').toLowerCase().includes(q))return false;if(filter==='banned')return u.is_banned;if(filter!=='all'&&u.role!==filter)return false;return true}).forEach(u=>{const tr=document.createElement('tr');const label=u.grade_title||u.role_label;tr.innerHTML=`<td><strong>${esc(u.username)}</strong>${u.grade_title?`<small class="custom-grade" style="--grade:${esc(u.grade_color||'#7c5cff')}">${esc(u.grade_title)}</small>`:''}</td><td>${u.class_code?`<span class="class-badge">${esc(u.class_code)}</span>`:'—'}</td><td><span class="${roleClass(u)}">${esc(u.is_bot?'BOT':label)}</span>${u.role==='moderator'?`<small class="permission-count">${esc(packLabel(u.moderator_pack))} · ${(u.moderator_permissions||[]).length} permission(s)</small>`:''}</td><td><span class="state-badge ${u.is_banned?'state-banned':'state-active'}">${u.is_banned?'Banni':'Actif'}</span></td><td class="action-row"></td>`;const td=tr.lastElementChild;if(!u.is_bot){td.append(btn('Grade','mini brand',()=>changeRole(u)),btn('Grade perso','mini',()=>changeBadge(u)),btn('Badges','mini good',()=>window.PiChatAdminBadges?.openForUser?.(u.id)));if(!u.is_admin){td.append(btn('Classe','mini',()=>changeClass(u)),btn('Assistance','mini brand',()=>createSupportAccess(u)),btn('Expulser','mini',()=>kick(u)),btn('Reset MDP','mini brand',()=>resetPassword(u)),btn(u.is_banned?'Débannir':'Bannir',u.is_banned?'mini good':'mini bad',()=>u.is_banned?unban(u):ban(u)),btn('Supprimer','mini bad',()=>deleteUser(u)))}}else td.textContent='Bot';body.append(tr)})}
async function changeRole(u){let v=prompt(`Nouveau grade de ${u.username}:\nplayer = JOUEUR\nmoderator = MODO\nadmin = ADMIN`,u.role||'player');if(v===null)return;v=v.trim().toLowerCase();if(!['player','moderator','admin'].includes(v)){msg('Grade invalide.');return}let class_code=null;if(v==='moderator'){class_code=prompt('Classe du modo :',u.moderator_class_code||u.class_code||'');if(class_code===null||!class_code.trim())return}try{await api(`/api/admin/users/${u.id}/role`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({role:v,class_code:class_code?class_code.toUpperCase():null})});msg('Grade modifié. Le compte devra se reconnecter.',true);await refreshAll()}catch(e){msg(e.message)}}
async function changeBadge(u){const title=prompt('Nom du badge personnalisé (vide = grade normal) :',u.grade_title||'');if(title===null)return;let color=u.grade_color||'#7c5cff';if(title.trim()){color=prompt('Couleur du badge (#RRGGBB) :',color);if(color===null)return}try{await api(`/api/admin/users/${u.id}/badge`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:title.trim(),color:title.trim()?color.trim():''})});msg('Badge mis à jour.',true);await refreshAll()}catch(e){msg(e.message)}}
async function changeClass(u){const c=prompt(`Classe de ${u.username}:`,u.class_code||'');if(c===null||!c.trim())return;try{await api(`/api/admin/users/${u.id}/class`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({class_code:c.trim().toUpperCase()})});msg('Classe modifiée.',true);await refreshAll()}catch(e){msg(e.message)}}
async function kick(u){if(!confirm(`Expulser ${u.username} maintenant ? Il pourra se reconnecter.`))return;try{await api(`/api/admin/users/${u.id}/kick`,{method:'POST'});msg(`${u.username} a été expulsé.`,true);await refreshAll()}catch(e){msg(e.message)}}
async function resetPassword(u){if(!confirm(`Réinitialiser le mot de passe de ${u.username} ? Il sera déconnecté.`))return;try{const r=await api(`/api/admin/users/${u.id}/reset-password`,{method:'POST'});const text=`Nouveau mot de passe temporaire de ${u.username}:\n\n${r.temporary_password}\n\nCopie-le maintenant : il ne sera plus affiché.`;alert(text);try{await navigator.clipboard.writeText(r.temporary_password);msg('Mot de passe temporaire copié.',true)}catch{msg('Mot de passe réinitialisé.',true)}await refreshAll()}catch(e){msg(e.message)}}
async function deleteUser(u){if(!confirm(`SUPPRIMER définitivement ${u.username} ? Ses messages liés seront supprimés. Cette action est irréversible.`))return;const check=prompt(`Tape exactement ${u.username} pour confirmer :`,'');if(check!==u.username)return;try{await api(`/api/admin/users/${u.id}`,{method:'DELETE'});msg('Compte supprimé.',true);await refreshAll()}catch(e){msg(e.message)}}
async function ban(u){const reason=prompt(`Motif du ban de ${u.username}:`,'');if(reason===null)return;try{await api(`/api/admin/users/${u.id}/ban`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason})});msg('Compte expulsé et banni.',true);await refreshAll()}catch(e){msg(e.message)}}async function unban(u){try{await api(`/api/admin/users/${u.id}/unban`,{method:'POST'});msg('Compte débanni.',true);await refreshAll()}catch(e){msg(e.message)}}
function renderProfanity(){if(!profanitySettings)return;$('profanity-enabled').checked=!!profanitySettings.enabled;$('profanity-words').value=profanitySettings.words_text||''}
async function saveProfanity(e){e.preventDefault();try{profanitySettings=await api('/api/admin/moderation-settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:$('profanity-enabled').checked,words:$('profanity-words').value})});renderProfanity();msg('Filtre enregistré.',true)}catch(e2){msg(e2.message)}}
function renderAudit(){const body=$('audit-table-body');body.innerHTML=auditLogs.length?'':'<tr><td colspan="5" class="muted">Aucune action enregistrée.</td></tr>';auditLogs.forEach(x=>{const tr=document.createElement('tr');tr.innerHTML=`<td>${esc(x.created_at)}</td><td>${esc(x.actor||'système')}</td><td><span class="audit-action">${esc(x.action)}</span></td><td>${esc(x.target||'—')}</td><td>${esc(x.details||'')}</td>`;body.append(tr)})}
function renderRooms(){const body=$('rooms-table-body');body.innerHTML='';rooms.forEach(r=>{const tr=document.createElement('tr');tr.innerHTML=`<td><strong>${esc(r.name)}</strong></td><td>${r.class_code?`<span class="class-badge">${esc(r.class_code)}</span>`:'Commun'}</td><td>${esc(r.created_at)}</td><td class="action-row"></td>`;tr.lastElementChild.append(btn('Supprimer','mini bad',()=>delRoom(r)));body.append(tr)})}async function createRoom(e){e.preventDefault();const name=$('room-name-input').value.trim(),class_code=$('room-class-input').value.trim().toUpperCase()||null;try{await api('/api/admin/rooms',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,class_code})});$('room-name-input').value='';$('room-class-input').value='';msg('Serveur créé.',true);await refreshAll()}catch(e2){msg(e2.message)}}async function delRoom(r){if(!confirm(`Supprimer ${r.name} ?`))return;try{await api(`/api/admin/rooms/${r.id}`,{method:'DELETE'});await refreshAll()}catch(e){msg(e.message)}}
function renderBots(){const list=$('bots-list');list.innerHTML=bots.length?'':'<p class="muted">Aucun bot.</p>';bots.forEach(b=>{const c=document.createElement('div');c.className='bot-card'+(b.enabled?'':' disabled');c.innerHTML=`<strong>${esc(b.name)}</strong><p>${esc(b.response_template)}</p><div class="action-row"></div>`;c.lastElementChild.append(btn(b.enabled?'Désactiver':'Activer','mini',()=>toggleBot(b)),btn('Supprimer','mini bad',()=>delBot(b)));list.append(c)})}async function createBot(e){e.preventDefault();try{await api('/api/admin/bots',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('bot-name-input').value.trim(),response_template:$('bot-response-input').value.trim()})});await refreshAll()}catch(e2){msg(e2.message)}}async function toggleBot(b){try{await api(`/api/admin/bots/${b.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:!b.enabled})});await refreshAll()}catch(e){msg(e.message)}}async function delBot(b){if(!confirm(`Supprimer ${b.name} ?`))return;try{await api(`/api/admin/bots/${b.id}`,{method:'DELETE'});await refreshAll()}catch(e){msg(e.message)}}
function renderAI(){if(!aiSettings||!$('ai-form'))return;$('ai-enabled').checked=!!aiSettings.enabled;$('ai-provider').value=aiSettings.provider;$('ai-model').value=aiSettings.model;$('ai-trigger').value=aiSettings.trigger_name;$('ai-instructions').value=aiSettings.instructions;$('ai-key-chip').textContent='Clé : '+(aiSettings.api_key_configured?'configurée ✓':'absente')}
async function saveAI(e){e.preventDefault();try{aiSettings=await api('/api/admin/ai',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:$('ai-enabled').checked,provider:$('ai-provider').value,model:$('ai-model').value.trim(),trigger_name:$('ai-trigger').value.trim(),instructions:$('ai-instructions').value.trim()})});renderAI();msg('Configuration PiAI enregistrée.',true)}catch(e2){msg(e2.message)}}
const USER_COMMAND_EXAMPLES=`COMMANDES UTILISATEURS PICHAT

# Créer un utilisateur avec mot de passe choisi
create-user toto 5C totototo

# Même commande en version explicite
create-user user toto class 5C password totototo

# Créer un utilisateur avec mot de passe temporaire généré par PiChat
create-user toto 5C

# Afficher tous les utilisateurs
users

# Voir le profil administratif d'un utilisateur
user toto

# Changer sa classe
class toto 6C

# Le passer modérateur de classe
role toto moderator 5C

# Le passer administrateur
role toto admin

# Réinitialiser son mot de passe
reset-password toto

COMMANDES TERMINAL MAC
cd ~/Downloads/PiChat
source venv/bin/activate
python create_user.py toto 5C totototo
python create_user.py user toto class 5C password totototo
`;
function setConsoleCopyState(message){const state=$('terminal-copy-state');if(!state)return;state.textContent=message;clearTimeout(setConsoleCopyState.timer);setConsoleCopyState.timer=setTimeout(()=>state.textContent='',2200)}
async function copyTextToClipboard(text){try{await navigator.clipboard.writeText(text);return true}catch(_){const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.opacity='0';document.body.appendChild(area);area.select();const ok=document.execCommand('copy');area.remove();return ok}}
async function copyWholeConsole(){const out=$('terminal-output');const pending=($('terminal-input')?.value||'').trim();let text=out?.textContent||'';if(pending)text+=`\nadmin@pichat:~$ ${pending}\n`;text+=`\n\n${USER_COMMAND_EXAMPLES}`;const ok=await copyTextToClipboard(text);setConsoleCopyState(ok?'Tout copié ✓':'Copie impossible')}
async function copyUserCommandExamples(){const ok=await copyTextToClipboard(USER_COMMAND_EXAMPLES);setConsoleCopyState(ok?'Commandes utilisateurs copiées ✓':'Copie impossible')}
function downloadConsoleHistory(){const out=$('terminal-output');const pending=($('terminal-input')?.value||'').trim();let text=out?.textContent||'';if(pending)text+=`\nadmin@pichat:~$ ${pending}\n`;text+=`\n\n${USER_COMMAND_EXAMPLES}`;const blob=new Blob([text],{type:'text/plain;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`pichat-console-${new Date().toISOString().replace(/[:.]/g,'-')}.txt`;document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);setConsoleCopyState('Fichier .txt créé ✓')}
async function runConsole(command){command=(command||'').trim();if(!command)return;const out=$('terminal-output');out.textContent+=`\nadmin@pichat:~$ ${command}\n`;$('terminal-input').value='';try{const r=await api('/api/admin/console',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command})});if(r.output==='__CLEAR__')out.textContent='';else out.textContent+=r.output+'\n';out.scrollTop=out.scrollHeight}catch(e){out.textContent+='ERREUR: '+e.message+'\n'}}function btn(text,cls,fn){const b=document.createElement('button');b.type='button';b.className=cls;b.textContent=text;b.onclick=fn;return b}


async function loadAutoModIncidents(){
  try{automodIncidents=await api('/api/admin/automod/incidents?status='+encodeURIComponent(($('automod-incident-filter')?.value)||'open'));renderAutoMod()}catch(e){msg(e.message)}
}
function renderAutoMod(){
  if(automodSettings&&$('automod-form')){
    $('automod-enabled').checked=!!automodSettings.enabled;
    $('automod-announce').checked=!!automodSettings.announce_actions;
    $('automod-exempt-staff').checked=!!automodSettings.exempt_staff;
    $('automod-profanity-mode').value=automodSettings.profanity_mode||'blur';
    $('automod-link-mode').value=automodSettings.link_mode||'warn';
    $('automod-max-links').value=automodSettings.max_links??2;
    $('automod-max-mentions').value=automodSettings.max_mentions??5;
    $('automod-warn-points').value=automodSettings.warn_points??1;
    $('automod-mute-points').value=automodSettings.mute_points??4;
    $('automod-mute-minutes').value=automodSettings.mute_minutes??10;
    $('automod-ban-points').value=automodSettings.temp_ban_points??8;
    $('automod-ban-minutes').value=automodSettings.temp_ban_minutes??60;
    $('automod-window').value=automodSettings.point_window_minutes??1440;
  }
  if($('automod-count'))$('automod-count').textContent=automodIncidents.filter(x=>x.status==='open').length;
  const body=$('automod-incidents-body');if(!body)return;
  body.innerHTML=automodIncidents.length?'':'<tr><td colspan="7" class="muted">Aucun incident AutoModo.</td></tr>';
  automodIncidents.forEach(x=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${esc(x.created_at)}</td><td><strong>${esc(x.username)}</strong><small>${esc(x.class_code||'')}</small></td><td>${esc(x.room_name||'—')}</td><td><span class="automod-rule">${esc(x.rule)}</span></td><td><span class="automod-points">+${Number(x.points||0)}</span></td><td>${esc(x.detail||x.content_preview||'—')}</td><td class="action-row"></td>`;
    const actions=tr.lastElementChild;
    if(x.status==='open')actions.append(btn('Valider','mini good',()=>reviewAutoMod(x,'resolved')),btn('Ignorer','mini',()=>reviewAutoMod(x,'ignored')),btn('Reset points','mini bad',()=>resetAutoModPoints(x)));
    else actions.textContent=x.status;
    body.append(tr);
  });
}
async function saveAutoMod(e){
  e.preventDefault();
  const data={enabled:$('automod-enabled').checked,announce_actions:$('automod-announce').checked,exempt_staff:$('automod-exempt-staff').checked,profanity_mode:$('automod-profanity-mode').value,link_mode:$('automod-link-mode').value,max_links:Number($('automod-max-links').value),max_mentions:Number($('automod-max-mentions').value),warn_points:Number($('automod-warn-points').value),mute_points:Number($('automod-mute-points').value),mute_minutes:Number($('automod-mute-minutes').value),temp_ban_points:Number($('automod-ban-points').value),temp_ban_minutes:Number($('automod-ban-minutes').value),point_window_minutes:Number($('automod-window').value)};
  try{automodSettings=await api('/api/admin/automod',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});renderAutoMod();msg('AutoModo enregistré.',true)}catch(e2){msg(e2.message)}
}
async function reviewAutoMod(x,status){
  const note=prompt(status==='ignored'?'Pourquoi ignorer cet incident ?':'Note de validation (facultative) :','');if(note===null)return;
  try{await api(`/api/admin/automod/incidents/${x.id}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status,note})});msg('Incident mis à jour.',true);await loadAutoModIncidents()}catch(e){msg(e.message)}
}
async function resetAutoModPoints(x){
  if(!confirm(`Remettre à zéro les points AutoModo de ${x.username} ?`))return;
  try{await api(`/api/admin/automod/users/${x.user_id}/reset-points`,{method:'POST'});msg('Points AutoModo remis à zéro.',true);await loadAutoModIncidents()}catch(e){msg(e.message)}
}


function renderUISettings(){
  if(!uiSettings||!$('ui-settings-form'))return;
  $('ui-app-name').value=uiSettings.app_name||'PiChat';
  $('ui-app-subtitle').value=uiSettings.app_subtitle||'';
  $('ui-logo-text').value=uiSettings.logo_text||'P';
  $('ui-theme-preset').value=uiSettings.theme_preset||'neon';
  $('ui-primary-color').value=uiSettings.primary_color||'#7c5cff';
  $('ui-secondary-color').value=uiSettings.secondary_color||'#37b5ff';
  $('ui-accent-color').value=uiSettings.accent_color||'#22d3a6';
  $('ui-density').value=uiSettings.density||'comfortable';
  $('ui-welcome').value=uiSettings.welcome_message||'';
  $('ui-show-bot-hint').checked=!!uiSettings.show_bot_hint;
  $('ui-show-diagnostic').checked=!!uiSettings.show_diagnostic;
  renderUIPreview();
  if(window.PiChatUI)window.PiChatUI.applyGlobal(uiSettings);
}
function renderUIPreview(){
  if(!$('ui-preview-name'))return;
  $('ui-preview-name').textContent=$('ui-app-name').value||'PiChat';
  $('ui-preview-subtitle').textContent=$('ui-app-subtitle').value||'';
  $('ui-preview-logo').textContent=$('ui-logo-text').value||'P';
  $('ui-preview-theme').textContent=$('ui-theme-preset').value;
  $('ui-preview-logo').style.background=`linear-gradient(135deg,${$('ui-primary-color').value},${$('ui-secondary-color').value})`;
}
async function saveUISettings(e){
  e.preventDefault();
  const data={app_name:$('ui-app-name').value.trim(),app_subtitle:$('ui-app-subtitle').value.trim(),welcome_message:$('ui-welcome').value.trim(),logo_text:$('ui-logo-text').value.trim(),theme_preset:$('ui-theme-preset').value,primary_color:$('ui-primary-color').value,secondary_color:$('ui-secondary-color').value,accent_color:$('ui-accent-color').value,density:$('ui-density').value,show_bot_hint:$('ui-show-bot-hint').checked,show_diagnostic:$('ui-show-diagnostic').checked};
  try{uiSettings=await api('/api/admin/ui-settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});renderUISettings();msg('Personnalisation enregistrée.',true)}catch(e2){msg(e2.message)}
}
async function resetUISettings(){
  if(!confirm('Réinitialiser le style global de PiChat ?'))return;
  try{uiSettings=await api('/api/admin/ui-settings/reset',{method:'POST'});renderUISettings();msg('Style réinitialisé.',true)}catch(e){msg(e.message)}
}

async function loadReports(){try{reports=await api('/api/admin/reports');renderReports()}catch(e){msg(e.message)}}
function renderReports(){const body=$('reports-table-body');if(!body)return;body.innerHTML=reports.length?'':'<tr><td colspan="5" class="muted">Aucun signalement.</td></tr>';reports.forEach(x=>{const tr=document.createElement('tr');tr.innerHTML=`<td>${esc(x.created_at)}</td><td><strong>${esc(x.author)}</strong></td><td>${esc(x.reporter)}</td><td>${esc(x.reason||'—')}</td><td>${esc((x.content||'').slice(0,160))}</td>`;body.append(tr)})}
function renderFeatures(){if(!featureSettings||!$('features-form'))return;$('feature-games').checked=!!featureSettings.games_enabled;$('feature-tutor').checked=!!featureSettings.tutor_enabled;$('feature-reactions').checked=!!featureSettings.reactions_enabled;$('feature-reports').checked=!!featureSettings.reports_enabled;$('feature-members').checked=!!featureSettings.member_panel;$('feature-pycoins').checked=!!featureSettings.pycoins_enabled;$('feature-custom-servers').checked=!!featureSettings.custom_servers_enabled;$('feature-code-lab').checked=!!featureSettings.code_lab_enabled;$('feature-support-access').checked=!!featureSettings.support_access_enabled;if($('feature-dm'))$('feature-dm').checked=!!featureSettings.direct_messages_enabled;if($('feature-edit'))$('feature-edit').checked=!!featureSettings.message_edit_enabled;if($('feature-pins'))$('feature-pins').checked=!!featureSettings.pins_enabled;if($('feature-search'))$('feature-search').checked=!!featureSettings.search_enabled;if($('feature-tutor-plus'))$('feature-tutor-plus').checked=!!featureSettings.tutor_plus_enabled;if($('feature-gaming'))$('feature-gaming').checked=!!featureSettings.gaming_profiles_enabled;if($('feature-arcade'))$('feature-arcade').checked=!!featureSettings.arcade_enabled;if($('feature-game-studio'))$('feature-game-studio').checked=!!featureSettings.game_studio_enabled;if($('feature-internet'))$('feature-internet').checked=!!featureSettings.internet_mode_enabled}
async function saveFeatures(e){e.preventDefault();try{featureSettings=await api('/api/admin/features',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({games_enabled:$('feature-games').checked,tutor_enabled:$('feature-tutor').checked,reactions_enabled:$('feature-reactions').checked,reports_enabled:$('feature-reports').checked,member_panel:$('feature-members').checked,pycoins_enabled:$('feature-pycoins').checked,custom_servers_enabled:$('feature-custom-servers').checked,code_lab_enabled:$('feature-code-lab').checked,support_access_enabled:$('feature-support-access').checked,direct_messages_enabled:$('feature-dm')?.checked??true,message_edit_enabled:$('feature-edit')?.checked??true,pins_enabled:$('feature-pins')?.checked??true,search_enabled:$('feature-search')?.checked??true,tutor_plus_enabled:$('feature-tutor-plus')?.checked??true,rpg_enabled:false,gaming_profiles_enabled:$('feature-gaming')?.checked??true,arcade_enabled:$('feature-arcade')?.checked??true,game_studio_enabled:$('feature-game-studio')?.checked??true,internet_mode_enabled:$('feature-internet')?.checked??false})});renderFeatures();msg('Fonctions enregistrées.',true)}catch(e2){msg(e2.message)}}

async function createSupportAccess(u){
  const reason=prompt(`Motif de l’accès assistance pour ${u.username} :`,'Aide technique');if(reason===null)return;
  try{const d=await api(`/api/admin/users/${u.id}/support-link`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason,validity_minutes:5})});
    const url=d.absolute_url||d.url;
    try{await navigator.clipboard.writeText(url)}catch{}
    if(confirm(`Lien unique créé pour ${u.username}.\nValable jusqu’à ${d.expires_at}.\n\nOuvrir maintenant en mode assistance ?`)){location.href=d.url}else msg('Lien d’assistance copié. Il ne fonctionne qu’une fois et avec ton compte admin.',true);
  }catch(e){msg(e.message)}
}

/* PiChat 1.1.3 — éditeur de grade et permissions de modo */
let modoEditorUser=null;
let modoPermissionCatalog=[];
let modoPackCatalog=[];
let selectedModoPack="custom";
const DEFAULT_MODO_PERMS=['reports_view','reports_resolve','messages_delete','users_warn','users_mute','users_kick','users_tempban','notes_manage','history_view','slowmode_manage'];
async function ensureModoPermissionCatalog(){
  if(modoPermissionCatalog.length)return modoPermissionCatalog;
  try{const d=await api('/api/admin/moderator-permissions');modoPermissionCatalog=d.permissions||[];modoPackCatalog=d.packs||[]}catch(e){msg(e.message)}
  return modoPermissionCatalog;
}
function packLabel(key){const p=modoPackCatalog.find(x=>x.key===key);if(p)return p.label;return ({small:'Petit modo',standard:'Modo normal',super:'Super modo',custom:'Personnalisé'})[key]||'Personnalisé'}
function detectModoPackFromChecks(){
  const selected=[...document.querySelectorAll('#modo-editor-permissions input:checked')].map(x=>x.value).sort();
  const pack=modoPackCatalog.find(p=>[...(p.permissions||[])].sort().join('|')===selected.join('|'));
  selectModoPack(pack?pack.key:'custom',false);
}
function selectModoPack(key,applyPermissions=true){
  selectedModoPack=key||'custom';
  document.querySelectorAll('.modo-pack-card').forEach(card=>card.classList.toggle('active',card.dataset.pack===selectedModoPack));
  const current=$('modo-editor-pack-current');if(current){current.textContent=selectedModoPack==='custom'?'PERSONNALISÉ':packLabel(selectedModoPack).toUpperCase();current.dataset.pack=selectedModoPack}
  if(applyPermissions&&selectedModoPack!=='custom'){
    const pack=modoPackCatalog.find(x=>x.key===selectedModoPack);if(pack)renderModoPermissions(pack.permissions||[]);
  }
}
function renderModoPacks(selected){
  const box=$('modo-editor-packs');if(!box)return;box.innerHTML='';
  modoPackCatalog.forEach(pack=>{const button=document.createElement('button');button.type='button';button.className='modo-pack-card';button.dataset.pack=pack.key;button.style.setProperty('--pack-color',pack.color||'#5865f2');button.innerHTML=`<span class="modo-pack-icon">${pack.key==='small'?'🟢':pack.key==='standard'?'🔵':'🟣'}</span><span><strong>${esc(pack.label)}</strong><small>${esc(pack.description)}</small><em>${pack.permission_count} permissions</em></span>`;button.onclick=()=>selectModoPack(pack.key,true);box.append(button)});
  const custom=document.createElement('button');custom.type='button';custom.className='modo-pack-card custom-pack';custom.dataset.pack='custom';custom.innerHTML='<span class="modo-pack-icon">⚙️</span><span><strong>Personnalisé</strong><small>Choisis chaque possibilité manuellement.</small><em>Sur mesure</em></span>';custom.onclick=()=>selectModoPack('custom',false);box.append(custom);
  selectModoPack(selected||'custom',false);
}
function closeModoEditor(){const b=$('modo-editor-backdrop');if(b){b.classList.remove('open');b.setAttribute('aria-hidden','true')}modoEditorUser=null}
function updateModoEditorVisibility(){
  const role=$('modo-editor-role')?.value;
  if($('modo-editor-class-wrap'))$('modo-editor-class-wrap').style.display=role==='moderator'?'grid':'none';
  if($('modo-editor-permission-wrap'))$('modo-editor-permission-wrap').style.display=role==='moderator'?'block':'none';
  if($('modo-editor-pack-wrap'))$('modo-editor-pack-wrap').style.display=role==='moderator'?'block':'none';
}
function renderModoPermissions(selected){
  const box=$('modo-editor-permissions');if(!box)return;box.innerHTML='';
  const set=new Set(selected||DEFAULT_MODO_PERMS);
  modoPermissionCatalog.forEach(item=>{const label=document.createElement('label');label.className='modo-permission';label.innerHTML=`<input type="checkbox" value="${esc(item.key)}" ${set.has(item.key)?'checked':''}><span><strong>${esc(item.label)}</strong><small>${esc(item.key)}</small></span>`;box.append(label);label.querySelector('input').addEventListener('change',detectModoPackFromChecks)});
}
async function changeRole(u){
  await ensureModoPermissionCatalog();modoEditorUser=u;
  $('modo-editor-title').textContent=`Configurer ${u.username}`;
  $('modo-editor-role').value=u.role||'player';
  $('modo-editor-class').value=u.moderator_class_code||u.class_code||'';
  renderModoPermissions(u.moderator_permissions?.length?u.moderator_permissions:DEFAULT_MODO_PERMS);
  renderModoPacks(u.moderator_pack||'custom');
  updateModoEditorVisibility();
  const b=$('modo-editor-backdrop');b.classList.add('open');b.setAttribute('aria-hidden','false');
}
async function saveModoEditor(){
  if(!modoEditorUser)return;
  const role=$('modo-editor-role').value;
  const class_code=role==='moderator'?$('modo-editor-class').value.trim().toUpperCase():null;
  if(role==='moderator'&&!class_code){msg('Indique la classe du modérateur.');return}
  const permissions=role==='moderator'?[...document.querySelectorAll('#modo-editor-permissions input:checked')].map(x=>x.value):[];
  try{
    await api(`/api/admin/users/${modoEditorUser.id}/role`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,class_code,permissions,moderator_pack:role==='moderator'&&selectedModoPack!=='custom'?selectedModoPack:null})});
    msg('Grade et permissions enregistrés. Le compte devra se reconnecter.',true);closeModoEditor();await refreshAll();
  }catch(e){msg(e.message)}
}
document.addEventListener('DOMContentLoaded',()=>{
  $('modo-editor-role')?.addEventListener('change',updateModoEditorVisibility);
  $('modo-editor-close')?.addEventListener('click',closeModoEditor);
  $('modo-editor-cancel')?.addEventListener('click',closeModoEditor);
  $('modo-editor-save')?.addEventListener('click',saveModoEditor);
  $('modo-editor-backdrop')?.addEventListener('click',e=>{if(e.target===e.currentTarget)closeModoEditor()});
});
