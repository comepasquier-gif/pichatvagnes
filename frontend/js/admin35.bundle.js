/* ===== backup_studio.js ===== */
(()=>{
const $=id=>document.getElementById(id);let backups=[],selected=null;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>{const u=['o','Ko','Mo','Go'];let i=0,v=Number(n||0);while(v>=1024&&i<u.length-1){v/=1024;i++}return `${v.toFixed(i?1:0)} ${u[i]}`};
async function api(url,opt={}){const r=await fetch(url,{credentials:'same-origin',...opt});let d=null;try{d=await r.json()}catch{}if(!r.ok)throw new Error(d?.detail||`Erreur ${r.status}`);return d}
function notify(t,ok=false){if(window.msg)return window.msg(t,ok);alert(t)}
async function load(){const list=$('backup-list');if(!list)return;try{backups=await api('/api/admin/backups');renderList();if(selected){const same=backups.find(x=>x.name===selected.name);if(same)await select(same.name);else{selected=null;renderEmpty()}}}catch(e){list.innerHTML=`<p class="backup-error">${esc(e.message)}</p>`}}
function renderList(){const el=$('backup-list');if(!backups.length){el.innerHTML='<div class="backup-empty compact"><span>💾</span><strong>Aucun backup</strong><small>Crée ton premier backup avec le bouton ci-dessus.</small></div>';return}el.innerHTML=backups.map(b=>`<button class="backup-card ${selected?.name===b.name?'active':''} ${b.valid?'':'invalid'}" data-backup="${esc(b.name)}"><span class="backup-card-icon">${b.valid?'💾':'⚠️'}</span><span><strong>${esc(b.label||b.name)}</strong><small>${esc(b.name)}</small><small>${b.valid?`${b.users} comptes · ${b.messages} messages · ${fmt(b.size)}`:esc(b.error)}</small></span><time>${esc((b.created_at||b.modified_at||'').replace('T',' ').slice(0,16))}</time></button>`).join('');el.querySelectorAll('[data-backup]').forEach(b=>b.onclick=()=>select(b.dataset.backup))}
function renderEmpty(){$('backup-detail').innerHTML='<div class="backup-empty"><span>💾</span><strong>Sélectionne une sauvegarde</strong><small>Son contenu et ses outils apparaîtront ici.</small></div>'}
async function select(name){try{selected=await api('/api/admin/backups/'+encodeURIComponent(name));renderList();renderDetail()}catch(e){notify(e.message)}}
function renderDetail(){const b=selected, el=$('backup-detail');if(!b)return renderEmpty();const files=b.files||[];el.innerHTML=`<div class="backup-detail-head"><div><span class="state-badge ${b.valid?'state-active':'state-banned'}">${b.valid?'VALIDE':'INVALIDE'}</span><h3>${esc(b.label||b.name)}</h3><p>${esc(b.name)}</p></div><a class="mini brand" href="/api/admin/backups/${encodeURIComponent(b.name)}/download">Télécharger</a></div><div class="backup-metrics"><div><b>${b.users}</b><small>COMPTES</small></div><div><b>${b.rooms}</b><small>SALONS</small></div><div><b>${b.messages}</b><small>MESSAGES</small></div><div><b>${b.uploads}</b><small>FICHIERS</small></div></div><label>Étiquette<input id="backup-label" maxlength="100" value="${esc(b.label||'')}"></label><label>Note<textarea id="backup-note" rows="3" maxlength="500">${esc(b.note||'')}</textarea></label><button id="backup-save-meta" class="primary-action">Enregistrer l’étiquette et la note</button><div class="backup-actions"><button data-ba="validate" class="mini good">✓ Vérifier</button><button data-ba="rename" class="mini">Renommer</button><button data-ba="duplicate" class="mini">Dupliquer</button><a class="mini" href="/api/admin/backups/${encodeURIComponent(b.name)}/accounts.csv">Comptes CSV</a><button data-ba="restore" class="mini bad">Restaurer</button><button data-ba="delete" class="mini bad">Supprimer</button></div><div class="backup-files-head"><div><h4>Fichiers inclus</h4><small>Tu peux ajouter, remplacer, extraire ou retirer un fichier du dossier uploads.</small></div><button id="backup-add-file" class="mini brand">＋ Ajouter</button><input id="backup-add-file-input" type="file" hidden></div><div class="backup-files">${files.length?files.map(f=>`<div class="backup-file"><span>📎</span><span><strong>${esc(f.name||f.path.replace(/^uploads\//,''))}</strong><small>${fmt(f.size)}</small></span><a title="Extraire" href="/api/admin/backups/${encodeURIComponent(b.name)}/files/${encodeURIComponent(f.path.replace(/^uploads\//,''))}">↓</a><button title="Retirer" data-remove-file="${esc(f.path)}">×</button></div>`).join(''):'<p class="muted">Aucun fichier uploadé dans ce backup.</p>'}</div>`;
$('backup-save-meta').onclick=saveMeta;el.querySelectorAll('[data-ba]').forEach(x=>x.onclick=()=>action(x.dataset.ba));$('backup-add-file').onclick=()=>$('backup-add-file-input').click();$('backup-add-file-input').onchange=addFile;el.querySelectorAll('[data-remove-file]').forEach(x=>x.onclick=()=>removeFile(x.dataset.removeFile));}
async function saveMeta(){try{selected=await api('/api/admin/backups/'+encodeURIComponent(selected.name),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:$('backup-label').value,note:$('backup-note').value})});notify('Backup modifié.',true);await load()}catch(e){notify(e.message)}}
async function action(a){if(!selected)return;try{if(a==='validate'){await api(`/api/admin/backups/${encodeURIComponent(selected.name)}/validate`,{method:'POST'});notify('Backup valide ✓',true)}if(a==='rename'){const n=prompt('Nouveau nom du fichier ZIP :',selected.name);if(!n)return;selected=await api(`/api/admin/backups/${encodeURIComponent(selected.name)}/rename`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({new_name:n})});notify('Backup renommé.',true)}if(a==='duplicate'){const n=prompt('Nom de la copie (laisser vide pour automatique) :','');selected=await api(`/api/admin/backups/${encodeURIComponent(selected.name)}/duplicate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({new_name:n||null})});notify('Copie créée.',true)}if(a==='delete'){if(!confirm(`Supprimer définitivement ${selected.name} ?`))return;await api(`/api/admin/backups/${encodeURIComponent(selected.name)}`,{method:'DELETE'});selected=null;notify('Backup supprimé.',true)}if(a==='restore'){const c=prompt(`RESTAURATION COMPLÈTE\n\nPiChat créera d’abord une sauvegarde de sécurité. Tous les utilisateurs seront déconnectés.\n\nTape RESTAURER pour continuer :`,'');if(c!=='RESTAURER')return;const r=await api(`/api/admin/backups/${encodeURIComponent(selected.name)}/restore`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmation:c})});alert(`Restauration terminée.\nBackup de sécurité : ${r.safety_backup}\n\nRecharge PiChat et reconnecte-toi.`);location.href='/login';return}await load()}catch(e){notify(e.message)}}
async function create(){const label=prompt('Étiquette du nouveau backup (facultatif) :','Backup manuel');if(label===null)return;try{selected=await api('/api/admin/backups',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label,note:''})});notify('Backup créé ✓',true);await load()}catch(e){notify(e.message)}}
async function importZip(){const input=$('backup-import-file'),file=input.files[0];if(!file)return;const fd=new FormData();fd.append('file',file);try{selected=await api('/api/admin/backups/import',{method:'POST',body:fd});notify('Backup importé ✓',true);await load()}catch(e){notify(e.message)}finally{input.value=''}}
async function addFile(){const input=$('backup-add-file-input'),file=input.files[0];if(!file)return;const fd=new FormData();fd.append('file',file);try{selected=await api(`/api/admin/backups/${encodeURIComponent(selected.name)}/files`,{method:'POST',body:fd});notify('Fichier ajouté au backup.',true);await load()}catch(e){notify(e.message)}finally{input.value=''}}
async function removeFile(path){if(!confirm(`Retirer ${path.replace(/^uploads\//,'')} de ce backup ?`))return;try{selected=await api(`/api/admin/backups/${encodeURIComponent(selected.name)}/files`,{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})});notify('Fichier retiré.',true);await load()}catch(e){notify(e.message)}}
function bind(){if(!$('backup-list'))return;$('backup-create').onclick=create;$('backup-import').onclick=()=>$('backup-import-file').click();$('backup-import-file').onchange=importZip;load();window.addEventListener('hashchange',()=>{if(location.hash==='#backups')load()})}
document.addEventListener('DOMContentLoaded',bind);window.PiChatBackupStudio={load};})();

;
/* ===== admin.js ===== */
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

;
/* ===== admin_v21.js ===== */
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function api(url, options={}) {
    const response = await fetch(url, {credentials:'same-origin',cache:'no-store',...options});
    let data={}; try { data=await response.json(); } catch {}
    if(!response.ok) throw new Error(data.detail || `Erreur ${response.status}`);
    return data;
  }
  function flash(text, ok=true){
    if(typeof window.msg==='function') return window.msg(text,ok);
    alert(text);
  }
  function render(data){
    const settings=data.settings||{};
    $('deployment-public-url').value=settings.public_url||'';
    $('deployment-hosts').value=settings.allowed_hosts||'localhost,127.0.0.1';
    $('deployment-proxy').checked=!!settings.proxy_headers;
    $('deployment-https').checked=!!settings.https_enabled;
    $('deployment-ready').checked=!!settings.internet_ready;
    const state=$('deployment-state'); state.textContent=data.ready?'Prêt ✓':'À configurer'; state.classList.toggle('good',!!data.ready);
    const checks=$('deployment-checks'); checks.innerHTML='';
    const labels={public_url_https:'URL en HTTPS',allowed_hosts:'Hôtes autorisés',proxy_headers:'Reverse proxy',https_enabled:'HTTPS confirmé',caddyfile_exists:'Caddyfile généré',production_env_exists:'Fichier production .env'};
    Object.entries(data.checks||{}).forEach(([key,value])=>{
      const row=document.createElement('div'); row.className='deployment-check '+(value?'good':'warn');
      row.innerHTML=`<span>${esc(labels[key]||key)}</span><b>${value?'OK':'À faire'}</b>`; checks.append(row);
    });
  }
  async function load(){
    if(!$('deployment-form')) return;
    try { const [data,caddy]=await Promise.all([api('/api/admin/deployment'),fetch('/api/admin/deployment/caddyfile',{credentials:'same-origin',cache:'no-store'}).then(r=>r.text())]); render(data); $('deployment-caddy').textContent=caddy; }
    catch(e){ $('deployment-caddy').textContent=e.message; }
  }
  async function save(event){
    event.preventDefault();
    try{
      await api('/api/admin/deployment',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({public_url:$('deployment-public-url').value.trim(),allowed_hosts:$('deployment-hosts').value.trim(),proxy_headers:$('deployment-proxy').checked,https_enabled:$('deployment-https').checked,internet_ready:$('deployment-ready').checked})});
      flash('Configuration Internet enregistrée.',true); await load();
    }catch(e){flash(e.message,false)}
  }
  async function generate(){
    try{const result=await api('/api/admin/deployment/generate',{method:'POST'});$('deployment-caddy').textContent=result.caddyfile;flash(`Fichiers générés dans ${result.directory}`,true);await load()}
    catch(e){flash(e.message,false)}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    $('deployment-form')?.addEventListener('submit',save);
    $('deployment-generate')?.addEventListener('click',generate);
    $('deployment-refresh')?.addEventListener('click',load);
    document.querySelector('[data-tab="deployment"]')?.addEventListener('click',load);
    if(location.hash==='#deployment') load();
  });
})();

;
/* ===== admin_economy.js ===== */
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

;
/* ===== ui_settings.js ===== */
(() => {
  const PRESETS={
    'pichat-dark':{brand:'#5865f2',brand2:'#8b78ff',brand3:'#23a559'},
    amoled:{brand:'#6c63ff',brand2:'#a970ff',brand3:'#2bd576'},
    light:{brand:'#5865f2',brand2:'#7c6ff0',brand3:'#168a5b'},
    discord:{brand:'#5865f2',brand2:'#7983f5',brand3:'#23a559'},
    neon:{brand:'#7c5cff',brand2:'#21d4fd',brand3:'#20e3b2'},
    ocean:{brand:'#1da1f2',brand2:'#5ac8fa',brand3:'#23a559'},
    sunset:{brand:'#e85d9e',brand2:'#ff9f43',brand3:'#ffd166'},
    forest:{brand:'#2fb344',brand2:'#66d17a',brand3:'#d3f9d8'},
    mono:{brand:'#747f8d',brand2:'#b5bac1',brand3:'#949ba4'}
  };
  const $=(s)=>document.querySelector(s),$$=(s)=>[...document.querySelectorAll(s)];

  function applyGlobal(s){
    const r=document.documentElement,pre=PRESETS[s.theme_preset]||PRESETS.neon;
    r.style.setProperty('--brand',s.primary_color||pre.brand);r.style.setProperty('--brand2',s.secondary_color||pre.brand2);r.style.setProperty('--brand3',s.accent_color||pre.brand3);r.style.setProperty('--discord-brand',s.primary_color||pre.brand);
    document.body.dataset.globalDensity=s.density||'comfortable';document.body.dataset.serverTheme=s.theme_preset||'pichat-dark';document.title=s.app_name||'PiChat';
    $$('.chat-logo,.brand-mark,.mini-logo,.mobile-logo').forEach(el=>el.textContent=s.logo_text||'P');
    const name=$('#sidebar-app-name');if(name)name.textContent=s.app_name||'PiChat';const sub=$('#sidebar-subtitle');if(sub)sub.textContent=s.app_subtitle||'Campus Messenger';
    const welcome=$('#ui-welcome-message');if(welcome){welcome.textContent=s.welcome_message||'';welcome.style.display=s.welcome_message?'block':'none'}
    const debug=$('#debug-panel');if(debug)debug.style.display=s.show_diagnostic?'':'none';window.PICHAT_UI_SETTINGS=s;
  }
  function prefs(){try{return JSON.parse(localStorage.getItem('pichat-user-ui')||'{}')}catch{return {}}}
  function save(p){localStorage.setItem('pichat-user-ui',JSON.stringify(p));applyLocal(p)}
  function applyLocal(p){const b=document.body;b.dataset.userTheme=p.theme||'global';b.dataset.glass=p.glass===false?'false':'true';b.dataset.reduceMotion=p.reduceMotion?'true':'false';b.dataset.userDensity=p.compact?'compact':'global';b.dataset.fontSize=p.fontSize||'normal';b.dataset.roundness=p.roundness||'round';b.dataset.glass=p.glass?'true':'false';b.dataset.wallpaper=p.wallpaper||'none';b.dataset.messageLayout=p.messageLayout||'cozy';if(p.accent){document.documentElement.style.setProperty('--discord-brand',p.accent)}else if(window.PICHAT_UI_SETTINGS){document.documentElement.style.setProperty('--discord-brand',window.PICHAT_UI_SETTINGS.primary_color||'#5865f2')}}

  function inject(){
    let modal=document.getElementById('ui-personalize-modal');if(modal)return;
    const fab=document.createElement('button');fab.id='ui-personalize-button';fab.className='ui-fab';fab.title='Personnalisation';fab.textContent='🎨';fab.style.display='none';document.body.append(fab);
    modal=document.createElement('div');modal.className='modal-backdrop ui-modal-backdrop';modal.id='ui-personalize-modal';modal.innerHTML=`<section class="discord-modal wide-modal ui-modal ui-personalize-card"><header class="ui-modal-head"><div><span class="eyebrow ui-eyebrow">MON PICHAT</span><h2>Personnalisation</h2><p class="ui-help">Ces préférences restent sur ce navigateur.</p></div><button class="modal-close ui-close" type="button" aria-label="Fermer">×</button></header>
    <div class="tutor-grid"><label>Thème<select id="ui-local-theme"><option value="global">Thème du serveur</option><option value="pichat-dark">PiChat Dark</option><option value="amoled">AMOLED</option><option value="light">Light</option><option value="discord">Discord</option><option value="neon">Neon</option><option value="ocean">Ocean (legacy)</option><option value="sunset">Sunset (legacy)</option><option value="forest">Forest (legacy)</option><option value="mono">Mono (legacy)</option></select></label><label>Accent<input id="ui-local-accent" type="color" value="#5865f2"></label><label>Taille du texte<select id="ui-font-size"><option value="small">Petite</option><option value="normal">Normale</option><option value="large">Grande</option></select></label><label>Arrondis<select id="ui-roundness"><option value="soft">Discrets</option><option value="round">Arrondis</option><option value="pill">Très arrondis</option></select></label><label>Fond<select id="ui-wallpaper"><option value="none">Uni</option><option value="dots">Points</option><option value="grid">Grille</option><option value="aurora">Aurora</option></select></label><label>Messages<select id="ui-message-layout"><option value="cozy">Confortable</option><option value="compact">Compact</option></select></label></div>
    <div class="personalization-toggles"><label class="ui-check"><span>Mode compact global</span><input id="ui-compact" type="checkbox"></label><label class="ui-check"><span>Effet verre</span><input id="ui-glass" type="checkbox"></label><label class="ui-check"><span>Réduire les animations</span><input id="ui-reduce-motion" type="checkbox"></label><label class="ui-check"><span>Trolls / easter eggs 😈</span><input id="ui-trolls" type="checkbox"></label></div>
    <div class="ui-actions"><button type="button" id="ui-local-reset">Réinitialiser</button><button type="button" id="ui-local-save" class="ui-primary">Appliquer</button></div></section>`;document.body.append(modal);
    const p=prefs();document.getElementById('ui-local-theme').value=p.theme||'global';document.getElementById('ui-local-accent').value=p.accent||'#5865f2';document.getElementById('ui-font-size').value=p.fontSize||'normal';document.getElementById('ui-roundness').value=p.roundness||'round';document.getElementById('ui-wallpaper').value=p.wallpaper||'none';document.getElementById('ui-message-layout').value=p.messageLayout||'cozy';document.getElementById('ui-compact').checked=!!p.compact;document.getElementById('ui-glass').checked=!!p.glass;document.getElementById('ui-reduce-motion').checked=!!p.reduceMotion;document.getElementById('ui-trolls').checked=p.trolls!==false;
    const close=()=>modal.classList.remove('open');fab.onclick=()=>modal.classList.add('open');modal.querySelector('.modal-close').onclick=close;modal.onclick=e=>{if(e.target===modal)close()};document.getElementById('ui-local-save').onclick=()=>{save({theme:document.getElementById('ui-local-theme').value,accent:document.getElementById('ui-local-accent').value,fontSize:document.getElementById('ui-font-size').value,roundness:document.getElementById('ui-roundness').value,wallpaper:document.getElementById('ui-wallpaper').value,messageLayout:document.getElementById('ui-message-layout').value,compact:document.getElementById('ui-compact').checked,glass:document.getElementById('ui-glass').checked,reduceMotion:document.getElementById('ui-reduce-motion').checked,trolls:document.getElementById('ui-trolls').checked});close()};document.getElementById('ui-local-reset').onclick=()=>{localStorage.removeItem('pichat-user-ui');location.reload()};
  }
  async function init(){try{const r=await fetch('/api/ui-settings',{cache:'no-store'});if(r.ok)applyGlobal(await r.json())}catch{}applyLocal(prefs());inject()}
  window.PiChatUI={applyGlobal};if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();

;
/* ===== pwa.js ===== */
(() => {
  'use strict';
  const PREF_KEY='pichat_pwa_preferences_v1';
  const UNREAD_KEY='pichat_pwa_unread_v1';
  const DRAFT_KEY='pichat_pwa_drafts_v1';
  const defaults={notifications:'mentions',sound:true,showPreview:true};
  let prefs={...defaults}; let unread={}; let deferredPrompt=null; let registration=null; let activeRoom=null;
  let notificationSocket=null; let notificationHeartbeat=null; let notificationRetry=1000; let wasOffline=!navigator.onLine;
  const $=id=>document.getElementById(id);
  const readJSON=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key))||fallback}catch{return fallback}};
  const savePrefs=()=>localStorage.setItem(PREF_KEY,JSON.stringify(prefs));
  const saveUnread=()=>localStorage.setItem(UNREAD_KEY,JSON.stringify(unread));
  const isStandalone=()=>window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;
  const isiOS=()=>/iphone|ipad|ipod/i.test(navigator.userAgent);
  const isSafari=()=>/^((?!chrome|android).)*safari/i.test(navigator.userAgent);
  const roomName=id=>window.CURRENT_ROOMS?.find(r=>Number(r.id)===Number(id))?.name||'salon';
  const ownUser=()=>window.CURRENT_USER||{};

  function toast(text){let t=$('pwa-toast');if(!t){t=document.createElement('div');t.id='pwa-toast';t.className='pwa-toast';document.body.append(t)}t.textContent=text;t.classList.add('show');clearTimeout(t._timer);t._timer=setTimeout(()=>t.classList.remove('show'),2600)}
  function addMeta(){document.documentElement.classList.toggle('pwa-app-mode',isStandalone());}
  function setOnlineUI(){const online=navigator.onLine;$('pwa-offline-banner')?.classList.toggle('show',!online);if(online&&wasOffline)toast('Connexion rétablie');wasOffline=!online;}

  async function registerSW(){
    if(!('serviceWorker' in navigator))return;
    try{
      registration=await navigator.serviceWorker.register('/service-worker.js',{scope:'/',updateViaCache:'none'});
      registration.addEventListener('updatefound',()=>{const w=registration.installing;if(!w)return;w.addEventListener('statechange',()=>{if(w.state==='installed'&&navigator.serviceWorker.controller)$('pwa-update-banner')?.classList.add('show')})});
      let reloading=false;navigator.serviceWorker.addEventListener('controllerchange',()=>{if(reloading)return;reloading=true;location.reload()});
      navigator.serviceWorker.addEventListener('message',e=>{if(e.data?.type==='PICHAT_UPDATED'){toast('PiChat mis à jour · '+(e.data.version||''));}if(e.data?.type==='pichat:notification-click'&&e.data.roomId){if(window.switchRoom)window.switchRoom(Number(e.data.roomId));else location.href=`/?room=${Number(e.data.roomId)}`}});
    }catch(e){console.warn('Service worker PiChat',e)}
  }

  function updateInstallUI(){
    const button=$('install-app-button'); if(!button)return;
    if(isStandalone()){button.title='PiChat est installé';button.textContent='✓';button.classList.remove('pwa-install-pulse');return}
    button.textContent='⬇';button.title='Installer PiChat comme une application';button.classList.add('pwa-install-pulse');
  }

  async function installApp(){
    if(deferredPrompt){deferredPrompt.prompt();const choice=await deferredPrompt.userChoice;deferredPrompt=null;updateInstallUI();toast(choice.outcome==='accepted'?'Installation lancée':'Installation annulée');return}
    openPwaModal();
    const help=$('pwa-platform-help');
    if(help){
      if(isiOS())help.innerHTML='<b>Sur iPhone/iPad :</b> dans Safari, touche <b>Partager</b> puis <b>Sur l’écran d’accueil</b>.';
      else if(isSafari())help.innerHTML='<b>Sur Mac Safari :</b> menu <b>Fichier → Ajouter au Dock</b>.';
      else help.innerHTML='<b>Dans le navigateur :</b> ouvre le menu puis choisis <b>Installer PiChat</b> ou <b>Ajouter à l’écran d’accueil</b>.';
      help.classList.add('show');
    }
  }

  async function requestNotifications(){
    if(!('Notification' in window)){toast('Ce navigateur ne prend pas en charge les notifications.');return false}
    const permission=await Notification.requestPermission();updateNotificationUI();
    if(permission==='granted'){toast('Notifications activées');return true}
    toast('Notifications refusées dans le navigateur');return false;
  }

  function updateNotificationUI(){
    const b=$('notification-button'); if(!b)return;
    const p=('Notification'in window)?Notification.permission:'unsupported';
    b.textContent=p==='granted'?'🔔':p==='denied'?'🔕':'🔔';b.title=p==='granted'?'Notifications actives':'Configurer les notifications';
    const dot=$('pwa-notification-status');if(dot){dot.className='pwa-status-dot '+(p==='granted'?'ok':p==='denied'?'bad':'warn')}
    const label=$('pwa-notification-label');if(label)label.textContent=p==='granted'?'Autorisées':p==='denied'?'Bloquées par le navigateur':'À autoriser';
  }

  function shouldNotify(message,roomId){
    if(!message||Number(message.user_id)===Number(ownUser().id))return false;
    if(prefs.notifications==='off')return false;
    const text=String(message.content||'');const mention=ownUser().username&&text.toLowerCase().includes('@'+ownUser().username.toLowerCase());
    if(prefs.notifications==='mentions'&&!mention)return false;
    return document.hidden||!document.hasFocus()||Number(activeRoom)!==Number(roomId);
  }

  async function showNotification(message,roomId){
    if(!shouldNotify(message,roomId)||!('Notification'in window)||Notification.permission!=='granted')return;
    const content=String(message.content||'Nouveau message');
    const payload={title:`${message.username||'Quelqu’un'} · #${roomName(roomId)}`,body:prefs.showPreview?content.slice(0,180):'Nouveau message sur PiChat',roomId,url:`/?room=${roomId}`,tag:`pichat-room-${roomId}`,silent:!prefs.sound};
    try{
      const reg=registration||await navigator.serviceWorker?.ready;
      if(reg?.active)reg.active.postMessage({type:'SHOW_NOTIFICATION',payload});
      else new Notification(payload.title,{body:payload.body,icon:'/assets/icons/pichat-192.png',tag:payload.tag});
    }catch(e){console.warn('Notification PiChat',e)}
  }

  function badgeFor(el,count,room=false){
    if(!el)return;
    if(room){let b=el.querySelector('.pwa-room-unread');if(!count){b?.remove();return}if(!b){b=document.createElement('span');b.className='pwa-room-unread';el.append(b)}b.textContent=count>99?'99+':String(count);return}
    let b=el.querySelector('.pwa-badge');if(!b){b=document.createElement('span');b.className='pwa-badge';el.append(b)}b.textContent=count>99?'99+':String(count);b.classList.toggle('show',count>0);
  }

  function updateUnreadUI(){
    let total=0;Object.entries(unread).forEach(([id,count])=>{count=Number(count)||0;total+=count;badgeFor(document.querySelector(`.channel-button[data-room-id="${id}"]`),count,true);badgeFor(document.querySelector(`.server-icon[data-room-id="${id}"]`),count,false)});
    document.title=total?`(${total}) PiChat`:'PiChat';
    if('setAppBadge'in navigator){if(total)navigator.setAppBadge(total).catch(()=>{});else navigator.clearAppBadge?.().catch(()=>{})}
  }
  function markRead(roomId){if(!roomId)return;unread[String(roomId)]=0;saveUnread();updateUnreadUI()}
  function addUnread(roomId,message){if(Number(message?.user_id)===Number(ownUser().id))return;if(Number(roomId)===Number(activeRoom)&&!document.hidden&&document.hasFocus())return;const k=String(roomId);unread[k]=(Number(unread[k])||0)+1;saveUnread();updateUnreadUI()}
  function onIncomingMessage(message,roomId){addUnread(roomId,message);showNotification(message,roomId)}
  function onRoomChanged(roomId){activeRoom=Number(roomId);markRead(activeRoom);restoreDraft(activeRoom);updateUnreadUI()}

  function connectNotificationSocket(){
    if(!window.CURRENT_USER||notificationSocket?.readyState===WebSocket.OPEN||notificationSocket?.readyState===WebSocket.CONNECTING)return;
    const protocol=location.protocol==='https:'?'wss:':'ws:';
    notificationSocket=new WebSocket(`${protocol}//${location.host}/ws/notifications`);
    notificationSocket.addEventListener('open',()=>{notificationRetry=1000;clearInterval(notificationHeartbeat);notificationHeartbeat=setInterval(()=>{if(notificationSocket?.readyState===WebSocket.OPEN)notificationSocket.send('ping')},25000)});
    notificationSocket.addEventListener('message',event=>{try{const data=JSON.parse(event.data);if(data.type==='room_notification'&&data.message)onIncomingMessage(data.message,Number(data.room_id));else if(data.type==='forced_logout'){location.href='/login'}}catch(e){console.warn('Notifications temps réel',e)}});
    notificationSocket.addEventListener('close',()=>{clearInterval(notificationHeartbeat);notificationHeartbeat=null;setTimeout(connectNotificationSocket,notificationRetry);notificationRetry=Math.min(notificationRetry*2,15000)});
    notificationSocket.addEventListener('error',()=>notificationSocket?.close());
  }

  function draftMap(){return readJSON(DRAFT_KEY,{})}
  function saveDraft(){const input=$('message-input');if(!input||!activeRoom)return;const map=draftMap();if(input.value)map[String(activeRoom)]=input.value;else delete map[String(activeRoom)];localStorage.setItem(DRAFT_KEY,JSON.stringify(map))}
  function restoreDraft(roomId){const input=$('message-input');if(!input)return;input.value=draftMap()[String(roomId)]||'';}

  function openPwaModal(){$('pwa-modal')?.classList.add('open')}
  function closePwaModal(){$('pwa-modal')?.classList.remove('open')}
  function bind(){
    $('install-app-button')?.addEventListener('click',installApp);
    $('notification-button')?.addEventListener('click',openPwaModal);
    $('pwa-open-settings')?.addEventListener('click',openPwaModal);
    $('pwa-modal-close')?.addEventListener('click',closePwaModal);
    $('pwa-enable-notifications')?.addEventListener('click',requestNotifications);
    $('pwa-install-action')?.addEventListener('click',installApp);
    $('pwa-notification-mode')?.addEventListener('change',e=>{prefs.notifications=e.target.value;savePrefs();toast('Préférence enregistrée')});
    $('pwa-preview-toggle')?.addEventListener('change',e=>{prefs.showPreview=e.target.checked;savePrefs()});
    $('pwa-sound-toggle')?.addEventListener('change',e=>{prefs.sound=e.target.checked;savePrefs()});
    $('pwa-update-now')?.addEventListener('click',()=>registration?.waiting?.postMessage({type:'SKIP_WAITING'}));
    $('pwa-update-later')?.addEventListener('click',()=>$('pwa-update-banner')?.classList.remove('show'));
    const input=$('message-input');input?.addEventListener('input',saveDraft);document.addEventListener('visibilitychange',()=>{if(!document.hidden&&activeRoom)markRead(activeRoom)});window.addEventListener('focus',()=>activeRoom&&markRead(activeRoom));
    window.addEventListener('online',setOnlineUI);window.addEventListener('offline',setOnlineUI);
    window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();deferredPrompt=e;updateInstallUI()});
    window.addEventListener('appinstalled',()=>{deferredPrompt=null;updateInstallUI();toast('PiChat est installé 🎉')});
  }

  function hydrateSettings(){prefs={...defaults,...readJSON(PREF_KEY,{})};unread=readJSON(UNREAD_KEY,{});if($('pwa-notification-mode'))$('pwa-notification-mode').value=prefs.notifications;if($('pwa-preview-toggle'))$('pwa-preview-toggle').checked=!!prefs.showPreview;if($('pwa-sound-toggle'))$('pwa-sound-toggle').checked=!!prefs.sound;}
  async function ensureUserForNotifications(){if(window.CURRENT_USER){connectNotificationSocket();return}try{const r=await fetch('/api/me',{credentials:'same-origin',cache:'no-store'});if(r.ok){window.CURRENT_USER=await r.json();connectNotificationSocket()}}catch{}}
  async function init(){addMeta();hydrateSettings();bind();setOnlineUI();updateInstallUI();updateNotificationUI();updateUnreadUI();await registerSW();if(registration){registration.update().catch(()=>{});setInterval(()=>registration.update().catch(()=>{}),5*60*1000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)registration.update().catch(()=>{})});}window.addEventListener('pichat:user-ready',connectNotificationSocket,{once:true});ensureUserForNotifications();if(new URLSearchParams(location.search).get('open')==='tutor')setTimeout(()=>$('open-tutor')?.click(),700)}

  window.PiChatPWA={onIncomingMessage,onRoomChanged,markRead,openSettings:openPwaModal,toast};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();

;
/* ===== admin_badges.js ===== */
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

;
/* ===== admin_arcade.js ===== */
(()=>{
  const $=id=>document.getElementById(id);let data=null;
  const names={reflex:'⚡ Réflexe éclair',memory:'🧠 Mémoire express',clicker:'👆 Click Rush',number:'🔢 Nombre mystère',quiz:'🧩 Quiz express',tictactoe:'⭕ Morpion'};
  async function api(url,options={}){const r=await fetch(url,{credentials:'same-origin',...options});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||'Erreur Arcade');return d}
  function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
  function notice(text,ok=true){if(window.msg)return window.msg(text,ok);alert(text)}
  async function load(){if(!$('arcade-admin-form'))return;try{data=await api('/api/admin/arcade');render()}catch(e){notice(e.message,false)}}
  function render(){const s=data.settings,t=data.totals;$('arcade-admin-enabled').checked=!!s.enabled;$('arcade-admin-rewards').checked=!!s.rewards_enabled;$('arcade-admin-plays').value=s.rewarded_plays_per_day;$('arcade-admin-cap').value=s.daily_coin_cap;$('arcade-admin-daily-coins').value=s.daily_challenge_coins;$('arcade-admin-daily-xp').value=s.daily_challenge_xp;$('arcade-admin-totals').innerHTML=[['Parties',t.plays],['Joueurs',t.players],['PyCoins distribués',t.coins],['XP distribuée',t.xp]].map(x=>`<div class="arcade-admin-total"><b>${Number(x[1]||0)}</b><small>${x[0]}</small></div>`).join('');$('arcade-admin-popular').innerHTML=data.popular.length?data.popular.map(x=>`<div class="arcade-admin-row"><span>${names[x.game_key]||esc(x.game_key)}</span><b>${x.plays}</b></div>`).join(''):'<p class="muted">Aucune partie.</p>';$('arcade-admin-recent').innerHTML=data.recent.length?data.recent.map(x=>`<div class="arcade-admin-row"><span><b>${esc(x.username)}</b><br><small>${names[x.game_key]||esc(x.game_key)} · ${esc(x.result_label)} · ${esc(x.created_at)}</small></span><b>${x.score}</b></div>`).join(''):'<p class="muted">Aucune partie.</p>'}
  async function save(e){e.preventDefault();try{const settings=await api('/api/admin/arcade/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:$('arcade-admin-enabled').checked,rewards_enabled:$('arcade-admin-rewards').checked,rewarded_plays_per_day:Number($('arcade-admin-plays').value),daily_coin_cap:Number($('arcade-admin-cap').value),daily_challenge_coins:Number($('arcade-admin-daily-coins').value),daily_challenge_xp:Number($('arcade-admin-daily-xp').value)})});data.settings=settings;render();notice('Réglages Arcade enregistrés.',true)}catch(error){notice(error.message,false)}}
  $('arcade-admin-form')?.addEventListener('submit',save);$('arcade-admin-refresh')?.addEventListener('click',load);document.querySelector('[data-tab="arcade"]')?.addEventListener('click',load);load();
})();

;
/* ===== admin_game_studio.js ===== */
(() => {
  const $=id=>document.getElementById(id);
  async function api(url,options={}){const r=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||`Erreur ${r.status}`);return d}
  function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
  function message(text,ok=false){const el=$(ok?'success-message':'error-message');if(!el)return;el.textContent=text;el.classList.add('visible');setTimeout(()=>el.classList.remove('visible'),3000)}
  async function load(){
    if(!$('game-studio-settings-form'))return;
    try{
      const [settings,games]=await Promise.all([api('/api/admin/game-studio/settings'),api('/api/game-studio/games')]);
      $('game-studio-enabled').checked=!!settings.enabled;$('game-studio-api').checked=!!settings.direct_api_enabled;$('game-studio-approval').checked=!!settings.require_admin_approval;$('game-studio-limit').value=settings.max_games_per_user||8;
      $('game-studio-api-state').textContent=settings.api_key_configured?'Clé API détectée sur le serveur.':'Aucune clé API détectée.';
      const box=$('game-studio-review-list');box.innerHTML='';
      if(!games.pending.length)box.innerHTML='<p class="muted">Aucun jeu en attente.</p>';
      games.pending.forEach(g=>{const card=document.createElement('article');card.className='admin-studio-review';card.innerHTML=`<span>${esc(g.icon||'🎮')}</span><div><strong>${esc(g.title)}</strong><small>par ${esc(g.owner_username)} · ${esc(g.description||'')}</small></div><button class="mini good">Publier</button><button class="mini bad">Refuser</button>`;const buttons=card.querySelectorAll('button');buttons[0].onclick=()=>review(g.id,true);buttons[1].onclick=()=>review(g.id,false);box.append(card)});
    }catch(error){message(error.message)}
  }
  async function save(event){event.preventDefault();try{await api('/api/admin/game-studio/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:$('game-studio-enabled').checked,direct_api_enabled:$('game-studio-api').checked,require_admin_approval:$('game-studio-approval').checked,max_games_per_user:Number($('game-studio-limit').value||8)})});message('PiGame Studio enregistré.',true);await load()}catch(error){message(error.message)}}
  async function review(id,approve){const note=prompt(approve?'Note facultative :':'Motif du refus :','');if(note===null)return;try{await api(`/api/admin/game-studio/games/${id}/${approve?'approve':'reject'}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({note})});message(approve?'Jeu publié.':'Jeu refusé.',true);await load()}catch(error){message(error.message)}}
  document.addEventListener('DOMContentLoaded',()=>{$('game-studio-settings-form')?.addEventListener('submit',save);$('game-studio-admin-refresh')?.addEventListener('click',load);load()});
  window.PiGameStudioAdmin={load};
})();

;
/* ===== admin_test_lab.js ===== */
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
  async function sendDiagnostic(){const button=$('test-lab-send-message');button.disabled=true;try{const result=await api('/api/admin/test-lab/send-message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:'✅ Diagnostic PiChat 3.5 : le serveur accepte bien les messages.'})});notice(`Message de diagnostic envoyé dans le salon ${result.room_id}.`,true)}catch(error){notice(error.message)}finally{button.disabled=false}}
  async function simulateConnections(){const button=$('test-lab-simulate-connections');if(!button)return;button.disabled=true;try{const result=await api('/api/admin/test-lab/simulate-connections',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({count:12})});notice(`${result.simulated_connections} connexions de test simulées sur ${result.test_users} compte(s).`,true);await load()}catch(error){notice(error.message)}finally{button.disabled=false}}
  function copyCredentials(){if(!lastCredentials.length)return;const text=lastCredentials.map(x=>`${x.username}\t${x.password}\t${x.class_code}\t${x.role}`).join('\n');navigator.clipboard?.writeText(text).then(()=>notice('Identifiants copiés.',true)).catch(()=>download('identifiants_pichat_test.txt',text))}
  function downloadCredentials(){if(!lastCredentials.length)return;const rows=['pseudo,mot_de_passe,classe,role',...lastCredentials.map(x=>[x.username,x.password,x.class_code,x.role].map(v=>`"${String(v).replace(/"/g,'""')}"`).join(','))];download('identifiants_pichat_test.csv','\ufeff'+rows.join('\n'),'text/csv')}
  function bind(){
    $('test-lab-create-form')?.addEventListener('submit',create);$('test-lab-clean-all')?.addEventListener('click',cleanAll);$('test-lab-refresh')?.addEventListener('click',load);$('test-lab-send-message')?.addEventListener('click',sendDiagnostic);$('test-lab-simulate-connections')?.addEventListener('click',simulateConnections);$('test-lab-copy-credentials')?.addEventListener('click',copyCredentials);$('test-lab-download-credentials')?.addEventListener('click',downloadCredentials);document.querySelector('[data-tab="test-lab"]')?.addEventListener('click',load);load();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
  window.PiChatTestLab={load};
})();

;
/* ===== admin_final_packs.js ===== */
(()=>{
  'use strict';
  const $=id=>document.getElementById(id);
  async function api(url,options={}){const r=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||`Erreur ${r.status}`);return d}
  function note(text,ok=false){const id=ok?'success-message':'error-message';const box=$(id);if(box){box.textContent=text;box.classList.add('show');setTimeout(()=>box.classList.remove('show'),3500)}else alert(text)}
  function fmtDate(value){if(!value)return 'Jamais';const d=new Date(value.replace(' ','T')+'Z');return Number.isNaN(d.getTime())?value:d.toLocaleString()}
  function setValue(id,value){const el=$(id);if(!el)return;if(el.type==='checkbox')el.checked=!!value;else el.value=value??''}
  async function load(){
    const root=$('final-pack-admin-status');if(root)root.innerHTML='<p class="muted">Chargement…</p>';
    try{
      const data=await api('/api/admin/final-packs');const s=data.settings,stats=data.stats;
      setValue('pack-scheduled-enabled',s.scheduled_messages_enabled);setValue('pack-social-enabled',s.social_enabled);setValue('pack-sessions-enabled',s.session_manager_enabled);setValue('pack-backup-enabled',s.auto_backup_enabled);
      setValue('pack-scheduled-days',s.scheduled_max_days);setValue('pack-edit-window',s.edit_window_minutes);setValue('pack-delete-window',s.delete_window_minutes);setValue('pack-backup-hours',s.backup_interval_hours);setValue('pack-backup-retention',s.backup_retention);
      if(root)root.innerHTML=`<article><span>Messages programmés</span><strong>${stats.scheduled.pending}</strong><small>${stats.scheduled.failed} échec(s)</small></article><article><span>Relations d’amitié</span><strong>${stats.social.friends}</strong><small>${stats.social.pending} demande(s)</small></article><article><span>Sessions actives</span><strong>${stats.sessions}</strong><small>tous les comptes</small></article><article><span>Backups automatiques</span><strong>${stats.backups.count}</strong><small>${stats.backups.last?'Dernier : '+fmtDate(stats.backups.last.created_at):'Aucun'}</small></article>`;
    }catch(error){if(root)root.innerHTML=`<p class="error">${error.message}</p>`}
  }
  async function save(event){event.preventDefault();const payload={scheduled_messages_enabled:$('pack-scheduled-enabled').checked,social_enabled:$('pack-social-enabled').checked,session_manager_enabled:$('pack-sessions-enabled').checked,auto_backup_enabled:$('pack-backup-enabled').checked,scheduled_max_days:Number($('pack-scheduled-days').value),edit_window_minutes:Number($('pack-edit-window').value),delete_window_minutes:Number($('pack-delete-window').value),backup_interval_hours:Number($('pack-backup-hours').value),backup_retention:Number($('pack-backup-retention').value)};try{await api('/api/admin/final-packs',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});note('Packs finaux enregistrés.',true);await load()}catch(error){note(error.message)}}
  async function backupNow(){const button=$('pack-backup-now');button.disabled=true;button.textContent='Sauvegarde…';try{const data=await api('/api/admin/final-packs/backup-now',{method:'POST'});note('Backup créé : '+(data.backup?.name||'OK'),true);await load()}catch(error){note(error.message)}finally{button.disabled=false;button.textContent='Créer un backup maintenant'}}
  function bind(){
    $('final-packs-admin-form')?.addEventListener('submit',save);$('pack-backup-now')?.addEventListener('click',backupNow);$('pack-final-refresh')?.addEventListener('click',load);
    document.querySelector('[data-tab="final-packs"]')?.addEventListener('click',load);load();
  }
  document.addEventListener('DOMContentLoaded',bind);
})();

;
/* ===== admin_cloud.js ===== */
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let current = null;
  let timer = null;

  async function api(url, options={}) {
    const response = await fetch(url, {credentials:'same-origin',cache:'no-store',...options});
    let data={};
    try { data=await response.json(); } catch {}
    if(!response.ok) throw new Error(data.detail || `Erreur ${response.status}`);
    return data;
  }
  function flash(text, ok=true){
    if(typeof window.msg==='function') return window.msg(text,ok);
    alert(text);
  }
  function busy(button, on, text='Patiente…'){
    if(!button) return;
    if(on){button.dataset.label=button.textContent;button.disabled=true;button.textContent=text}
    else{button.disabled=false;button.textContent=button.dataset.label||button.textContent}
  }
  function statusLabel(data){
    if(data.running && data.mode==='quick') return 'URL temporaire active';
    if(data.running && data.mode==='permanent') return 'Domaine permanent actif';
    if(data.installed) return 'Prêt à mettre en ligne';
    return 'Installation nécessaire';
  }
  function render(data){
    current=data;
    const state=$('cloud-state');
    state.textContent=statusLabel(data);
    state.className='chip '+(data.running?'good':data.installed?'':'warn');
    $('cloud-platform').textContent=data.platform||'Mac';
    $('cloud-version').textContent=data.installed?(data.version||'Installé'):'Non installé';
    $('cloud-process').textContent=data.running?`Actif · PID ${data.pid}`:'Arrêté';
    $('cloud-mode').textContent=data.mode==='quick'?'Temporaire':data.mode==='permanent'?'Permanent':'—';

    const url=data.public_url||'';
    const box=$('cloud-public-box');
    box.classList.toggle('active',!!url && data.running);
    $('cloud-public-url').textContent=url||'Aucune adresse publique active';
    $('cloud-open').disabled=!url;
    $('cloud-copy').disabled=!url;
    $('cloud-share').disabled=!url;
    $('cloud-stop').disabled=!data.running;
    $('cloud-quick').disabled=!data.installed || data.running;
    $('cloud-permanent-start').disabled=!data.installed || !data.token_configured || data.running;
    $('cloud-install').textContent=data.installed?'Réinstaller cloudflared':'Installer cloudflared';
    $('cloud-token-state').textContent=data.token_configured?'Jeton enregistré sur ce Mac':'Aucun jeton enregistré';
    $('cloud-autostart-state').textContent=data.autostart?'Démarrage automatique activé':'Démarrage automatique désactivé';
    $('cloud-log').textContent=data.log_tail||data.last_error||'Aucun journal pour le moment.';
    $('cloud-error').textContent=data.last_error||'';
    $('cloud-error').hidden=!data.last_error;

    if(url){
      $('cloud-permanent-url').value ||= url.includes('trycloudflare.com')?'':url;
      $('cloud-qr').src=`/api/admin/cloud/qr?url=${encodeURIComponent(url)}&t=${Date.now()}`;
      $('cloud-qr-wrap').hidden=false;
    }else{
      $('cloud-qr-wrap').hidden=true;
      $('cloud-qr').removeAttribute('src');
    }
  }
  async function load(silent=false){
    try{render(await api('/api/admin/cloud'))}
    catch(e){if(!silent) flash(e.message,false)}
  }
  async function action(button, url, options={}, wait='Patiente…'){
    busy(button,true,wait);
    try{const data=await api(url,{method:'POST',...options});render(data);return data}
    catch(e){flash(e.message,false);await load(true);return null}
    finally{busy(button,false)}
  }
  async function copyUrl(){
    const url=current?.public_url;
    if(!url) return;
    try{await navigator.clipboard.writeText(url);flash('Adresse HTTPS copiée.',true)}
    catch{window.prompt('Copie cette adresse :',url)}
  }
  async function shareUrl(){
    const url=current?.public_url;
    if(!url) return;
    if(navigator.share){
      try{await navigator.share({title:'PiChat',text:'Rejoins PiChat',url});return}catch(e){if(e.name==='AbortError')return}
    }
    await copyUrl();
  }
  function openUrl(){
    const url=current?.public_url;
    if(url) window.open(url,'_blank','noopener,noreferrer');
  }
  async function configurePermanent(event){
    event.preventDefault();
    const button=$('cloud-permanent-save');
    const token=$('cloud-token').value.trim();
    const publicUrl=$('cloud-permanent-url').value.trim();
    const autostart=$('cloud-autostart').checked;
    busy(button,true,'Configuration…');
    try{
      const data=await api('/api/admin/cloud/permanent/configure',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({token,public_url:publicUrl,autostart})
      });
      $('cloud-token').value='';render(data);flash('Configuration permanente enregistrée.',true);
    }catch(e){flash(e.message,false)}finally{busy(button,false)}
  }
  async function deleteToken(){
    if(!confirm('Supprimer le jeton Cloudflare enregistré sur ce Mac ?')) return;
    try{render(await api('/api/admin/cloud/token',{method:'DELETE'}));flash('Jeton supprimé.',true)}
    catch(e){flash(e.message,false)}
  }
  function startPolling(){
    clearInterval(timer);
    timer=setInterval(()=>{
      const panel=document.querySelector('[data-panel="deployment"]');
      if(panel?.classList.contains('active')) load(true);
    },4000);
  }
  document.addEventListener('DOMContentLoaded',()=>{
    $('cloud-install')?.addEventListener('click',()=>action($('cloud-install'),'/api/admin/cloud/install',{},'Téléchargement…'));
    $('cloud-quick')?.addEventListener('click',()=>action($('cloud-quick'),'/api/admin/cloud/quick/start',{},'Création de l’URL…'));
    $('cloud-stop')?.addEventListener('click',()=>action($('cloud-stop'),'/api/admin/cloud/stop',{},'Arrêt…'));
    $('cloud-permanent-start')?.addEventListener('click',()=>action($('cloud-permanent-start'),'/api/admin/cloud/permanent/start',{},'Connexion…'));
    $('cloud-permanent-form')?.addEventListener('submit',configurePermanent);
    $('cloud-token-delete')?.addEventListener('click',deleteToken);
    $('cloud-copy')?.addEventListener('click',copyUrl);
    $('cloud-share')?.addEventListener('click',shareUrl);
    $('cloud-open')?.addEventListener('click',openUrl);
    $('cloud-refresh')?.addEventListener('click',()=>load());
    document.querySelector('[data-tab="deployment"]')?.addEventListener('click',()=>load());
    if(location.hash==='#deployment') load();
    startPolling();
  });
})();

;
/* ===== admin_integrations.js ===== */
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

;
/* ===== admin_pro.js ===== */
(()=>{
const $=id=>document.getElementById(id);const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api=async(url,options={})=>{const r=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||`Erreur ${r.status}`);return d};
const duration=s=>{s=Math.max(0,Number(s)||0);const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return d?`${d} j ${h} h`:h?`${h} h ${m} min`:`${m} min`};
function toast(text,bad=false){const el=$('pro-state');if(!el)return;el.textContent=text;el.classList.toggle('pro-error',!!bad);setTimeout(()=>{if(el.textContent===text)el.textContent=''},4500)}
function set(id,value){const el=$(id);if(el)el.textContent=value}
function render(d){const stats=d.stats||{},db=d.database||{},st=d.storage||{},b=d.backup||{},ai=d.api||{},pub=d.public||{},auto=d.automod||{},launch=d.launch||{};
 set('pro-version',`PiChat ${d.version} · ${d.edition||'FREE ONLINE'}`);set('pro-score',`${launch.score||0}/100`);set('pro-ready-label',launch.ready?'Prêt pour la mise en ligne':'Vérifications restantes');set('pro-uptime',duration(d.uptime_seconds));
 set('pro-online',stats.online_users||0);set('pro-users',stats.users||0);set('pro-messages',stats.messages_today||0);set('pro-mps',Number(stats.messages_per_second||0).toFixed(3));set('pro-rooms',stats.rooms||0);set('pro-disk',`${st.backend||'—'} · ${st.uploads_human||'0 o'}`);set('pro-server',d.server?.state==='online'?'En ligne':'À vérifier');
 set('pro-db',`${db.backend||'—'} · ${db.size_human||'0 o'}`);set('pro-uploads',`${st.objects||0} fichier(s) · ${st.uploads_human||'0 o'}`);set('pro-backups',`${b.count||0} · ${b.size_human||'0 o'}`);set('pro-backup-latest',b.latest?`${b.latest}${b.age_hours!=null?' · '+b.age_hours+' h':''}`:'Aucun backup');
 const cloud=$('pro-cloud');if(cloud)cloud.innerHTML=pub.https?`<span class="pro-dot ok"></span>${esc(pub.url||'HTTPS actif')}`:`<span class="pro-dot"></span>${esc(pub.url||'URL non définie')}`;
 const ap=$('pro-api');if(ap)ap.innerHTML=ai.configured?`<span class="pro-dot ${ai.last_test_status==='ok'?'ok':'warn'}"></span>${esc(ai.model||ai.provider||'API')}`:`<span class="pro-dot"></span>Non configurée (facultatif)`;
 const checks=$('pro-checks');if(checks)checks.innerHTML=(launch.checks||[]).map(c=>`<div class="pro-check ${c.ok?'ok':'missing'}"><span>${c.ok?'✓':'!'}</span><div><strong>${esc(c.label)}</strong><small>${c.ok?'OK':'À corriger'}</small></div><b>${c.weight}</b></div>`).join('');
 const health=$('pro-health');if(health)health.innerHTML=[['Base '+(db.backend||''),db.ok,db.status||db.detail],['HTTPS public',pub.https,pub.url||'Non défini'],['API IA',!!ai.configured,ai.configured?(ai.last_test_status||'configurée'):'Facultative'],['AutoModo',auto.ok,auto.enabled?'Actif':'Désactivé'],['Stockage persistant',['database','s3'].includes(st.backend),st.backend||'—']].map(([l,ok,x])=>`<div class="pro-health-row"><span class="pro-dot ${ok?'ok':''}"></span><div><strong>${esc(l)}</strong><small>${esc(x)}</small></div></div>`).join('');
 set('pro-system',`${d.platform||''} · Python ${d.python||''}`);
}
async function load(){try{render(await api('/api/admin/pro'))}catch(e){toast(e.message,true)}}
async function backup(){const el=$('pro-backup-now');if(el)el.disabled=true;try{const d=await api('/api/admin/pro/backup',{method:'POST'});render(d.overview);toast(`Backup créé : ${d.name}`)}catch(e){toast(e.message,true)}finally{if(el)el.disabled=false}}
async function bundle(){const el=$('pro-bundle');if(el)el.disabled=true;try{const d=await api('/api/admin/pro/support-bundle',{method:'POST'});toast('Diagnostic créé');location.href=d.download_url}catch(e){toast(e.message,true)}finally{if(el)el.disabled=false}}
function bind(){$('pro-refresh')?.addEventListener('click',load);$('pro-backup-now')?.addEventListener('click',backup);$('pro-bundle')?.addEventListener('click',bundle);document.querySelector('[data-tab="pro"]')?.addEventListener('click',load);if(location.hash==='#pro')load()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
})();

;
/* ===== admin_online34.js ===== */
(() => {
 const $=id=>document.getElementById(id);
 async function api(url){const r=await fetch(url,{credentials:'same-origin',cache:'no-store'}),d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||`Erreur ${r.status}`);return d}
 const duration=s=>{s=Number(s)||0;const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return d?`${d} j ${h} h`:h?`${h} h ${m} min`:`${m} min`};
 function render(d){
   const launch=d.launch||{},pub=d.public||{},db=d.database||{},storage=d.storage||{},ai=d.api||{},automod=d.automod||{};
   $('online34-score').textContent=`${launch.score||0}/100`;$('online34-ready').textContent=launch.ready?'Prêt à partager':'Corrections recommandées';
   $('online34-url').textContent=pub.url||'Non définie';$('online34-https').textContent=pub.https?'Actif ✓':'À activer';$('online34-server').textContent=`${d.server?.state||'online'} · PiChat ${d.version||''}`;
   $('online34-db').textContent=`${db.backend||'—'}${db.size_human?' · '+db.size_human:''}`;$('online34-storage').textContent=`${storage.backend||'—'}${storage.total_human?' · '+storage.total_human:''}`;
   $('online34-api').textContent=ai.configured?`${ai.provider||'OpenAI'} · configurée`:'Facultative';$('online34-automod').textContent=automod.enabled?'Actif':'Désactivé';$('online34-uptime').textContent=duration(d.uptime_seconds);
   $('online34-checks').innerHTML=(launch.checks||[]).map(c=>`<div class="online34-check ${c.ok?'ok':'bad'}"><span>${c.label}</span><b>${c.ok?'OK':'À corriger'}</b></div>`).join('')||'<p class="muted">Aucun diagnostic disponible.</p>';
 }
 async function load(){try{render(await api('/api/admin/pro'))}catch(e){const box=$('online34-checks');if(box)box.innerHTML=`<p class="error-message">${e.message}</p>`}}
 function bind(){window.addEventListener('pichat:ping',e=>{const el=$('online35-ping');if(el){const ms=Number(e.detail?.ms||0);el.textContent=ms?`${ms} ms · ${ms<=50?'objectif atteint ✓':ms<=110?'correct':'à optimiser'}`:'Mesure…'}});$('online34-refresh')?.addEventListener('click',load);document.querySelector('[data-tab="online34"]')?.addEventListener('click',load);if(location.hash==='#online34')load()}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
})();

;
/* ===== admin_launch31.js ===== */
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

;
/* ===== admin_railway.js ===== */
(()=>{const $=id=>document.getElementById(id);const api=async(u,o={})=>{const r=await fetch(u,{credentials:'same-origin',...o});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||`Erreur ${r.status}`);return d};let state=null;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));function render(d){state=d;$('railway-mode').textContent=d.railway_mode?'EN LIGNE':'PRÉPARATION';$('railway-mode').className=d.railway_mode?'online':'';$('railway-big-status').textContent=d.railway_mode&&d.public_url?'✓':'R';$('railway-url').textContent=d.public_url||'Le domaine apparaîtra ici après “Generate Domain” dans Railway.';$('railway-url').href=d.public_url||'#';$('railway-url').classList.toggle('online',!!d.public_url);$('railway-data-root').textContent=d.data_root||'—';$('railway-volume').textContent=d.volume_mount_path||'/app/data à configurer';$('railway-free').textContent=d.free_human||'—';$('railway-checks').innerHTML=(d.checks||[]).map(x=>`<article class="railway-check ${x.ok?'ok':''}"><span>${x.ok?'✓':'!'}</span><div><strong>${esc(x.label)}</strong><small>${esc(x.help)}</small></div></article>`).join('');$('railway-vars').textContent=d.variables||'';$('railway-runtime-box').hidden=!d.railway_mode;if(d.railway_mode){$('railway-runtime-info').textContent=`Service : ${d.service_name||'PiChat'} · données : ${d.data_root}`}}async function load(){try{render(await api('/api/admin/railway'));$('railway-error').hidden=true}catch(e){$('railway-error').textContent=e.message;$('railway-error').hidden=false}}async function bundle(prepare=false){const btn=$(prepare?'railway-prepare':'railway-bundle');btn.disabled=true;try{const d=await api(prepare?'/api/admin/railway/prepare':'/api/admin/railway/bundle',{method:'POST'});if(d.download_url){const a=document.createElement('a');a.href=d.download_url;a.download='';document.body.appendChild(a);a.click();a.remove()}$('railway-action').textContent=prepare?`✓ Backup ${d.backup_created} + paquet Railway créés.`:'✓ Paquet Railway prêt.';if(d.checks)render(d)}catch(e){$('railway-action').textContent=e.message}finally{btn.disabled=false}}async function copyVars(){try{const r=await fetch('/api/admin/railway/variables',{credentials:'same-origin'});const t=await r.text();if(!r.ok)throw new Error(t);await navigator.clipboard.writeText(t);$('railway-action').textContent='Variables Railway copiées ✓'}catch(e){$('railway-action').textContent='Copie impossible : '+e.message}}function bind(){$('railway-refresh')?.addEventListener('click',load);$('railway-bundle')?.addEventListener('click',()=>bundle(false));$('railway-prepare')?.addEventListener('click',()=>bundle(true));$('railway-copy-vars')?.addEventListener('click',copyVars);document.querySelector('.nav-item[data-tab="railway"]')?.addEventListener('click',load)}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind()})();
;
/* ===== pro31.js ===== */
(()=>{
  const $=id=>document.getElementById(id);
  const actions=[
    {label:'Chat',icon:'💬',run:()=>location.href='/'},
    {label:'Messages privés',icon:'✉️',run:()=>document.getElementById('open-direct-messages')?.click()},
    {label:'PiTutor+',icon:'📚',run:()=>document.getElementById('open-tutor')?.click()},
    {label:'Arcade & mini-jeux',icon:'🕹️',run:()=>document.getElementById('open-games')?.click()},
    {label:'PiGame Studio',icon:'🧪',run:()=>document.getElementById('open-game-studio')?.click()},
    {label:'Importer un jeu',icon:'📦',run:()=>{document.getElementById('open-game-studio')?.click();setTimeout(()=>{document.querySelector('[data-studio-tab="create"]')?.click();document.getElementById('studio-drop-zone')?.scrollIntoView({behavior:'smooth',block:'center'})},120)}},
    {label:'Profil gaming',icon:'🏅',run:()=>document.getElementById('open-gaming-profile')?.click()},
    {label:'PyCoins',icon:'🪙',run:()=>document.getElementById('open-economy')?.click()},
    {label:'Mon profil',icon:'👤',run:()=>document.getElementById('open-profile')?.click()},
    {label:'Personnalisation',icon:'🎨',run:()=>document.getElementById('open-personalization')?.click()},
    {label:'Établissements',icon:'🏫',run:()=>location.href='/spaces'},
    {label:'Railway Online',icon:'🌍',admin:true,run:()=>location.href='/admin#railway'},
    {label:'Administration',icon:'⚙️',admin:true,run:()=>location.href='/admin'},
  ];
  let modal,input,list;
  function available(){return actions.filter(a=>!a.admin||document.getElementById('admin-link')?.style.display!=='none')}
  function build(){if(modal)return;modal=document.createElement('div');modal.className='pro31-palette-backdrop';modal.id='pro31-palette';modal.innerHTML=`<section class="pro31-palette"><header><span>⌘K</span><input id="pro31-palette-input" placeholder="Ouvrir une fonction…" autocomplete="off"><button type="button">×</button></header><div id="pro31-palette-list"></div><footer>↑↓ naviguer · Entrée ouvrir · Échap fermer</footer></section>`;document.body.appendChild(modal);input=$('pro31-palette-input');list=$('pro31-palette-list');modal.addEventListener('click',e=>{if(e.target===modal)close()});modal.querySelector('button').addEventListener('click',close);input.addEventListener('input',render);input.addEventListener('keydown',key);render()}
  function render(){const q=(input?.value||'').trim().toLowerCase();const items=available().filter(a=>a.label.toLowerCase().includes(q));list.innerHTML=items.map((a,i)=>`<button type="button" data-i="${i}" class="${i===0?'active':''}"><span>${a.icon}</span><strong>${a.label}</strong><kbd>↵</kbd></button>`).join('')||'<p class="pro31-empty">Aucun raccourci.</p>';list.querySelectorAll('button').forEach((b,i)=>b.addEventListener('click',()=>{items[i].run();close()}));list._items=items}
  function key(e){const buttons=[...list.querySelectorAll('button')];let i=Math.max(0,buttons.findIndex(b=>b.classList.contains('active')));if(e.key==='ArrowDown'){e.preventDefault();buttons[i]?.classList.remove('active');i=(i+1)%buttons.length;buttons[i]?.classList.add('active');buttons[i]?.scrollIntoView({block:'nearest'})}else if(e.key==='ArrowUp'){e.preventDefault();buttons[i]?.classList.remove('active');i=(i-1+buttons.length)%buttons.length;buttons[i]?.classList.add('active');buttons[i]?.scrollIntoView({block:'nearest'})}else if(e.key==='Enter'){e.preventDefault();buttons[i]?.click()}else if(e.key==='Escape')close()}
  function open(){build();modal.classList.add('show');input.value='';render();setTimeout(()=>input.focus(),20)}
  function close(){modal?.classList.remove('show')}
  document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();open()}else if(e.key==='Escape'&&modal?.classList.contains('show'))close()});
  document.addEventListener('DOMContentLoaded',()=>{const btn=document.createElement('button');btn.type='button';btn.className='pro31-command-button';btn.textContent='⌘K';btn.title='Recherche rapide';btn.addEventListener('click',open);document.body.appendChild(btn)});
})();

;
/* ===== brand35.js ===== */
(() => {
  'use strict';
  const mascot='/assets/brand/pichat-mascot.svg?v=3500';
  function img(alt='PiChat'){const i=document.createElement('img');i.src=mascot;i.alt=alt;i.decoding='async';i.draggable=false;return i}
  function replaceMark(el){if(!el||el.dataset.p35Brand==='1')return;el.textContent='';el.append(img('Mascotte PiChat'));el.dataset.p35Brand='1'}
  function enhanceMarks(){document.querySelectorAll('.chat-logo,.brand-mark,.mini-logo,.mobile-logo').forEach(replaceMark)}
  function lockup(compact=false){const el=document.createElement('div');el.className='p35-brand-lockup';el.append(img('PiChat'));const c=document.createElement('div');c.className='p35-brand-copy';c.innerHTML='<span class="p35-wordmark">Pi<b>Chat</b></span>'+(compact?'':'<span class="p35-school">CHAVAGNES</span>');el.append(c);return el}
  function enhanceAuth(){
    document.querySelectorAll('.auth-card').forEach(card=>{if(card.querySelector('.auth-mobile-brand'))return;const b=lockup(true);b.classList.add('auth-mobile-brand');card.prepend(b)});
    document.querySelectorAll('.visual-content').forEach(v=>{if(v.querySelector('.auth-hero-logo'))return;const old=v.querySelector('.mini-logo');if(old)old.remove();const logo=document.createElement('img');logo.className='auth-hero-logo';logo.src='/assets/brand/pichat-logo.svg?v=3500';logo.alt='PiChat Chavagnes';v.prepend(logo)});
  }
  const states={
    1:['idle','Repos'],2:['idle','Clignement A'],3:['idle','Clignement B'],4:['curious','Regarde à gauche'],5:['curious','Regarde à droite'],6:['curious','Curieux'],7:['typing','Utilisateur écrit'],8:['typing','PiChat écrit A'],9:['typing','PiChat écrit B'],10:['typing','PiChat écrit C'],11:['happy','Nouveau message'],12:['happy','Mention'],13:['happy','Notification'],14:['curious','Réfléchit'],15:['typing','Chargement A'],16:['typing','Chargement B'],17:['typing','Chargement C'],18:['happy','Succès'],19:['happy','PyCoins'],20:['happy','Niveau supérieur'],21:['happy','Victoire gaming'],22:['error','Défaite gaming'],23:['error','Erreur'],24:['offline','Connexion perdue'],25:['curious','Reconnexion'],26:['happy','Retour en ligne'],27:['idle','Fatigué'],28:['idle','S’endort'],29:['idle','Dort'],30:['curious','Se réveille'],31:['happy','Réveillé !'],32:['curious','Tap / touché'],33:['happy','Content d’être touché'],34:['curious','Tap répété'],35:['error','Beaucoup trop de taps'],36:['happy','Coucou'],37:['happy','Cœur'],38:['dance-a','Danse A'],39:['dance-b','Danse B'],40:['dance-c','Danse C'],41:['curious','Mode admin'],42:['error','AutoModo alert'],43:['happy','PiGame'],44:['curious','PiTutor'],45:['curious','Secret / Easter egg'],46:['error','WTF / bug étrange'],47:['happy','Popcorn'],48:['idle','Mini Bot caché']
  };
  const symbols={typing:'…',curious:'?',happy:'✦',error:'!',offline:'⌁','dance-a':'♪','dance-b':'♫','dance-c':'♪',idle:''};
  let tapCount=0,tapTimer=null,restoreTimer=null;
  function ensureBot(){
    if(document.getElementById('p35-mini-bot'))return;
    const b=document.createElement('button');b.id='p35-mini-bot';b.type='button';b.dataset.state='idle';b.setAttribute('aria-label','Mini Bot PiChat');b.title='Mini Bot PiChat';
    b.innerHTML='<span class="p35-bot-head"><i class="p35-bot-earpad l"></i><i class="p35-bot-earpad r"></i><span class="p35-bot-face"><i class="p35-bot-eye l"></i><i class="p35-bot-eye r"></i><i class="p35-bot-mouth"></i></span><span class="p35-bot-symbol"></span></span>';
    const tip=document.createElement('div');tip.className='p35-bot-tip';tip.id='p35-bot-tip';tip.textContent='PiChat 3.5 · Mini Bot';document.body.append(b,tip);
    b.addEventListener('click',()=>{tapCount++;clearTimeout(tapTimer);tapTimer=setTimeout(()=>tapCount=0,1700);setState(tapCount>=4?35:tapCount===3?34:tapCount===2?33:32,1100)});
  }
  function setState(state,duration=0){
    ensureBot();let key=state,label='';if(typeof state==='number'){[key,label]=states[state]||states[1]}else{key=String(state||'idle');label=key}
    const b=document.getElementById('p35-mini-bot'),s=b.querySelector('.p35-bot-symbol'),tip=document.getElementById('p35-bot-tip');b.dataset.state=key;s.textContent=symbols[key]??'✦';tip.textContent=label;tip.classList.add('visible');clearTimeout(restoreTimer);if(duration)restoreTimer=setTimeout(()=>{tip.classList.remove('visible');b.dataset.state=navigator.onLine?'idle':'offline';s.textContent=symbols[b.dataset.state]||''},duration);else setTimeout(()=>tip.classList.remove('visible'),850)
  }
  function bindAutoStates(){
    addEventListener('offline',()=>setState(24,1500));addEventListener('online',()=>setState(26,1500));
    addEventListener('pichat:ping',e=>{const ms=Number(e.detail?.ms||999);if(ms>180)setState(23,900)});
    addEventListener('pichat:new-message',()=>setState(11,800));
    addEventListener('pichat:automod-alert',()=>setState(42,1200));
    const input=document.getElementById('message-input');if(input)input.addEventListener('input',()=>{if(input.value.trim())setState(7,500)});
    if(location.pathname.startsWith('/admin'))setState(41,1200);
  }
  function init(){enhanceMarks();enhanceAuth();ensureBot();bindAutoStates();document.documentElement.dataset.pichatVersion='3.5.0'}
  window.PiChatMiniBot={setState,states};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();

;
/* ===== performance35.js ===== */
(() => {
  'use strict';
  const TARGET=50, samples=[];
  let timer=null, active=true, wsActiveUntil=0;
  function ensurePill(){
    let pill=document.getElementById('ping-status');if(pill)return pill;
    pill=document.createElement('span');pill.id='ping-status';pill.className='p35-ping-pill';pill.innerHTML='<i class="p35-ping-dot"></i><span>Ping…</span>';
    const ws=document.getElementById('ws-status');if(ws?.parentNode)ws.after(pill);else{const wrap=document.createElement('div');wrap.className='p35-ping-floating';wrap.append(pill);document.body.append(wrap)}return pill;
  }
  function record(ms,source='http'){
    if(String(source).toLowerCase().includes('websocket'))wsActiveUntil=Date.now()+15000;
    ms=Math.max(0,Math.round(Number(ms)||0));if(!ms)return;
    samples.push(ms);if(samples.length>8)samples.shift();const median=[...samples].sort((a,b)=>a-b)[Math.floor(samples.length/2)];const value=Math.round(median);
    const pill=ensurePill();const cls=value<=TARGET?'good':value<=110?'ok':'slow';pill.className='p35-ping-pill '+cls;pill.innerHTML=`<i class="p35-ping-dot"></i><span>${value} ms</span><small class="p35-perf-mode">objectif &lt;${TARGET}</small>`;pill.title=`Latence ${source} · médiane des ${samples.length} dernières mesures`;
    window.dispatchEvent(new CustomEvent('pichat:ping',{detail:{ms:value,raw:ms,target:TARGET,source}}));
  }
  async function httpPing(){
    if(!active||document.hidden||Date.now()<wsActiveUntil)return;const start=performance.now();
    try{const r=await fetch('/api/ping?ts='+Date.now(),{cache:'no-store',credentials:'same-origin'});if(r.ok)record(performance.now()-start,'HTTP')}
    catch(_){const p=ensurePill();p.className='p35-ping-pill slow';p.innerHTML='<i class="p35-ping-dot"></i><span>Hors ligne</span>'}
  }
  function start(){ensurePill();httpPing();clearInterval(timer);timer=setInterval(httpPing,12000)}
  document.addEventListener('visibilitychange',()=>{active=!document.hidden;if(active)httpPing()});
  window.PiChatPerf35={record,httpPing,target:TARGET};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();

