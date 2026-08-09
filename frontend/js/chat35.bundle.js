/* ===== app.js ===== */
let CURRENT_USER = null;

document.addEventListener("DOMContentLoaded", () => {
  checkServerStatus();
  checkAuthentication();
});

async function checkAuthentication(){
  try{
    const response=await fetch('/api/me',{credentials:'same-origin',cache:'no-store'});
    if(!response.ok){location.href='/login';return;}
    CURRENT_USER=await response.json();
    window.CURRENT_USER=CURRENT_USER;
    displayUserInfo(CURRENT_USER);
  }catch(e){console.error('Session PiChat',e);}
}

function initials(name){return (name||'?').slice(0,2).toUpperCase()}

function displayUserInfo(user){
  const box=document.getElementById('user-info');
  const name=document.getElementById('username-display');
  const avatar=document.getElementById('me-avatar');
  const status=document.getElementById('me-status');
  const admin=document.getElementById('admin-link');
  const moderation=document.getElementById('moderation-link');
  const section=document.getElementById('chat-section');
  name.textContent=user.username;
  avatar.textContent=initials(user.username);
  if(user.profile_color) avatar.style.background=user.profile_color;
  status.textContent=user.status_message || (user.role_label ? user.role_label : 'En ligne');
  box.style.display='flex'; section.style.display='grid';
  document.getElementById('mobile-bottom-nav').style.display='grid';
  if(user.is_admin) admin.style.display='grid';
  if(user.is_admin||user.is_moderator) moderation.style.display='grid';
  document.getElementById('logout-button').addEventListener('click',handleLogout);
  initChat();
  loadAIStatus();
  window.dispatchEvent(new CustomEvent('pichat:user-ready',{detail:user}));
}

async function handleLogout(){
  if(CURRENT_USER?.support_mode){
    try{await fetch('/api/support/end',{method:'POST',credentials:'same-origin'});}catch{}
    location.href='/admin#users';return;
  }
  try{await fetch('/api/logout',{method:'POST',credentials:'same-origin'});}catch{}
  location.href='/login';
}

async function checkServerStatus(){
  const box=document.getElementById('server-status');
  try{
    const r=await fetch('/api/health',{cache:'no-store'}); if(!r.ok) throw new Error(r.status);
    const d=await r.json(); box.textContent=`${d.app} v${d.version} opérationnel`;box.className='server-status-hidden ok';
  }catch(e){box.textContent='Serveur indisponible';box.className='server-status-hidden error';}
}

async function loadAIStatus(){
  try{
    const r=await fetch('/api/ai/status',{cache:'no-store'});if(!r.ok)return;
    const s=await r.json();const input=document.getElementById('message-input');
    if(input&&s.enabled)input.placeholder=`Message…  @${s.trigger_name} pour appeler l’IA`;
  }catch{}
}

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
/* ===== websocket.js ===== */
let chatSocket=null;
let currentRoomId=null;
let CURRENT_ROOMS=[];
let profanityFilter={enabled:false,words:[]};
let historyHasMore=false;
let historyLoading=false;
let oldestMessageId=null;
let unreadMessageCount=0;
let autoLoadOlderTimer=null;
let pendingReplyMessage=null;
let reconnectTimer=null;
let socketGeneration=0;
let queuedChatMessages=[];
let sendFormBound=false;
let p35PingTimer=null;
let p35PingSeq=0;
const p35PendingPings=new Map();

async function loadProfanityFilter(){try{const r=await fetch('/api/moderation/filter',{credentials:'same-origin'});if(r.ok)profanityFilter=await r.json()}catch{}}
function escapeRegex(s){return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}
function appendFilteredText(container,text){
  if(!profanityFilter.enabled||!profanityFilter.words?.length){container.textContent=text;return}
  const words=profanityFilter.words.filter(Boolean).sort((a,b)=>b.length-a.length).map(escapeRegex);if(!words.length){container.textContent=text;return}
  const re=new RegExp(`(${words.join('|')})`,'giu');let last=0;
  for(const m of String(text).matchAll(re)){if(m.index>last)container.append(document.createTextNode(text.slice(last,m.index)));const span=document.createElement('span');span.className='profanity-blur';span.textContent=m[0];span.title='Cliquer pour révéler';span.onclick=()=>span.classList.toggle('revealed');container.append(span);last=m.index+m[0].length}
  if(last<text.length)container.append(document.createTextNode(text.slice(last)));
}
function escText(s){return String(s??'')}
function initials(name){return (name||'?').slice(0,2).toUpperCase()}

async function initChat(){
  bindSendForm();
  await loadProfanityFilter();
  const rooms=await loadRoomList();
  if(!rooms.length){
    updateComposerConnection('Aucun salon disponible','error');
    return;
  }
  bindMessageNavigation();
  const requested=Number(new URLSearchParams(location.search).get('room'));
  const first=rooms.find(r=>Number(r.id)===requested)||rooms[0];
  await switchRoom(first.id);
}

async function loadRoomList(){
  try{
    const r=await fetch('/api/rooms',{credentials:'same-origin',cache:'no-store'});if(!r.ok)return[];
    CURRENT_ROOMS=await r.json();window.CURRENT_ROOMS=CURRENT_ROOMS;
    const selector=document.getElementById('room-selector');selector.innerHTML='';
    const rail=document.getElementById('server-list');const channels=document.getElementById('channel-list');rail.innerHTML='';channels.innerHTML='';
    CURRENT_ROOMS.forEach((room,idx)=>{
      const option=document.createElement('option');option.value=room.id;option.textContent=room.name;selector.append(option);
      const icon=document.createElement('button');icon.className='server-icon room-server';icon.dataset.roomId=room.id;icon.title=room.class_code?`Serveur ${room.class_code}`:room.name;icon.textContent=room.room_kind==='custom'?(room.icon||'💬'):(room.class_code?room.class_code.slice(0,3).toUpperCase():'#');icon.onclick=()=>switchRoom(room.id);rail.append(icon);
      const ch=document.createElement('button');ch.className='channel-button';ch.dataset.roomId=room.id;ch.innerHTML='<span class="hash">#</span><span></span>';ch.querySelector('span:last-child').textContent=room.room_kind==='custom'?`${room.icon||'💬'} ${room.name}`:(room.class_code?`${room.name} · ${room.class_code}`:room.name);ch.onclick=()=>switchRoom(room.id);channels.append(ch);
    });
    return CURRENT_ROOMS;
  }catch(e){console.error('Salons',e);return[]}
}

function roomById(id){return CURRENT_ROOMS.find(r=>Number(r.id)===Number(id))}
function setActiveRoomUI(roomId){
  document.getElementById('room-selector').value=String(roomId);
  document.querySelectorAll('[data-room-id]').forEach(el=>el.classList.toggle('active',Number(el.dataset.roomId)===Number(roomId)));
  const room=roomById(roomId);if(!room)return;
  document.getElementById('current-room-name').textContent=room.name;
  document.getElementById('current-room-topic').textContent=room.room_kind==='custom'?(room.description||'Serveur personnel sur invitation'):(room.class_code?`Serveur privé de la classe ${room.class_code}`:'Discussion générale de PiChat');
  document.getElementById('message-input').placeholder=`Envoyer un message dans #${room.name}`;
}

async function switchRoom(roomId){
  currentRoomId=Number(roomId);window.currentRoomId=currentRoomId;setActiveRoomUI(currentRoomId);window.PiChatPWA?.onRoomChanged?.(currentRoomId);
  const list=document.getElementById('messages-list');list.innerHTML='';resetHistoryState();
  clearTimeout(reconnectTimer);reconnectTimer=null;
  socketGeneration+=1;
  const previous=chatSocket;chatSocket=null;
  if(previous){try{previous.close()}catch{}}
  updateComposerConnection('Connexion au salon…','connecting');
  await loadMessageHistory(currentRoomId);connectWebSocket(currentRoomId,socketGeneration);
  if(window.PiChatCommunity?.onRoomChanged)window.PiChatCommunity.onRoomChanged(currentRoomId);
}

async function loadMessageHistory(roomId){
  try{
    const r=await fetch(`/api/messages/history?room_id=${roomId}&limit=60`,{credentials:'same-origin',cache:'no-store'});
    if(!r.ok)return;
    const d=await r.json();
    d.messages.forEach(appendMessageToChat);
    historyHasMore=!!d.has_more;oldestMessageId=d.oldest_id||null;updateHistoryControls();
    requestAnimationFrame(()=>scrollToBottom(false));
  }catch(e){console.error('Historique',e)}
}

async function loadOlderMessages(){
  if(historyLoading||!historyHasMore||!oldestMessageId||!currentRoomId)return;
  historyLoading=true;updateHistoryControls();
  const list=document.getElementById('messages-list');const oldHeight=list.scrollHeight;const oldTop=list.scrollTop;
  try{
    const r=await fetch(`/api/messages/history?room_id=${currentRoomId}&before_id=${oldestMessageId}&limit=60`,{credentials:'same-origin',cache:'no-store'});
    if(!r.ok)throw new Error('Historique indisponible');
    const d=await r.json();
    const fragment=document.createDocumentFragment();d.messages.forEach(m=>fragment.append(buildMessageElement(m)));
    list.prepend(fragment);historyHasMore=!!d.has_more;oldestMessageId=d.oldest_id||oldestMessageId;
    requestAnimationFrame(()=>{list.scrollTop=oldTop+(list.scrollHeight-oldHeight);});
  }catch(e){window.PiChatTrolls?.toast?.(e.message||String(e))}
  finally{historyLoading=false;updateHistoryControls()}
}

function connectWebSocket(roomId,generation=socketGeneration){
  if(!roomId || generation!==socketGeneration)return;
  clearTimeout(reconnectTimer);reconnectTimer=null;
  const protocol=location.protocol==='https:'?'wss:':'ws:';
  const socket=new WebSocket(`${protocol}//${location.host}/ws?room_id=${roomId}`);
  chatSocket=socket;
  socket.addEventListener('open',()=>{
    if(generation!==socketGeneration||Number(roomId)!==Number(currentRoomId)||chatSocket!==socket){try{socket.close()}catch{};return}
    updateWsStatus('En ligne','connected');
    updateComposerConnection('Prêt à envoyer','connected');
    startP35SocketPing(socket,generation);
    flushQueuedMessages();
  });
  socket.addEventListener('close',()=>{
    if(generation!==socketGeneration||Number(roomId)!==Number(currentRoomId)||chatSocket!==socket)return;
    chatSocket=null;
    stopP35SocketPing();
    updateWsStatus('Reconnexion…','disconnected');
    window.PiChatMiniBot?.setState?.(24,1200);
    updateComposerConnection(queuedChatMessages.some(x=>Number(x.room_id)===Number(roomId))?'Message en attente — reconnexion…':'Reconnexion au chat…','connecting');
    reconnectTimer=setTimeout(()=>connectWebSocket(roomId,generation),1200);
  });
  socket.addEventListener('error',e=>{console.error('WebSocket',e);updateComposerConnection('Connexion instable — nouvelle tentative…','error')});
  socket.addEventListener('message',event=>{try{handleIncomingMessage(JSON.parse(event.data))}catch(e){console.error(e)}});
}

function updateComposerConnection(text,state=''){
  const button=document.getElementById('message-send-button')||document.querySelector('#message-form .send-button');
  const status=document.getElementById('composer-send-status');
  if(button){
    button.dataset.state=state;
    button.title=text||'Envoyer';
    button.setAttribute('aria-label',text||'Envoyer le message');
  }
  if(status){status.textContent=text||'';status.dataset.state=state}
}

function flushQueuedMessages(){
  if(!chatSocket||chatSocket.readyState!==WebSocket.OPEN||!currentRoomId)return;
  const keep=[];
  for(const item of queuedChatMessages){
    if(Number(item.room_id)!==Number(currentRoomId)){keep.push(item);continue}
    try{chatSocket.send(JSON.stringify({content:item.content,reply_to_id:item.reply_to_id||null}))}
    catch{keep.push(item);continue}
  }
  const sent=queuedChatMessages.length-keep.length;
  queuedChatMessages=keep;
  if(sent){clearRoomReply();updateComposerConnection(`${sent} message${sent>1?'s':''} envoyé${sent>1?'s':''} ✓`,'connected');setTimeout(()=>updateComposerConnection('Prêt à envoyer','connected'),1600)}
}

function queueChatMessage(content,replyToId){
  if(!currentRoomId)return false;
  if(queuedChatMessages.length>=20){window.PiChatTrolls?.toast?.('Trop de messages en attente. Attends la reconnexion.');updateComposerConnection('File d’attente pleine','error');return false}
  queuedChatMessages.push({room_id:Number(currentRoomId),content,reply_to_id:replyToId||null,queued_at:Date.now()});
  updateComposerConnection('Message mis en attente — reconnexion…','connecting');
  if(!chatSocket||chatSocket.readyState===WebSocket.CLOSED)connectWebSocket(currentRoomId,socketGeneration);
  return true;
}

function handleIncomingMessage(data){
  if(data.type==='pong'){recordP35SocketPong(data);return}
  if(data.type==='new_message'){window.dispatchEvent(new CustomEvent('pichat:new-message',{detail:data.message}));const follow=isNearBottom();appendMessageToChat(data.message);if(follow||Number(data.message.user_id)===Number(window.CURRENT_USER?.id))scrollToBottom(true);else{unreadMessageCount+=1;updateScrollLatestButton();}}
  else if(data.type==='message_updated'){replaceMessage(data.message);}
  else if(data.type==='reactions_updated'){updateReactionRow(data.message_id,data.reactions||[]);}
  else if(data.type==='user_joined'){appendSystemMessage(`${data.username} est arrivé`);window.PiChatCommunity?.refreshMembers?.();}
  else if(data.type==='user_left'){appendSystemMessage(`${data.username} est parti`);window.PiChatCommunity?.refreshMembers?.();}
  else if(data.type==='message_deleted'){document.querySelector(`[data-message-id="${data.message_id}"]`)?.remove();}
  else if(data.type==='moderation_notice'){appendSystemMessage(data.message||'Message de modération.');window.PiChatTrolls?.toast?.(data.message||'Message de modération.');}
  else if(data.type==='system_notice'){appendSystemMessage(data.message||'Information.');window.PiChatTrolls?.toast?.(data.message||'Information.');}
  else if(data.type==='direct_message'||data.type==='direct_message_updated'){window.dispatchEvent(new CustomEvent('pichat:dm-event',{detail:data}));}
  else if(data.type==='forced_logout'){alert(data.reason||'Ton accès à PiChat a été retiré.');location.href='/login';}
}

function startP35SocketPing(socket,generation){
  stopP35SocketPing();
  const send=()=>{
    if(generation!==socketGeneration||chatSocket!==socket||socket.readyState!==WebSocket.OPEN)return;
    const nonce=`${Date.now().toString(36)}-${++p35PingSeq}`;
    p35PendingPings.set(nonce,performance.now());
    try{socket.send(JSON.stringify({type:'ping',client_ts:Date.now(),nonce}))}catch{}
    // Oublie les vieux pings pour ne jamais accumuler de mémoire.
    for(const [key,started] of p35PendingPings){if(performance.now()-started>30000)p35PendingPings.delete(key)}
  };
  send();p35PingTimer=setInterval(send,5000);
}
function stopP35SocketPing(){if(p35PingTimer){clearInterval(p35PingTimer);p35PingTimer=null}p35PendingPings.clear()}
function recordP35SocketPong(data){
  const started=p35PendingPings.get(data.nonce);if(started==null)return;
  p35PendingPings.delete(data.nonce);const ms=performance.now()-started;
  window.PiChatPerf35?.record?.(ms,'WebSocket');
}

function updateWsStatus(text,cls){const x=document.getElementById('ws-status');x.textContent=text;x.className='ws-pill '+cls}

function avatarFor(message){
  const a=document.createElement('span');a.className='avatar message-avatar';a.textContent=initials(message.username);if(message.profile_color)a.style.background=message.profile_color;
  if(message.username==='PiAI')a.style.background='linear-gradient(135deg,#a970ff,#5865f2)';
  else if(/^AutoModo/i.test(message.username||''))a.style.background='linear-gradient(135deg,#ed4245,#b72c30)';
  else if(message.is_bot)a.style.background='linear-gradient(135deg,#23a559,#1abc9c)';
  a.onclick=()=>window.PiChatCommunity?.openPublicProfile?.(message.user_id);return a;
}
function badgeFor(message){
  if(message.username==='PiAI'){const b=document.createElement('span');b.className='message-grade-badge grade-ai';b.textContent='✦ IA';return b}
  if(/^AutoModo/i.test(message.username||'')){const b=document.createElement('span');b.className='message-grade-badge grade-automod';b.textContent='AUTO MOD';return b}
  if(message.is_bot){const b=document.createElement('span');b.className='message-grade-badge grade-bot';b.textContent='BOT';return b}
  if(!message.role_label)return null;
  const b=document.createElement('span');b.className='message-grade-badge grade-'+(message.role||'player');b.textContent=message.role_label;if(message.grade_color){b.style.color=message.grade_color;b.style.borderColor=message.grade_color}return b;
}

function appendMessageToChat(message){
  const list=document.getElementById('messages-list');const item=buildMessageElement(message);list.append(item);
}
function replaceMessage(message){const old=document.querySelector(`[data-message-id="${message.id}"]`);const next=buildMessageElement(message);if(old)old.replaceWith(next);else document.getElementById('messages-list').append(next)}

function buildMessageElement(message){
  const item=document.createElement('article');item.className='message-item role-'+(message.role||'player');item.dataset.messageId=message.id;
  if(message.username==='PiAI')item.classList.add('ai-message');if(message.is_bot)item.classList.add('bot-message');
  item.append(avatarFor(message));
  const main=document.createElement('div');main.className='message-main';
  const header=document.createElement('div');header.className='message-header';const author=document.createElement('span');author.className='message-author';author.textContent=message.username;author.onclick=()=>window.PiChatCommunity?.openPublicProfile?.(message.user_id);header.append(author);const badge=badgeFor(message);if(badge)header.append(badge);const time=document.createElement('span');time.className='message-time';time.textContent=formatTime(message.created_at);header.append(time);if(message.edited_at){const edited=document.createElement('span');edited.className='message-edited';edited.textContent='(modifié)';header.append(edited)}if(message.is_pinned){const pin=document.createElement('span');pin.className='message-pin-badge';pin.textContent='📌';pin.title='Message épinglé';header.append(pin)}main.append(header);
  if(message.reply){const reply=document.createElement('button');reply.className='message-reply-preview';reply.innerHTML='<strong></strong><span></span>';reply.querySelector('strong').textContent='↪ '+message.reply.username;reply.querySelector('span').textContent=message.reply.content;reply.onclick=()=>document.querySelector(`[data-message-id="${message.reply.id}"]`)?.scrollIntoView({behavior:'smooth',block:'center'});main.append(reply)}
  if(message.message_type&&message.message_type!=='text')main.append(renderSpecialCard(message));else{const content=document.createElement('div');content.className='message-content';appendFilteredText(content,message.content);main.append(content)}
  const reactions=document.createElement('div');reactions.className='reaction-row';reactions.dataset.reactionsFor=message.id;renderReactions(reactions,message.reactions||[],message.id);main.append(reactions);item.append(main);
  const actions=document.createElement('div');actions.className='message-actions';
  const reply=document.createElement('button');reply.textContent='↩';reply.title='Répondre';reply.onclick=()=>setRoomReply(message);actions.append(reply);
  const react=document.createElement('button');react.textContent='☺';react.title='Réagir';react.onclick=e=>showEmojiPopover(e.currentTarget,message.id);actions.append(react);
  if(Number(message.user_id)===Number(window.CURRENT_USER?.id)){const edit=document.createElement('button');edit.textContent='✎';edit.title='Modifier';edit.onclick=()=>editRoomMessage(message);actions.append(edit)}
  if(Number(message.user_id)===Number(window.CURRENT_USER?.id)||window.CURRENT_USER?.is_admin||window.CURRENT_USER?.is_moderator){const del=document.createElement('button');del.textContent='🗑';del.title='Supprimer';del.onclick=()=>deleteRoomMessage(message);actions.append(del)}
  if(window.CURRENT_USER?.is_admin||window.CURRENT_USER?.is_moderator){const pin=document.createElement('button');pin.textContent=message.is_pinned?'📍':'📌';pin.title=message.is_pinned?'Désépingler':'Épingler';pin.onclick=()=>toggleRoomPin(message);actions.append(pin)}
  const report=document.createElement('button');report.textContent='⚑';report.title='Signaler';report.onclick=()=>reportMessage(message.id);actions.append(report);item.append(actions);
  return item;
}

function renderSpecialCard(message){
  const m=message.metadata||{};const card=document.createElement('div');card.className='message-card card-'+message.message_type;
  if(message.message_type==='duel'){card.classList.add('duel-card');renderDuelCard(card,m);return card}
  if(message.message_type==='file'){renderFileCard(card,m,message);return card}
  if(message.message_type==='python_code'){renderPythonCodeCard(card,m,message);return card}
  if(message.message_type==='poll'){const h=document.createElement('h4');h.textContent='📊 '+(m.question||message.content);card.append(h);(m.options||[]).forEach((o,i)=>{const row=document.createElement('div');row.className='poll-option';const btn=document.createElement('button');btn.className='reaction-chip';btn.textContent=(m.emojis?.[i]||`${i+1}.`);btn.onclick=()=>reactToMessage(message.id,m.emojis?.[i]||String(i+1));const t=document.createElement('span');t.textContent=o;row.append(btn,t);card.append(row)});return card}
  if(message.message_type==='stats'){const h=document.createElement('h4');h.textContent='🏆 '+(m.username||message.content);card.append(h);const grid=document.createElement('div');grid.className='stats-grid';[['Niveau',m.level||1],['XP',m.xp||0],['PiCoins',m.coins||0],['V/D',`${m.wins||0}/${m.losses||0}`]].forEach(([k,v])=>{const d=document.createElement('div');const b=document.createElement('b');b.textContent=v;const s=document.createElement('small');s.textContent=k;d.append(b,s);grid.append(d)});card.append(grid);return card}
  const h=document.createElement('h4');h.textContent=iconForType(message.message_type)+' '+titleForType(message.message_type);const p=document.createElement('p');appendFilteredText(p,message.content);card.append(h,p);
  if(message.message_type==='eightball'&&m.question){const s=document.createElement('small');s.textContent='Question : '+m.question;card.append(s)}
  return card;
}
function iconForType(t){return({dice:'🎲',coin:'🪙',rps:'✋',eightball:'🎱',choice:'🎯',game_notice:'🎮',game_help:'🕹',automod:'🛡️',file:'📎',python_code:'🐍'})[t]||'✦'}
function titleForType(t){return({dice:'Lancer de dé',coin:'Pile ou face',rps:'Pierre · Feuille · Ciseaux',eightball:'Boule magique',choice:'Choix de PiGame',game_notice:'PiGame',game_help:'Commandes PiGame',automod:'AutoModo',file:'Fichier',python_code:'PiCode Python'})[t]||'PiGame'}


function renderPythonCodeCard(card,m,message){
  card.classList.add('python-code-card');
  const head=document.createElement('div');head.className='python-code-head';
  const title=document.createElement('h4');title.textContent='🐍 '+(m.title||message.content||'Mini-code Python');
  const copy=document.createElement('button');copy.textContent='Copier le code';copy.onclick=async()=>{try{await navigator.clipboard.writeText(m.code||'');copy.textContent='Copié ✓';setTimeout(()=>copy.textContent='Copier le code',1400)}catch{prompt('Copie le code :',m.code||'')}};
  head.append(title,copy);card.append(head);
  const pre=document.createElement('pre');pre.className='python-code-block';const code=document.createElement('code');code.textContent=m.code||'# Aucun code';pre.append(code);card.append(pre);
  if(m.explanation){const p=document.createElement('p');p.className='python-code-explanation';p.textContent=m.explanation;card.append(p)}
  const meta=document.createElement('div');meta.className='python-code-meta';meta.innerHTML=`<span>${m.provider==='openai'?'IA OpenAI':'Mode local'}</span><span>${m.lines||0} ligne(s)</span><span>${m.cost||0} PyCoins</span><span>Validation sécurité ✓</span>`;card.append(meta);
  const warning=document.createElement('div');warning.className='python-code-warning';warning.textContent='⚠️ Code non exécuté par PiChat. Lis-le et demande à un adulte/enseignant avant de l’exécuter ailleurs.';card.append(warning);
}

function formatFileSize(bytes){
  bytes=Number(bytes||0);if(bytes<1024)return `${bytes} o`;if(bytes<1024*1024)return `${(bytes/1024).toFixed(1)} Ko`;return `${(bytes/1024/1024).toFixed(1)} Mo`;
}
function renderFileCard(card,m,message){
  card.classList.add('file-card');
  const mime=String(m.mime||'');
  if(mime.startsWith('image/')&&m.url){
    const a=document.createElement('a');a.href=m.url;a.target='_blank';a.rel='noopener';
    const img=document.createElement('img');img.src=m.url;img.alt=m.name||'Image envoyée';img.loading='lazy';a.append(img);card.append(a);return;
  }
  const icon=document.createElement('span');icon.className='file-icon';icon.textContent=mime.includes('pdf')?'📕':mime.includes('zip')?'🗜️':'📄';
  const info=document.createElement('span');info.className='file-info';const name=document.createElement('strong');name.textContent=m.name||message.content||'Fichier';const meta=document.createElement('small');meta.textContent=`${formatFileSize(m.size)}${mime?' · '+mime:''}`;info.append(name,meta);
  const link=document.createElement('a');link.href=m.url||'#';link.target='_blank';link.rel='noopener';link.download=m.name||'';link.textContent='Télécharger';
  card.append(icon,info,link);
}

function renderDuelCard(card,m){
  const title=document.createElement('h4');title.textContent='⚔️ DUEL';card.append(title);
  const head=document.createElement('div');head.className='duel-head';const a=document.createElement('span');a.textContent=`${m.challenger_rpg?.class_icon||'⚔️'} ${m.challenger||'?'} · ${m.challenger_hp??100} PV · ✨${m.challenger_energy??3}`;const b=document.createElement('span');b.textContent=`${m.opponent_rpg?.class_icon||'⚔️'} ${m.opponent||'?'} · ${m.opponent_hp??100} PV · ✨${m.opponent_energy??3}`;head.append(a,b);card.append(head);if((m.challenger_guard||0)||(m.opponent_guard||0)){const guard=document.createElement('small');guard.textContent=`Protections : ${m.challenger||'?'} ${m.challenger_guard||0} · ${m.opponent||'?'} ${m.opponent_guard||0}`;card.append(guard)}
  [m.challenger_hp??100,m.opponent_hp??100].forEach(hp=>{const line=document.createElement('div');line.className='hp-line';const fill=document.createElement('span');fill.style.width=Math.max(0,hp)+'%';if(hp<35)fill.style.background='#f23f43';else if(hp<65)fill.style.background='#f0b232';line.append(fill);card.append(line)});
  const state=document.createElement('p');state.textContent=m.status==='pending'?'Défi en attente':m.status==='active'?`Tour : ${m.turn_user_id===m.challenger_id?m.challenger:m.opponent}`:m.status==='finished'?`🏆 Gagnant : ${m.winner_id===m.challenger_id?m.challenger:m.opponent}`:'Duel refusé';card.append(state);
  const log=document.createElement('div');log.className='duel-log';(m.log||[]).forEach(x=>{const d=document.createElement('div');d.textContent=x;log.append(d)});card.append(log);
  const actions=document.createElement('div');actions.className='card-actions';const me=window.CURRENT_USER?.id;
  const add=(label,action,cls='')=>{const btn=document.createElement('button');btn.textContent=label;if(cls)btn.className=cls;btn.onclick=()=>duelAction(m.duel_id,action);actions.append(btn)};
  if(m.status==='pending'&&me===m.opponent_id){add('✅ Accepter','accept');add('Refuser','decline','secondary')}
  if(m.status==='active'&&[m.challenger_id,m.opponent_id].includes(me)){if(me===m.turn_user_id){add('⚔️ Attaque','attack');add('🛡 Défense','defend');add('✨ Spécial','special');add('💥 Risqué','risky');add('💚 Soin','heal')}add('🏳 Abandon','forfeit','danger')}
  if(actions.children.length)card.append(actions);
}
async function duelAction(id,action){try{const r=await fetch(`/api/games/duels/${id}/action`,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({action})});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Action refusée')}catch(e){window.PiChatTrolls?.toast?.(e.message||String(e))}}

function renderReactions(row,reactions,messageId){row.innerHTML='';(reactions||[]).forEach(r=>{const b=document.createElement('button');b.className='reaction-chip';b.textContent=`${r.emoji} ${r.count}`;b.onclick=()=>reactToMessage(messageId,r.emoji);row.append(b)})}
function updateReactionRow(messageId,reactions){const row=document.querySelector(`[data-reactions-for="${messageId}"]`);if(row)renderReactions(row,reactions,messageId)}
async function reactToMessage(messageId,emoji){try{await fetch(`/api/messages/${messageId}/reaction`,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({emoji})})}catch{}}
function showEmojiPopover(anchor,messageId){document.querySelector('.emoji-popover')?.remove();const p=document.createElement('div');p.className='emoji-popover';['👍','❤️','😂','🔥','🎉','🤔','💀'].forEach(e=>{const b=document.createElement('button');b.textContent=e;b.onclick=()=>{reactToMessage(messageId,e);p.remove()};p.append(b)});document.body.append(p);const r=anchor.getBoundingClientRect();p.style.left=Math.min(innerWidth-260,r.left-120)+'px';p.style.top=Math.max(8,r.top-50)+'px';setTimeout(()=>document.addEventListener('click',ev=>{if(!p.contains(ev.target))p.remove()},{once:true}),0)}
async function reportMessage(messageId){const reason=prompt('Pourquoi signales-tu ce message ? (facultatif)')??null;if(reason===null)return;try{const r=await fetch(`/api/messages/${messageId}/report`,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({reason})});if(r.ok)window.PiChatTrolls?.toast?.('Signalement envoyé aux modérateurs.')}catch{}}
function showEmojiComposer(anchor){document.querySelector('.emoji-popover')?.remove();const p=document.createElement('div');p.className='emoji-popover';['😀','😂','❤️','👍','🔥','🎉','🤔','💀','✨'].forEach(e=>{const b=document.createElement('button');b.textContent=e;b.onclick=()=>{const input=document.getElementById('message-input');input.value+=e;input.focus();p.remove()};p.append(b)});document.body.append(p);const r=anchor.currentTarget.getBoundingClientRect();p.style.left=Math.max(8,Math.min(innerWidth-300,r.left-180))+'px';p.style.top=Math.max(8,r.top-56)+'px';setTimeout(()=>document.addEventListener('click',ev=>{if(!p.contains(ev.target))p.remove()},{once:true}),0)}

function appendSystemMessage(text){const d=document.createElement('div');d.className='system-message';d.textContent=text;document.getElementById('messages-list').append(d)}
function formatTime(s){try{return new Date(s.replace(' ','T')+'Z').toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}catch{return''}}
function resetHistoryState(){historyHasMore=false;historyLoading=false;oldestMessageId=null;unreadMessageCount=0;updateHistoryControls();updateScrollLatestButton()}
function isNearBottom(threshold=90){const x=document.getElementById('messages-list');return x.scrollHeight-x.scrollTop-x.clientHeight<=threshold}
function scrollToBottom(smooth=true){const x=document.getElementById('messages-list');x.scrollTo({top:x.scrollHeight,behavior:smooth?'smooth':'auto'});unreadMessageCount=0;updateScrollLatestButton()}
function updateScrollLatestButton(){const b=document.getElementById('scroll-latest');if(!b)return;const show=!isNearBottom()||unreadMessageCount>0;b.hidden=!show;b.textContent=unreadMessageCount?`↓ ${unreadMessageCount} nouveau${unreadMessageCount>1?'x':''} message${unreadMessageCount>1?'s':''}`:'↓ Revenir en bas'}
function updateHistoryControls(){const b=document.getElementById('load-older');if(!b)return;b.hidden=!historyHasMore&&!historyLoading;b.disabled=historyLoading;b.textContent=historyLoading?'Chargement…':'↑ Charger les messages précédents'}
function visibleMessageIndex(){const list=document.getElementById('messages-list');const items=[...list.querySelectorAll('.message-item')];if(!items.length)return-1;const top=list.getBoundingClientRect().top+8;let best=0;for(let i=0;i<items.length;i++){if(items[i].getBoundingClientRect().top>=top){best=i;break}best=i}return best}
function jumpMessage(direction){const list=document.getElementById('messages-list');const items=[...list.querySelectorAll('.message-item')];if(!items.length)return;let i=visibleMessageIndex();i=Math.max(0,Math.min(items.length-1,i+direction));items[i].scrollIntoView({block:'center',behavior:'smooth'});items[i].classList.add('message-focus');setTimeout(()=>items[i].classList.remove('message-focus'),900)}
function bindMessageNavigation(){const list=document.getElementById('messages-list');document.getElementById('scroll-latest').onclick=()=>scrollToBottom(true);document.getElementById('jump-latest').onclick=()=>scrollToBottom(true);document.getElementById('jump-first').onclick=async()=>{while(historyHasMore)await loadOlderMessages();list.scrollTo({top:0,behavior:'smooth'})};document.getElementById('jump-previous').onclick=()=>jumpMessage(-1);document.getElementById('jump-next').onclick=()=>jumpMessage(1);document.getElementById('load-older').onclick=loadOlderMessages;list.addEventListener('scroll',()=>{updateScrollLatestButton();if(list.scrollTop<110&&historyHasMore&&!historyLoading){clearTimeout(autoLoadOlderTimer);autoLoadOlderTimer=setTimeout(loadOlderMessages,180)}});list.addEventListener('keydown',e=>{if(e.key==='PageUp'){e.preventDefault();list.scrollBy({top:-Math.max(220,list.clientHeight*.75),behavior:'smooth'})}else if(e.key==='PageDown'){e.preventDefault();list.scrollBy({top:Math.max(220,list.clientHeight*.75),behavior:'smooth'})}else if((e.metaKey||e.ctrlKey)&&e.key==='Home'){e.preventDefault();document.getElementById('jump-first').click()}else if((e.metaKey||e.ctrlKey)&&e.key==='End'){e.preventDefault();scrollToBottom(true)}else if(e.altKey&&e.key==='ArrowUp'){e.preventDefault();jumpMessage(-1)}else if(e.altKey&&e.key==='ArrowDown'){e.preventDefault();jumpMessage(1)}});window.addEventListener('keydown',e=>{if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName))return;if(e.altKey&&e.key==='ArrowUp'){e.preventDefault();jumpMessage(-1)}else if(e.altKey&&e.key==='ArrowDown'){e.preventDefault();jumpMessage(1)}})}

function setRoomReply(message){pendingReplyMessage=message;const bar=document.getElementById('reply-composer-bar');bar.hidden=false;document.getElementById('reply-composer-user').textContent=message.username;document.getElementById('reply-composer-preview').textContent=message.content||message.message_type;document.getElementById('message-input').focus()}
function clearRoomReply(){pendingReplyMessage=null;const bar=document.getElementById('reply-composer-bar');if(bar)bar.hidden=true}
async function editRoomMessage(message){const content=prompt('Modifier le message :',message.content||'');if(content===null||!content.trim())return;try{const r=await fetch(`/api/messages/${message.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({content:content.trim()})});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Modification refusée')}catch(e){window.PiChatTrolls?.toast?.(e.message||String(e))}}
async function deleteRoomMessage(message){if(!confirm('Supprimer ce message ?'))return;try{const r=await fetch(`/api/messages/${message.id}`,{method:'DELETE',credentials:'same-origin'});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Suppression refusée')}catch(e){window.PiChatTrolls?.toast?.(e.message||String(e))}}
async function toggleRoomPin(message){try{const r=await fetch(`/api/messages/${message.id}/pin`,{method:'POST',credentials:'same-origin'});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Action refusée')}catch(e){window.PiChatTrolls?.toast?.(e.message||String(e))}}
function sendChatContent(content){
  content=String(content||'').trim();if(!content)return false;
  if(!currentRoomId){updateComposerConnection('Aucun salon sélectionné','error');window.PiChatTrolls?.toast?.('Choisis un salon avant d’envoyer.');return false}
  if(window.PiChatTrolls?.handleLocalCommand?.(content))return true;
  const replyToId=pendingReplyMessage?.id||null;
  if(chatSocket&&chatSocket.readyState===WebSocket.OPEN){
    try{chatSocket.send(JSON.stringify({content,reply_to_id:replyToId}));clearRoomReply();updateComposerConnection('Message envoyé ✓','connected');setTimeout(()=>updateComposerConnection('Prêt à envoyer','connected'),900);return true}
    catch(error){console.error('Envoi WebSocket',error)}
  }
  const queued=queueChatMessage(content,replyToId);
  if(queued)clearRoomReply();
  return queued;
}
function handleSendMessage(event){
  event.preventDefault();
  const input=document.getElementById('message-input');if(!input)return;
  const content=input.value.trim();if(!content)return;
  if(sendChatContent(content)){input.value='';input.focus()}
}
function bindSendForm(){
  if(sendFormBound)return;
  const form=document.getElementById('message-form');
  if(!form)return;
  form.addEventListener('submit',handleSendMessage);
  sendFormBound=true;
  updateComposerConnection('Connexion au chat…','connecting');
}
function bindComposerUi(){bindSendForm();document.getElementById('cancel-reply')?.addEventListener('click',clearRoomReply)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bindComposerUi,{once:true});else bindComposerUi();
window.sendChatContent=sendChatContent;window.switchRoom=switchRoom;window.loadRoomList=loadRoomList;window.showEmojiComposer=showEmojiComposer;window.setRoomReply=setRoomReply;

;
/* ===== gaming_profiles.js ===== */
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fallbackCatalog = [
    {key:'valorant',name:'Valorant',icon:'🎯',username_hint:'Pseudo#TAG',platform_hint:'PC'},
    {key:'brawl-stars',name:'Brawl Stars',icon:'⭐',username_hint:'Pseudo ou tag joueur',platform_hint:'Mobile'},
    {key:'roblox',name:'Roblox',icon:'⬛',username_hint:'Pseudo Roblox',platform_hint:'PC / Mobile / Console'},
    {key:'fortnite',name:'Fortnite',icon:'🪂',username_hint:'Pseudo Epic Games',platform_hint:'PC / Console / Mobile'}
  ];
  let catalog = fallbackCatalog;
  let games = [];
  let customIndex = 0;

  async function api(url, options={}){
    const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});
    let data={};try{data=await response.json()}catch{}
    if(!response.ok)throw new Error(data.detail||`Erreur ${response.status}`);
    return data;
  }
  function gameIcon(key){return (catalog.find(x=>x.key===key)||{}).icon||'🎮'}
  function normaliseGames(profileGames){
    const byKey=new Map((profileGames||[]).map(g=>[g.game_key,g]));
    const rows=catalog.map(item=>({game_key:item.key,game_name:item.name,username:byKey.get(item.key)?.username||'',platform:byKey.get(item.key)?.platform||item.platform_hint||'',is_public:byKey.get(item.key)?.is_public!==false,fixed:true,icon:item.icon,username_hint:item.username_hint}));
    (profileGames||[]).filter(g=>!catalog.some(item=>item.key===g.game_key)).forEach(g=>rows.push({...g,fixed:false,icon:g.icon||'🎮'}));
    return rows.slice(0,12);
  }
  function addCustomGame(initial={}){
    if(games.length>=12){status('Maximum 12 jeux.');return}
    customIndex+=1;
    games.push({game_key:initial.game_key||`custom-new-${customIndex}`,game_name:initial.game_name||'',username:initial.username||'',platform:initial.platform||'',is_public:initial.is_public!==false,fixed:false,icon:'🎮'});
    renderGameRows();
    const rows=$('gaming-profile-list')?.querySelectorAll('.game-identity-row');
    rows?.[rows.length-1]?.querySelector('.game-name-field')?.focus();
  }
  function renderGameRows(){
    const box=$('gaming-profile-list');if(!box)return;box.innerHTML='';
    games.forEach((game,index)=>{
      const row=document.createElement('div');row.className='game-identity-row';row.dataset.index=String(index);
      const nameHtml=game.fixed?`<span class="game-fixed-name">${esc(game.game_name)}</span>`:`<input class="game-name-field" maxlength="48" placeholder="Nom du jeu" value="${esc(game.game_name)}">`;
      row.innerHTML=`<span class="game-identity-icon">${esc(game.icon||gameIcon(game.game_key))}</span>${nameHtml}<input class="game-username-field" maxlength="80" placeholder="${esc(game.username_hint||'Ton pseudo')}" value="${esc(game.username||'')}"><input class="game-platform-field" maxlength="32" placeholder="Plateforme" value="${esc(game.platform||'')}"><label class="game-public-toggle"><input type="checkbox" class="game-public-field" ${game.is_public!==false?'checked':''}> Public</label>${game.fixed?'<span></span>':'<button type="button" class="game-remove" title="Supprimer">×</button>'}`;
      row.querySelector('.game-name-field')?.addEventListener('input',e=>{games[index].game_name=e.target.value});
      row.querySelector('.game-username-field')?.addEventListener('input',e=>{games[index].username=e.target.value});
      row.querySelector('.game-platform-field')?.addEventListener('input',e=>{games[index].platform=e.target.value});
      row.querySelector('.game-public-field')?.addEventListener('change',e=>{games[index].is_public=e.target.checked});
      row.querySelector('.game-remove')?.addEventListener('click',()=>{games.splice(index,1);renderGameRows()});
      box.append(row);
    });
  }
  function renderBadges(badges){
    const box=$('profile-badges');if(!box)return;box.innerHTML='';
    if(!(badges||[]).length){box.innerHTML='<span class="muted">Aucun badge pour le moment.</span>';return}
    badges.forEach(b=>{const chip=document.createElement('span');chip.className='profile-badge-chip';chip.style.setProperty('--badge-color',b.color||'#f0b232');chip.title=b.description||b.reason||b.name;chip.innerHTML=`<span>${esc(b.icon||'🏅')}</span><strong>${esc(b.name)}</strong><small>${esc(b.description||'')}</small>`;box.append(chip)})
  }
  function renderProfile(p){
    games=normaliseGames(p.games||[]);renderGameRows();renderBadges(p.badges||[]);
    if($('profile-stats'))$('profile-stats').innerHTML=`<div><b>${esc(p.class_code||'—')}</b><small>CLASSE</small></div><div><b>${Number(p.coins||0)}</b><small>PICOINS</small></div><div><b>${(p.badges||[]).length}</b><small>BADGES</small></div><div><b>${(p.games||[]).filter(g=>g.username).length}</b><small>JEUX</small></div>`;
  }
  function collectGames(){
    return games.map((game,index)=>{
      const row=$('gaming-profile-list')?.querySelector(`[data-index="${index}"]`);
      return {game_key:game.fixed?game.game_key:'',game_name:(row?.querySelector('.game-name-field')?.value||game.game_name||'').trim(),username:(row?.querySelector('.game-username-field')?.value||'').trim(),platform:(row?.querySelector('.game-platform-field')?.value||'').trim(),is_public:!!row?.querySelector('.game-public-field')?.checked};
    }).filter(g=>g.game_name&&g.username).slice(0,12);
  }
  function status(text){if($('gaming-profile-status'))$('gaming-profile-status').textContent=text||''}
  async function saveProfile(){
    const button=$('save-profile');if(button)button.disabled=true;status('Enregistrement…');
    try{
      const profile=await api('/api/profile/me',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status_message:$('profile-status').value.trim(),profile_bio:$('profile-bio').value.trim(),profile_color:$('profile-color').value,grade_visibility:$('grade-visibility').value})});
      const result=await api('/api/profile/me/games',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({games:collectGames()})});
      const merged={...profile,...result.profile,games:result.games};
      renderProfile(merged);status('Profil enregistré ✓');return merged;
    }finally{if(button)button.disabled=false;setTimeout(()=>status(''),2400)}
  }
  function publicSections(p){
    const badges=(p.badges||[]).filter(b=>b.showcased!==false).slice(0,12);
    const publicGames=(p.games||[]).filter(g=>g.is_public!==false&&g.username);
    let html='';
    if(badges.length)html+=`<section class="public-profile-badges"><h3>🏅 Badges</h3><div class="profile-badge-list">${badges.map(b=>`<span class="profile-badge-chip" style="--badge-color:${esc(b.color||'#f0b232')}" title="${esc(b.description||'')}"><span>${esc(b.icon||'🏅')}</span><strong>${esc(b.name)}</strong></span>`).join('')}</div></section>`;
    if(publicGames.length)html+=`<section class="public-profile-games"><h3>🎮 Pseudos de jeux</h3><div class="public-game-grid">${publicGames.map(g=>`<div class="public-game-card"><span>${esc(g.icon||gameIcon(g.game_key))}</span><div><strong>${esc(g.game_name)}</strong><span>${esc(g.username)}</span>${g.platform?`<small>${esc(g.platform)}</small>`:''}</div></div>`).join('')}</div></section>`;
    return html;
  }
  async function loadCatalog(){try{catalog=await api('/api/gaming/catalog')}catch{catalog=fallbackCatalog}}
  async function loadAndRender(){await loadCatalog();const p=await api('/api/profile/me');renderProfile(p);return p}
  document.addEventListener('DOMContentLoaded',()=>{$('add-custom-game')?.addEventListener('click',()=>addCustomGame())});
  window.PiChatGamingProfiles={renderProfile,saveProfile,publicSections,loadAndRender,addCustomGame};
})();

;
/* ===== arcade.js ===== */
(()=>{
  const $=id=>document.getElementById(id);
  let dashboard=null,currentSession=null,currentGame='clicker',memoryTimer=null,clickerTimer=null,reflexTimer=null;

  async function api(url,options={}){
    const response=await fetch(url,{credentials:'same-origin',...options});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.detail||'Erreur Arcade.');
    return data;
  }
  function esc(value){return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
  function clearTimers(){if(memoryTimer)clearInterval(memoryTimer);if(clickerTimer)clearInterval(clickerTimer);if(reflexTimer)clearTimeout(reflexTimer);memoryTimer=clickerTimer=reflexTimer=null}
  function setResult(text,type=''){const el=$('arcade-result');if(!el)return;el.textContent=text||'';el.className='arcade-result '+type}

  async function loadDashboard(game=currentGame){
    try{
      dashboard=await api('/api/arcade/dashboard?game='+encodeURIComponent(game));
      currentGame=dashboard.leaderboard_game||game;
      renderDashboard();
    }catch(error){setResult(error.message,'error');const list=$('arcade-game-list');if(list)list.innerHTML='<p class="muted">'+esc(error.message)+'</p>'}
  }

  function renderDashboard(){
    if(!dashboard)return;
    const list=$('arcade-game-list');
    if(list){list.innerHTML=dashboard.catalog.map(game=>`<button class="arcade-game-card ${currentSession?.game_key===game.key?'active':''}" data-arcade-game="${game.key}"><span class="icon">${game.icon}</span><span><b>${esc(game.name)}</b><small>${esc(game.description)}</small></span></button>`).join('');list.querySelectorAll('[data-arcade-game]').forEach(button=>button.onclick=()=>startGame(button.dataset.arcadeGame))}
    const select=$('arcade-leaderboard-game');
    if(select){const old=select.value;select.innerHTML=dashboard.catalog.map(game=>`<option value="${game.key}">${game.icon} ${esc(game.name)}</option>`).join('');select.value=dashboard.leaderboard_game||old||'clicker'}
    const challenge=dashboard.daily_challenge;const progress=Math.min(100,Math.round((challenge.today_best||0)/Math.max(1,challenge.target_score)*100));
    const daily=$('arcade-daily');if(daily)daily.innerHTML=`<strong>${challenge.completed?'✅':'🎯'} Défi du jour</strong><p>${challenge.icon} Atteins <b>${challenge.target_score} points</b> à ${esc(challenge.game_name)}.</p><div class="arcade-daily-progress"><span style="width:${progress}%"></span></div><small class="${challenge.completed?'arcade-daily-done':''}">${challenge.completed?'Récompense récupérée':`${challenge.today_best||0} / ${challenge.target_score}`} · 🪙 ${challenge.reward_coins} · ✨ ${challenge.reward_xp} XP</small>`;
    const sum=dashboard.summary;const summary=$('arcade-summary');if(summary)summary.innerHTML=`<div class="arcade-stat"><b>${sum.plays}</b><small>parties</small></div><div class="arcade-stat"><b>${sum.coins_earned}</b><small>PyCoins gagnés</small></div><div class="arcade-stat"><b>${sum.wallet}</b><small>dans le portefeuille</small></div><div class="arcade-stat"><b>${sum.xp}</b><small>XP total</small></div>`;
    const board=$('arcade-leaderboard');if(board)board.innerHTML=dashboard.leaderboard.length?dashboard.leaderboard.map((row,index)=>`<div class="arcade-rank"><span>${index<3?['🥇','🥈','🥉'][index]:index+1}</span><strong>${esc(row.username)}</strong><small>${row.best_score}</small></div>`).join(''):'<p class="muted">Aucun score pour le moment.</p>';
  }

  function gameHead(session){return `<div class="arcade-game-head"><div class="arcade-big-icon">${session.game.icon}</div><h3>${esc(session.game.name)}</h3><p>${esc(session.game.description)}</p></div>`}

  async function startGame(gameKey){
    clearTimers();setResult('');
    const stage=$('arcade-stage');if(stage)stage.innerHTML='<div class="arcade-welcome"><span>⏳</span><h3>Préparation de la partie…</h3></div>';
    try{
      currentSession=await api('/api/arcade/start/'+encodeURIComponent(gameKey),{method:'POST'});
      currentGame=gameKey;renderDashboard();renderGame(currentSession);
    }catch(error){setResult(error.message,'error');if(stage)stage.innerHTML='<div class="arcade-welcome"><span>⚠️</span><h3>Impossible de lancer le jeu</h3><p>'+esc(error.message)+'</p></div>'}
  }

  function renderGame(session){
    if(session.game_key==='number')return renderNumber(session);
    if(session.game_key==='quiz')return renderQuiz(session);
    if(session.game_key==='memory')return renderMemory(session);
    if(session.game_key==='reflex')return renderReflex(session);
    if(session.game_key==='clicker')return renderClicker(session);
    if(session.game_key==='tictactoe')return renderTicTacToe(session.board||Array(9).fill(''),'À toi de jouer : tu es X.');
  }

  async function action(payload){return api('/api/arcade/sessions/'+encodeURIComponent(currentSession.session_id)+'/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})}

  function renderNumber(session){
    const stage=$('arcade-stage');stage.innerHTML=`<div class="arcade-game-screen">${gameHead(session)}<div id="number-hint" class="arcade-hint">Entre ton premier nombre.</div><div class="arcade-number-box"><input id="number-guess" type="number" min="1" max="100" value="50"><button id="number-submit" class="arcade-primary">Essayer</button></div><div id="number-attempts" class="arcade-attempts">0 tentative</div></div>`;
    const submit=async()=>{try{const value=Number($('number-guess').value);const result=await action({action:'guess',guess:value});if(result.completed)return completeGame(result);$('number-hint').textContent=result.hint==='higher'?'⬆️ Plus haut !':'⬇️ Plus bas !';$('number-attempts').textContent=result.attempts+' tentative'+(result.attempts>1?'s':'');$('number-guess').focus();$('number-guess').select()}catch(error){setResult(error.message,'error')}};
    $('number-submit').onclick=submit;$('number-guess').onkeydown=e=>{if(e.key==='Enter')submit()};$('number-guess').focus();
  }

  function renderQuiz(session){
    const stage=$('arcade-stage');stage.innerHTML=`<form id="arcade-quiz-form" class="arcade-game-screen"><div>${gameHead(session)}</div><div class="arcade-quiz">${session.questions.map((item,index)=>`<div class="arcade-question"><strong>${index+1}. ${esc(item.question)}</strong>${item.options.map((option,opt)=>`<label><input type="radio" name="q${index}" value="${opt}"> ${esc(option)}</label>`).join('')}</div>`).join('')}</div><button class="arcade-primary">Valider les réponses</button></form>`;
    $('arcade-quiz-form').onsubmit=async event=>{event.preventDefault();const answers=session.questions.map((_,index)=>{const picked=document.querySelector(`input[name="q${index}"]:checked`);return picked?Number(picked.value):-1});if(answers.some(x=>x<0)){setResult('Réponds à toutes les questions.','error');return}try{completeGame(await action({action:'submit',answers}))}catch(error){setResult(error.message,'error')}};
  }

  function renderMemory(session){
    const stage=$('arcade-stage');const started=Date.now();let first=null,lock=false,matches=0,moves=0;
    stage.innerHTML=`<div class="arcade-game-screen">${gameHead(session)}<div class="arcade-memory-meta"><span id="memory-moves">0 coup</span><span id="memory-time">0.0 s</span></div><div id="memory-grid" class="arcade-memory-grid">${session.cards.map((_,index)=>`<button class="arcade-memory-card" data-index="${index}">❔</button>`).join('')}</div></div>`;
    memoryTimer=setInterval(()=>{const el=$('memory-time');if(el)el.textContent=((Date.now()-started)/1000).toFixed(1)+' s'},100);
    const cards=[...$('memory-grid').querySelectorAll('.arcade-memory-card')];
    cards.forEach(button=>button.onclick=async()=>{if(lock||button.classList.contains('matched')||button===first)return;const index=Number(button.dataset.index);button.textContent=session.cards[index];button.classList.add('revealed');if(!first){first=button;return}moves++;$('memory-moves').textContent=moves+' coup'+(moves>1?'s':'');const firstIndex=Number(first.dataset.index);if(session.cards[firstIndex]===session.cards[index]){first.classList.add('matched');button.classList.add('matched');first=null;matches++;if(matches===session.pairs){clearTimers();try{completeGame(await action({action:'finish',moves,elapsed_ms:Date.now()-started}))}catch(error){setResult(error.message,'error')}}}else{lock=true;setTimeout(()=>{first.textContent='❔';button.textContent='❔';first.classList.remove('revealed');button.classList.remove('revealed');first=null;lock=false},650)}});
  }

  function renderReflex(session){
    const stage=$('arcade-stage');stage.innerHTML=`<div class="arcade-game-screen">${gameHead(session)}<button id="reflex-pad" class="arcade-reflex-pad">Attends le vert…</button><p class="muted" style="text-align:center">Un clic trop tôt termine la manche.</p></div>`;
    const pad=$('reflex-pad');let ready=false;reflexTimer=setTimeout(()=>{ready=true;pad.classList.add('ready');pad.textContent='CLIQUE !'},session.wait_ms);
    pad.onclick=async()=>{pad.disabled=true;clearTimers();try{const result=await action({action:'tap'});if(result.failed){setResult('Trop tôt ! Relance une partie.','error');return renderFailed(session,'⏱️','Trop tôt !')}completeGame(result)}catch(error){setResult(error.message,'error')}};
  }

  function renderClicker(session){
    const stage=$('arcade-stage');let clicks=0;let remaining=session.duration_ms;const started=Date.now();stage.innerHTML=`<div class="arcade-game-screen">${gameHead(session)}<div class="arcade-clicker-meta"><span id="clicker-count">0 clic</span><span id="clicker-time">10.0 s</span></div><button id="clicker-button" class="arcade-clicker-button">CLIQUE !</button></div>`;
    const button=$('clicker-button');button.onclick=()=>{clicks++;$('clicker-count').textContent=clicks+' clic'+(clicks>1?'s':'')};
    clickerTimer=setInterval(async()=>{remaining=Math.max(0,session.duration_ms-(Date.now()-started));const timeEl=$('clicker-time');if(timeEl)timeEl.textContent=(remaining/1000).toFixed(1)+' s';if(remaining<=0){clearTimers();button.disabled=true;button.textContent='TERMINÉ';try{completeGame(await action({action:'finish',clicks}))}catch(error){setResult(error.message,'error')}}},50);
  }

  function renderTicTacToe(board,status){
    const session=currentSession;const stage=$('arcade-stage');stage.innerHTML=`<div class="arcade-game-screen">${gameHead(session)}<div id="ttt-status" class="arcade-ttt-status">${esc(status)}</div><div class="arcade-ttt-grid">${board.map((value,index)=>`<button class="arcade-ttt-cell" data-cell="${index}" ${value?'disabled':''}>${value==='X'?'❌':value==='O'?'⭕':''}</button>`).join('')}</div></div>`;
    stage.querySelectorAll('[data-cell]').forEach(button=>button.onclick=async()=>{stage.querySelectorAll('[data-cell]').forEach(x=>x.disabled=true);try{const result=await action({action:'move',cell:Number(button.dataset.cell)});if(result.completed)return completeGame(result);renderTicTacToe(result.board,'PiBot a joué. À toi !')}catch(error){setResult(error.message,'error');renderTicTacToe(board,'À toi de jouer.')}});
  }

  function renderFailed(session,icon,title){const stage=$('arcade-stage');stage.innerHTML=`<div class="arcade-end-card"><div class="result-icon">${icon}</div><h3>${esc(title)}</h3><p>Cette manche n’est pas comptabilisée.</p><button id="arcade-replay" class="arcade-primary">Rejouer</button></div>`;$('arcade-replay').onclick=()=>startGame(session.game_key)}

  async function completeGame(result){
    clearTimers();const game=currentSession?.game||{icon:'🎮',name:'Mini-jeu'};const reward=result.reward||{};const daily=result.daily_challenge_bonus||{};const stage=$('arcade-stage');
    stage.innerHTML=`<div class="arcade-end-card"><div class="result-icon">${result.failed?'⏱️':game.icon}</div><h3>${esc(result.result_label||'Partie terminée')}</h3><p>Score : <strong>${result.score||0} points</strong></p><div class="arcade-reward-line">${reward.coins?`<span class="arcade-reward-chip">🪙 +${reward.coins}</span>`:''}${reward.xp?`<span class="arcade-reward-chip">✨ +${reward.xp} XP</span>`:''}${daily.claimed?`<span class="arcade-reward-chip daily">🎯 Défi réussi · +${daily.coins} 🪙 · +${daily.xp} XP</span>`:''}${!reward.coins&&!reward.xp&&!daily.claimed?'<span class="arcade-reward-chip">Record enregistré</span>':''}</div><button id="arcade-replay" class="arcade-primary">Rejouer</button> <button id="arcade-other" class="arcade-secondary">Choisir un autre jeu</button></div>`;
    setResult(daily.claimed?'Défi du jour réussi !':reward.coins?'Récompense ajoutée à ton portefeuille.':'Score enregistré.',daily.claimed||reward.coins?'reward':'success');
    $('arcade-replay').onclick=()=>startGame(currentSession.game_key);$('arcade-other').onclick=()=>{currentSession=null;stage.innerHTML='<div class="arcade-welcome"><span>🕹️</span><h3>Choisis un mini-jeu</h3><p>Les cartes sont disponibles à gauche.</p></div>';renderDashboard()};
    await loadDashboard(currentGame);
  }

  function bind(){
    $('open-games')?.addEventListener('click',()=>loadDashboard(currentGame));
    $('arcade-refresh')?.addEventListener('click',()=>loadDashboard(currentGame));
    $('arcade-leaderboard-game')?.addEventListener('change',event=>loadDashboard(event.target.value));
  }
  bind();
  window.PiChatArcade={load:loadDashboard,start:startGame};
})();

;
/* ===== game_studio.js ===== */
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let status = null;
  let games = {published:[], mine:[], pending:[]};
  let currentGame = null;
  let selectedFile = null;

  async function api(url, options={}){
    const response = await fetch(url, {credentials:'same-origin', cache:'no-store', ...options});
    const data = await response.json().catch(() => ({}));
    if(!response.ok) throw new Error(data.detail || `Erreur ${response.status}`);
    return data;
  }
  function setMessage(text, kind=''){
    const el = $('game-studio-status'); if(!el) return;
    el.textContent = text || ''; el.className = `game-studio-status ${kind}`;
  }
  function openModal(){ $('game-studio-modal')?.classList.add('open'); loadAll(); }
  function closeModal(){ $('game-studio-modal')?.classList.remove('open'); stopGame(); }
  function stopGame(){
    const frame=$('game-studio-frame'); if(frame){frame.src='about:blank';frame.srcdoc='';}
    $('game-studio-player')?.classList.remove('open'); currentGame=null;
  }
  async function copyText(text){
    try{await navigator.clipboard.writeText(text);return true}catch{}
    const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.opacity='0';document.body.append(area);area.select();const ok=document.execCommand('copy');area.remove();return ok;
  }
  function tab(name){
    document.querySelectorAll('[data-studio-tab]').forEach(button=>button.classList.toggle('active',button.dataset.studioTab===name));
    document.querySelectorAll('[data-studio-panel]').forEach(panel=>panel.classList.toggle('active',panel.dataset.studioPanel===name));
  }
  function statusLabel(value){return ({draft:'BROUILLON',pending:'EN VALIDATION',published:'PUBLIC',rejected:'REFUSÉ'})[value]||String(value||'').toUpperCase()}
  function gameCard(game, mine=false, pending=false){
    const article=document.createElement('article');article.className='studio-game-card';
    article.innerHTML=`<div class="studio-game-icon">${esc(game.icon||'🎮')}</div><div class="studio-game-info"><div class="studio-game-title"><strong>${esc(game.title)}</strong><span class="studio-status ${esc(game.status)}">${esc(statusLabel(game.status))}</span></div><p>${esc(game.description||'')}</p><small>par ${esc(game.owner_username||'—')} · ${Number(game.plays||0)} partie(s)</small><div class="studio-card-actions"></div></div>`;
    const actions=article.querySelector('.studio-card-actions');
    const add=(label, fn, cls='')=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.className=cls;b.addEventListener('click',async()=>{if(b.disabled)return;b.disabled=true;try{await fn()}finally{b.disabled=false}});actions.append(b)};
    add('▶ Jouer',()=>play(game.id),'primary');
    if(mine && ['draft','rejected'].includes(game.status)) add('Envoyer en validation',()=>submit(game.id));
    if(mine && game.status!=='published') add('Supprimer',()=>remove(game.id),'danger');
    if(pending && status?.is_admin){add('✓ Publier',()=>review(game.id,true),'good');add('✕ Refuser',()=>review(game.id,false),'danger')}
    return article;
  }
  function renderLists(){
    const publicBox=$('game-studio-public-list'),mineBox=$('game-studio-my-list'),pendingBox=$('game-studio-pending-list');
    if(publicBox){publicBox.innerHTML='';if(!games.published.length)publicBox.innerHTML='<p class="studio-empty">Aucun jeu public pour le moment.</p>';games.published.forEach(g=>publicBox.append(gameCard(g)))}
    if(mineBox){mineBox.innerHTML='';if(!games.mine.length)mineBox.innerHTML='<p class="studio-empty">Tu n’as encore créé aucun jeu.</p>';games.mine.forEach(g=>mineBox.append(gameCard(g,true)))}
    if(pendingBox){pendingBox.innerHTML='';if(!games.pending.length)pendingBox.innerHTML='<p class="studio-empty">Aucun jeu en attente.</p>';games.pending.forEach(g=>pendingBox.append(gameCard(g,false,true)))}
    const pendingTab=$('studio-pending-tab');if(pendingTab)pendingTab.hidden=!status?.is_admin;
  }
  async function loadAll(){
    try{
      status=await api('/api/game-studio/status');
      if(!status.enabled){$('open-game-studio').style.display='none';closeModal();return}
      $('studio-api-generate').hidden=!(status.direct_api_enabled&&status.api_key_configured);
      $('studio-api-note').textContent=status.direct_api_enabled?(status.api_key_configured?'Génération directe disponible.':'Clé API manquante sur le serveur.'):'Génération directe désactivée par l’admin.';
      games=await api('/api/game-studio/games');renderLists();
    }catch(error){setMessage(error.message,'error')}
  }
  function getIdea(){return $('studio-idea').value.trim()}
  function getTitle(){return $('studio-title').value.trim()}
  async function preparePrompt(){
    const idea=getIdea();if(!idea){setMessage('Décris ton idée de jeu.','error');return}
    const button=$('studio-open-chatgpt');button.disabled=true;setMessage('Préparation du prompt spécial…');
    const popup=window.open('https://chatgpt.com/','_blank','noopener,noreferrer');
    try{
      const data=await api('/api/game-studio/prompt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idea,title:getTitle()})});
      $('studio-special-prompt').value=data.prompt;await copyText(data.prompt);
      setMessage(popup?'Prompt copié. Colle-le dans ChatGPT, puis copie sa réponse JSON ici.':'Prompt copié. Le navigateur a bloqué l’onglet : utilise le lien « Ouvrir ChatGPT manuellement ».','success');
      tab('create');
    }catch(error){setMessage(error.message,'error')}finally{button.disabled=false}
  }
  async function copyPrompt(){const text=$('studio-special-prompt').value;if(!text){setMessage('Prépare d’abord le prompt.','error');return}await copyText(text);setMessage('Prompt copié ✓','success')}
  async function importAnswer(){
    const answer=$('studio-chatgpt-answer').value.trim();if(!answer){setMessage('Colle la réponse JSON de ChatGPT.','error');return}
    const button=$('studio-import');button.disabled=true;setMessage('Analyse de sécurité et import du jeu…');
    try{
      const game=await api('/api/game-studio/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idea:getIdea(),title:getTitle(),answer})});
      $('studio-chatgpt-answer').value='';setMessage(`Jeu « ${game.title} » importé en brouillon ✓`,'success');await loadAll();tab('mine');await play(game.id,false);
    }catch(error){setMessage(error.message,'error')}finally{button.disabled=false}
  }
  function selectGameFile(file){
    selectedFile=file||null;
    const name=$('studio-file-name'),button=$('studio-file-import'),zone=$('studio-drop-zone');
    if(name)name.textContent=selectedFile?`${selectedFile.name} · ${Math.max(1,Math.round(selectedFile.size/1024))} Ko`:'Aucun fichier choisi';
    if(button)button.disabled=!selectedFile;
    if(zone)zone.classList.toggle('has-file',!!selectedFile);
  }
  async function importFile(){
    if(!selectedFile){setMessage('Choisis un fichier .html, .css, .js, .json ou .zip.','error');return}
    const button=$('studio-file-import');button.disabled=true;setMessage('Vérification et import du fichier…');
    try{
      const form=new FormData();form.append('file',selectedFile,selectedFile.name);
      const game=await api('/api/game-studio/import-file',{method:'POST',body:form});
      selectGameFile(null);if($('studio-file-input'))$('studio-file-input').value='';
      setMessage(`Jeu « ${game.title} » importé en brouillon ✓`,'success');await loadAll();tab('mine');await play(game.id,false);
    }catch(error){setMessage(error.message,'error')}finally{button.disabled=!selectedFile}
  }

  async function generateDirect(){
    const idea=getIdea();if(!idea){setMessage('Décris ton idée de jeu.','error');return}
    const button=$('studio-api-generate');button.disabled=true;setMessage('ChatGPT crée et sécurise le jeu… Cela peut prendre un moment.');
    try{
      const game=await api('/api/game-studio/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idea,title:getTitle()})});
      setMessage(`Jeu « ${game.title} » généré en brouillon ✓`,'success');await loadAll();tab('mine');await play(game.id,false);
    }catch(error){setMessage(error.message,'error')}finally{button.disabled=false}
  }
  async function pushPiGameContext(context=null){
    const frame=$('game-studio-frame');
    if(!frame?.contentWindow||!currentGame)return;
    try{
      const safe=context||await api(`/api/game-studio/games/${currentGame.id}/pigame/context`);
      frame.contentWindow.postMessage({__pigame_context:1,game_id:Number(currentGame.id),context:safe},'*');
    }catch(error){setMessage(`PiGame API : ${error.message}`,'error')}
  }
  async function handlePiGameMessage(event){
    const frame=$('game-studio-frame'),data=event.data;
    if(!currentGame||!frame?.contentWindow||event.source!==frame.contentWindow||!data||data.__pigame!==1||Number(data.game_id)!==Number(currentGame.id))return;
    try{
      if(data.type==='ready'||data.type==='refresh'){await pushPiGameContext();return}
      if(data.type==='score'){
        const result=await api(`/api/game-studio/games/${currentGame.id}/pigame/score`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({score:Number(data.score)||0})});
        await pushPiGameContext(result.context);return;
      }
      if(data.type==='achievement'){
        const result=await api(`/api/game-studio/games/${currentGame.id}/pigame/achievement`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:String(data.key||'').slice(0,48),title:String(data.title||'').slice(0,80)})});
        await pushPiGameContext(result.context);
      }
    }catch(error){setMessage(`PiGame API : ${error.message}`,'error')}
  }
  async function play(id,count=true){
    try{
      const game=await api(`/api/game-studio/games/${id}${count?'/play':''}`,count?{method:'POST'}:{});currentGame=game;
      $('game-studio-player-title').textContent=`${game.icon||'🎮'} ${game.title}`;
      const frame=$('game-studio-frame');frame.setAttribute('sandbox','allow-scripts');frame.srcdoc=game.document;
      $('game-studio-player').classList.add('open');
    }catch(error){setMessage(error.message,'error')}
  }
  async function submit(id){try{await api(`/api/game-studio/games/${id}/submit`,{method:'POST'});setMessage(status?.require_admin_approval?'Jeu envoyé à l’admin ✓':'Jeu publié ✓','success');await loadAll()}catch(error){setMessage(error.message,'error')}}
  async function remove(id){if(!confirm('Supprimer définitivement ce jeu ?'))return;try{await api(`/api/game-studio/games/${id}`,{method:'DELETE'});setMessage('Jeu supprimé.','success');await loadAll()}catch(error){setMessage(error.message,'error')}}
  async function review(id,approve){const note=prompt(approve?'Note facultative de publication :':'Motif du refus :','');if(note===null)return;try{await api(`/api/admin/game-studio/games/${id}/${approve?'approve':'reject'}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({note})});setMessage(approve?'Jeu publié ✓':'Jeu refusé.','success');await loadAll()}catch(error){setMessage(error.message,'error')}}
  function bind(){
    window.addEventListener('message',handlePiGameMessage);
    $('open-game-studio')?.addEventListener('click',openModal);
    $('game-studio-close')?.addEventListener('click',closeModal);
    $('game-studio-modal')?.addEventListener('click',event=>{if(event.target===event.currentTarget)closeModal()});
    document.querySelectorAll('[data-studio-tab]').forEach(button=>button.addEventListener('click',()=>tab(button.dataset.studioTab)));
    $('studio-open-chatgpt')?.addEventListener('click',preparePrompt);
    $('studio-copy-prompt')?.addEventListener('click',copyPrompt);
    $('studio-import')?.addEventListener('click',importAnswer);
    $('studio-api-generate')?.addEventListener('click',generateDirect);
    $('studio-drop-zone')?.addEventListener('click',()=>$('studio-file-input')?.click());
    $('studio-file-input')?.addEventListener('change',event=>selectGameFile(event.target.files?.[0]||null));
    $('studio-file-import')?.addEventListener('click',importFile);
    const drop=$('studio-drop-zone');
    if(drop){
      ['dragenter','dragover'].forEach(name=>drop.addEventListener(name,event=>{event.preventDefault();drop.classList.add('dragging')}));
      ['dragleave','drop'].forEach(name=>drop.addEventListener(name,event=>{event.preventDefault();drop.classList.remove('dragging')}));
      drop.addEventListener('drop',event=>selectGameFile(event.dataTransfer?.files?.[0]||null));
    }
    $('game-studio-player-close')?.addEventListener('click',stopGame);
    $('game-studio-stop')?.addEventListener('click',stopGame);
    $('game-studio-reload')?.addEventListener('click',()=>{if(currentGame){const frame=$('game-studio-frame');frame.srcdoc='';setTimeout(()=>frame.srcdoc=currentGame.document,30)}});
  }
  window.addEventListener('pichat:user-ready',async()=>{try{status=await api('/api/game-studio/status');if($('open-game-studio'))$('open-game-studio').style.display=status.enabled?'':'none';if(status.enabled&&new URLSearchParams(location.search).get('open')==='game-studio')openModal()}catch{if($('open-game-studio'))$('open-game-studio').style.display='none'}},{once:true});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
  window.PiGameStudio={open:openModal,load:loadAll};
})();

;
/* ===== community.js ===== */
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

;
/* ===== debug.js ===== */
/**
 * debug.js
 * --------
 * Petite console de diagnostic technique intégrée à la page, pensée
 * comme un outil de développeur discret (repliable, en bas de page) —
 * pas un menu de jeu vidéo. Utile pour voir rapidement, sans ouvrir
 * les outils du navigateur (F12), ce que l'application sait de l'état
 * courant : utilisateur connecté, rôle, salon actif, état du WebSocket.
 *
 * Pour retirer ce panneau en production, il suffit de supprimer :
 * - le bloc <footer id="debug-panel"> dans index.html
 * - la balise <script src="/js/debug.js"> dans index.html
 * - ce fichier
 */

document.addEventListener("DOMContentLoaded", () => {
    const toggleButton = document.getElementById("debug-toggle");
    const content = document.getElementById("debug-content");

    // Affiche immédiatement les infos de debug au chargement, sans
    // attendre un clic (utile en phase de mise au point).
    refreshDebugInfo();

    toggleButton.addEventListener("click", () => {
        const isVisible = content.style.display !== "none";
        content.style.display = isVisible ? "none" : "block";

        if (!isVisible) {
            refreshDebugInfo();
        }
    });
});

/**
 * Récupère l'état courant de l'application et l'affiche dans le panneau.
 * Fonction volontairement simple : elle lit des variables globales déjà
 * définies par les autres scripts (app.js, websocket.js) plutôt que de
 * dupliquer leur logique.
 */
async function refreshDebugInfo() {
    const logBox = document.getElementById("debug-log");

    let meResponseText = "(non appelé)";
    let meStatusCode = "-";

    try {
        const response = await fetch("/api/me", { credentials: "same-origin" });
        meStatusCode = response.status;
        const data = await response.json();
        meResponseText = JSON.stringify(data, null, 2);
    } catch (error) {
        meResponseText = `Erreur : ${error.message}`;
    }

    const wsState = typeof chatSocket !== "undefined" && chatSocket
        ? describeWebSocketState(chatSocket.readyState)
        : "non initialisé";

    const roomId = typeof currentRoomId !== "undefined" ? currentRoomId : "non défini";

    logBox.textContent =
        `--- /api/me (HTTP ${meStatusCode}) ---\n` +
        `${meResponseText}\n\n` +
        `--- État du chat ---\n` +
        `Salon actif (currentRoomId) : ${roomId}\n` +
        `État WebSocket : ${wsState}\n\n` +
        `--- Page ---\n` +
        `URL : ${window.location.href}\n` +
        `User-Agent : ${navigator.userAgent}`;
}

/**
 * Traduit le code numérique readyState d'un WebSocket en texte lisible.
 */
function describeWebSocketState(readyState) {
    const states = {
        0: "CONNECTING (0)",
        1: "OPEN (1)",
        2: "CLOSING (2)",
        3: "CLOSED (3)",
    };
    return states[readyState] || `Inconnu (${readyState})`;
}

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
/* ===== trolls.js ===== */
(() => {
  const STORAGE_KEY = 'pichat-user-ui';
  const state = { konami: [], timer: null };
  const konami = ['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a'];

  function prefs(){
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
    catch { return {}; }
  }
  function enabled(){ return prefs().trolls !== false; }

  function toast(text, ms=2600){
    if(!enabled()) return;
    let wrap=document.getElementById('pichat-troll-toast-wrap');
    if(!wrap){ wrap=document.createElement('div'); wrap.id='pichat-troll-toast-wrap'; wrap.className='troll-toast-wrap'; document.body.appendChild(wrap); }
    const el=document.createElement('div'); el.className='troll-toast'; el.textContent=text; wrap.appendChild(el);
    requestAnimationFrame(()=>el.classList.add('show'));
    setTimeout(()=>{el.classList.remove('show');setTimeout(()=>el.remove(),280)},ms);
  }

  function confetti(){
    if(!enabled()) return;
    const symbols=['✨','🎉','🟣','🔵','🟢','⭐','💫'];
    for(let i=0;i<55;i++){
      const s=document.createElement('span'); s.className='troll-confetti'; s.textContent=symbols[Math.floor(Math.random()*symbols.length)];
      s.style.left=(Math.random()*100)+'vw'; s.style.animationDelay=(Math.random()*.5)+'s'; s.style.animationDuration=(1.8+Math.random()*1.8)+'s';
      document.body.appendChild(s); setTimeout(()=>s.remove(),4200);
    }
    toast('Mode fête activé. Productivité : -73 % 😎');
  }

  function matrix(){
    if(!enabled()) return;
    document.body.classList.add('troll-matrix'); toast('Connexion au mainframe de la cantine…');
    setTimeout(()=>document.body.classList.remove('troll-matrix'),4500);
  }

  function flip(){
    if(!enabled()) return;
    document.body.classList.add('troll-flip'); toast('Oups. La gravité CSS a changé de sens.');
    setTimeout(()=>document.body.classList.remove('troll-flip'),1700);
  }

  function panic(){
    if(!enabled()) return;
    const overlay=document.createElement('div'); overlay.className='troll-panic';
    overlay.innerHTML='<div><strong>ERREUR CRITIQUE 418</strong><span>Café introuvable. PiChat refuse de travailler.</span><small>Réparation automatique en cours…</small></div>';
    document.body.appendChild(overlay); setTimeout(()=>overlay.classList.add('show'),20);
    setTimeout(()=>{overlay.classList.remove('show');setTimeout(()=>overlay.remove(),300)},2400);
  }

  function hamster(){
    const messages=[
      'Le hamster réseau pédale à 98 % 🐹',
      'Synchronisation avec le satellite du CDI…',
      'Optimisation du Wi‑Fi avec du scotch…',
      'Recherche d’un adulte responsable… aucun résultat.',
      'Ping vers Mars : étonnamment correct.',
      'PiChat a trouvé 0 devoir à faire. Suspect.'
    ];
    toast(messages[Math.floor(Math.random()*messages.length)],3000);
  }

  function localCommand(raw){
    if(!enabled()) return false;
    const cmd=String(raw||'').trim().toLowerCase();
    if(cmd==='/troll' || cmd==='/easteregg'){
      toast('Commandes secrètes : /confetti · /matrix · /flip · /panic · /hamster',5200); return true;
    }
    if(cmd==='/confetti'){confetti();return true}
    if(cmd==='/matrix'){matrix();return true}
    if(cmd==='/flip'){flip();return true}
    if(cmd==='/panic'){panic();return true}
    if(cmd==='/hamster'){hamster();return true}
    return false;
  }

  function installKonami(){
    document.addEventListener('keydown',e=>{
      if(!enabled()) return;
      state.konami.push(e.key); if(state.konami.length>konami.length) state.konami.shift();
      if(state.konami.join('|').toLowerCase()===konami.join('|').toLowerCase()){
        state.konami=[]; confetti(); setTimeout(matrix,400);
      }
    });
  }

  function installLogoEgg(){
    const logo=document.querySelector('.chat-logo,.brand-mark,.mini-logo,.mobile-logo');
    if(!logo) return;
    logo.title='PiChat';
    logo.addEventListener('dblclick',()=>{ if(enabled()){ hamster(); logo.classList.add('troll-logo-spin'); setTimeout(()=>logo.classList.remove('troll-logo-spin'),900); } });
  }

  function maybeRareTroll(){
    if(!enabled()) return;
    if(Math.random()<0.035) setTimeout(hamster,1800+Math.random()*2500);
  }

  window.PiChatTrolls={enabled,toast,confetti,matrix,flip,panic,hamster,handleLocalCommand:localCommand};
  const init=()=>{installKonami();installLogoEgg();maybeRareTroll();};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();

;
/* ===== discord104.js ===== */
(function(){
'use strict';
const $=id=>document.getElementById(id);
const COMMANDS=[
 ['/duel @pseudo','Défier un membre en duel'],['/roll 20','Lancer un dé'],['/coin','Pile ou face'],
 ['/rps pierre','Pierre-feuille-ciseaux'],['/8ball question','Poser une question à la boule magique'],
 ['/choose A | B','Choisir au hasard'],['/poll Question | A | B','Créer un sondage'],['/stats','Afficher ton profil de jeu']
];
let searchOverlay, switcherOverlay, commandBox;
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function initials(n){return String(n||'?').slice(0,2).toUpperCase()}
function makeOverlay(id,placeholder){
 const root=document.createElement('div');root.id=id;root.className='d104-overlay';
 root.innerHTML=`<section class="d104-dialog"><div class="d104-search-head"><input autocomplete="off" placeholder="${esc(placeholder)}"></div><div class="d104-search-meta">PiChat 1.1.0</div><div class="d104-results"></div></section>`;
 document.body.append(root);root.addEventListener('mousedown',e=>{if(e.target===root)closeOverlay(root)});return root;
}
function closeOverlay(root){root?.classList.remove('open')}
function openSearch(){
 if(!searchOverlay){searchOverlay=makeOverlay('d104-search','Rechercher dans les messages du salon');const input=searchOverlay.querySelector('input');input.addEventListener('input',()=>renderSearch(input.value));}
 searchOverlay.classList.add('open');const input=searchOverlay.querySelector('input');input.value='';renderSearch('');setTimeout(()=>input.focus(),30);
}
function renderSearch(q){
 const out=searchOverlay.querySelector('.d104-results');const meta=searchOverlay.querySelector('.d104-search-meta');q=q.trim().toLowerCase();
 const rows=[...document.querySelectorAll('.message-item')].map(el=>({el,author:el.querySelector('.message-author')?.textContent||'?',text:el.querySelector('.message-content')?.textContent||el.querySelector('.message-card')?.textContent||''})).filter(x=>!q||`${x.author} ${x.text}`.toLowerCase().includes(q)).slice(-80).reverse();
 meta.textContent=q?`${rows.length} résultat(s) dans #${$('current-room-name')?.textContent||'salon'}`:`Messages récents dans #${$('current-room-name')?.textContent||'salon'}`;
 out.innerHTML='';if(!rows.length){out.innerHTML='<div class="d104-empty">Aucun message trouvé.</div>';return}
 rows.forEach(x=>{const b=document.createElement('button');b.className='d104-result';b.innerHTML=`<span class="d104-result-icon">${esc(initials(x.author))}</span><span><strong>${esc(x.author)}</strong><small>${esc(x.text.slice(0,180)||'Message interactif')}</small></span>`;b.onclick=()=>{closeOverlay(searchOverlay);x.el.scrollIntoView({block:'center',behavior:'smooth'});x.el.classList.remove('highlight-search');requestAnimationFrame(()=>x.el.classList.add('highlight-search'));};out.append(b)});
}
function openSwitcher(){
 if(!switcherOverlay){switcherOverlay=makeOverlay('d104-switcher','Où veux-tu aller ?');const input=switcherOverlay.querySelector('input');input.addEventListener('input',()=>renderSwitcher(input.value));}
 switcherOverlay.classList.add('open');const input=switcherOverlay.querySelector('input');input.value='';renderSwitcher('');setTimeout(()=>input.focus(),30);
}
function renderSwitcher(q){
 const out=switcherOverlay.querySelector('.d104-results');const rooms=window.CURRENT_ROOMS||[];q=q.trim().toLowerCase();const filtered=rooms.filter(r=>!q||`${r.name} ${r.class_code||''}`.toLowerCase().includes(q));
 switcherOverlay.querySelector('.d104-search-meta').textContent=`${filtered.length} salon(s) disponible(s)`;out.innerHTML='';filtered.forEach((r,i)=>{const b=document.createElement('button');b.className='d104-result'+(i===0?' active':'');b.innerHTML=`<span class="d104-result-icon">#</span><span><strong>${esc(r.name)}</strong><small>${esc(r.class_code?`Serveur de classe ${r.class_code}`:'Salon général')}</small></span>`;b.onclick=()=>{closeOverlay(switcherOverlay);window.switchRoom?.(r.id)};out.append(b)});if(!filtered.length)out.innerHTML='<div class="d104-empty">Aucun salon trouvé.</div>';
}
function showContext(e,item){
 e.preventDefault();document.querySelector('.d104-context')?.remove();const menu=document.createElement('div');menu.className='d104-context';
 const add=(label,icon,fn,cls='')=>{const b=document.createElement('button');b.className=cls;b.innerHTML=`<span>${esc(label)}</span><span>${icon}</span>`;b.onclick=()=>{menu.remove();fn()};menu.append(b)};
 add('Ajouter une réaction','☺',()=>item.querySelector('.message-actions button:first-child')?.click());
 add('Copier le texte','⌘C',async()=>{const text=item.querySelector('.message-content')?.textContent||item.querySelector('.message-card')?.textContent||'';try{await navigator.clipboard.writeText(text)}catch{}});
 add('Signaler le message','⚑',()=>item.querySelector('.message-actions button:last-child')?.click(),'danger');
 document.body.append(menu);const w=200,h=110;menu.style.left=Math.min(innerWidth-w-8,Math.max(8,e.clientX))+'px';menu.style.top=Math.min(innerHeight-h-8,Math.max(8,e.clientY))+'px';
 setTimeout(()=>document.addEventListener('mousedown',ev=>{if(!menu.contains(ev.target))menu.remove()},{once:true}),0);
}
function decorateText(root){
 if(!root||root.dataset.d104Decorated)return;root.dataset.d104Decorated='1';const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement?.closest('.profanity-blur,.mention-token,.chat-link')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
 nodes.forEach(n=>{const s=n.nodeValue;if(!/(@[\wÀ-ÿ.-]+|https?:\/\/[^\s]+)/i.test(s))return;const frag=document.createDocumentFragment();let last=0;const re=/(@[\wÀ-ÿ.-]+|https?:\/\/[^\s]+)/gi;for(const m of s.matchAll(re)){if(m.index>last)frag.append(document.createTextNode(s.slice(last,m.index)));if(m[0][0]==='@'){const sp=document.createElement('span');sp.className='mention-token';sp.textContent=m[0];frag.append(sp)}else{const a=document.createElement('a');a.className='chat-link';a.href=m[0];a.target='_blank';a.rel='noopener noreferrer';a.textContent=m[0];frag.append(a)}last=m.index+m[0].length}if(last<s.length)frag.append(document.createTextNode(s.slice(last)));n.replaceWith(frag)});
}
function bindMessageEnhancements(){
 const list=$('messages-list');if(!list)return;const enhance=item=>{if(item.dataset.d104Bound)return;item.dataset.d104Bound='1';item.addEventListener('contextmenu',e=>showContext(e,item));let timer;item.addEventListener('touchstart',e=>{timer=setTimeout(()=>{item.classList.toggle('mobile-actions');navigator.vibrate?.(18)},520)},{passive:true});['touchend','touchmove','touchcancel'].forEach(x=>item.addEventListener(x,()=>clearTimeout(timer),{passive:true}));decorateText(item.querySelector('.message-content'))};
 [...list.querySelectorAll('.message-item')].forEach(enhance);new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(n=>{if(n.nodeType!==1)return;if(n.matches?.('.message-item'))enhance(n);n.querySelectorAll?.('.message-item').forEach(enhance)}))).observe(list,{childList:true,subtree:true});
}
function setupHeader(){
 const spacer=document.querySelector('.channel-header-spacer');if(!spacer)return;
 const quick=document.createElement('button');quick.id='d104-quick-switcher';quick.className='header-action hide-mobile';quick.title='Changer de salon (⌘K)';quick.textContent='⌘K';quick.onclick=openSwitcher;spacer.after(quick);
 const search=document.createElement('button');search.id='d104-search-trigger';search.className='discord-search-trigger';search.innerHTML='<span>Rechercher</span><kbd>⌘F</kbd>';search.onclick=openSearch;quick.after(search);
 const help=document.createElement('button');help.className='header-action hide-mobile';help.title='Aide';help.textContent='?';help.onclick=()=>$('help-button')?.click();search.after(help);
}
function setupDock(){
 const profile=$('dock-profile-button');if(!profile)return;const controls=document.createElement('span');controls.className='dock-voice-controls';controls.innerHTML='<button type="button" class="dock-action" id="d104-mute" title="Couper le micro (visuel)">🎙</button><button type="button" class="dock-action" id="d104-deafen" title="Mode silencieux (visuel)">🎧</button>';profile.after(controls);
 $('d104-mute').onclick=e=>{e.currentTarget.classList.toggle('is-muted');e.currentTarget.textContent=e.currentTarget.classList.contains('is-muted')?'🔇':'🎙'};
 $('d104-deafen').onclick=e=>{e.currentTarget.classList.toggle('is-deafened');e.currentTarget.textContent=e.currentTarget.classList.contains('is-deafened')?'🔕':'🎧'};
}
function setupCommandSuggestions(){
 const form=$('message-form'),input=$('message-input');if(!form||!input)return;commandBox=document.createElement('div');commandBox.className='command-suggestions';form.parentElement.append(commandBox);
 const render=()=>{const v=input.value.trimStart();if(!v.startsWith('/')){commandBox.classList.remove('open');return}const q=v.toLowerCase();const xs=COMMANDS.filter(([c,d])=>`${c} ${d}`.toLowerCase().includes(q)).slice(0,8);commandBox.innerHTML='';xs.forEach(([c,d],i)=>{const b=document.createElement('button');b.type='button';b.className='command-suggestion'+(i===0?' active':'');b.innerHTML=`<b>${esc(c)}</b><small>${esc(d)}</small>`;b.onclick=()=>{input.value=c;input.focus();commandBox.classList.remove('open')};commandBox.append(b)});commandBox.classList.toggle('open',xs.length>0)};input.addEventListener('input',render);input.addEventListener('keydown',e=>{if(e.key==='Escape')commandBox.classList.remove('open')});document.addEventListener('mousedown',e=>{if(!commandBox.contains(e.target)&&e.target!==input)commandBox.classList.remove('open')});
}
function setTooltips(){document.querySelectorAll('.server-icon').forEach(x=>x.dataset.tooltip=x.title||x.getAttribute('aria-label')||'PiChat');const rail=$('server-list');if(rail)new MutationObserver(()=>document.querySelectorAll('.server-icon').forEach(x=>x.dataset.tooltip=x.title||'Serveur')).observe(rail,{childList:true})}
function init(){
 document.body.classList.add('d104-ready');setupHeader();setupDock();setupCommandSuggestions();bindMessageEnhancements();setTooltips();
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeOverlay(searchOverlay);closeOverlay(switcherOverlay);document.querySelector('.d104-context')?.remove()}if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openSwitcher()}if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='f'&&!['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)){e.preventDefault();openSearch()}});
}
window.PiChatDiscord104={openSearch,openSwitcher,decorateText};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();

;
/* ===== mobile112.js ===== */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const isMobile = () => matchMedia('(max-width: 820px), (hover: none) and (pointer: coarse)').matches;
  let touch = null;
  let syntheticTarget = null;
  let syntheticAt = 0;

  function setViewport(){
    const viewport = window.visualViewport;
    const height = Math.round(viewport?.height || window.innerHeight || document.documentElement.clientHeight);
    const offsetTop = Math.round(viewport?.offsetTop || 0);
    document.documentElement.style.setProperty('--pichat-viewport-height', `${height}px`);
    document.documentElement.style.setProperty('--pichat-viewport-offset', `${offsetTop}px`);
  }

  function interactiveTarget(node){
    if(!(node instanceof Element)) return null;
    const target = node.closest('button,a[href],[role="button"],.channel-button,.server-icon,.member-row,.reaction-chip');
    if(!target || target.matches('[disabled],[aria-disabled="true"]')) return null;
    if(target.closest('input,textarea,select')) return null;
    return target;
  }

  function installReliableTap(){
    // Safari iOS peut perdre certains clics dans une grille fixe/PWA. On
    // transforme uniquement un vrai toucher immobile en click synthétique.
    document.addEventListener('touchstart', event => {
      if(!isMobile() || event.touches.length !== 1) return;
      const target = interactiveTarget(event.target);
      if(!target) return;
      const point = event.touches[0];
      touch = {target, x: point.clientX, y: point.clientY, moved: false, at: Date.now()};
    }, {passive:true, capture:true});

    document.addEventListener('touchmove', event => {
      if(!touch || !event.touches.length) return;
      const point = event.touches[0];
      if(Math.abs(point.clientX-touch.x)>9 || Math.abs(point.clientY-touch.y)>9) touch.moved=true;
    }, {passive:true, capture:true});

    document.addEventListener('touchcancel', () => { touch=null; }, {passive:true, capture:true});
    document.addEventListener('touchend', event => {
      if(!touch) return;
      const current = touch; touch=null;
      if(current.moved || Date.now()-current.at>750) return;
      const endedOn = interactiveTarget(event.target);
      if(!endedOn || endedOn !== current.target) return;
      event.preventDefault();
      syntheticTarget=current.target; syntheticAt=Date.now();
      current.target.click();
    }, {passive:false, capture:true});

    // Bloque le click fantôme généré ensuite par Safari, mais laisse passer le
    // click synthétique (isTrusted=false) qui exécute le vrai gestionnaire.
    document.addEventListener('click', event => {
      if(!event.isTrusted) return;
      if(syntheticTarget && Date.now()-syntheticAt<700 && (event.target===syntheticTarget || syntheticTarget.contains(event.target))){
        event.preventDefault(); event.stopImmediatePropagation();
      }
    }, true);
  }

  function closeDrawers(){
    $('channel-panel')?.classList.remove('open');
    $('member-panel')?.classList.remove('open');
    $('mobile-overlay')?.classList.remove('open');
  }

  function repairShell(){
    if(!isMobile()) return;
    document.body.classList.add('pichat-mobile-ready');
    const shell=$('chat-section');
    if(shell && shell.style.display!=='none') shell.style.display='grid';
    const nav=$('mobile-bottom-nav');
    if(nav && shell && shell.style.display!=='none') nav.style.display='grid';
    const list=$('messages-list');
    if(list){
      list.style.webkitOverflowScrolling='touch';
      list.setAttribute('data-touch-ready','true');
    }
  }

  function keyboardRepair(){
    const input=$('message-input'); if(!input) return;
    input.addEventListener('focus',()=>setTimeout(()=>{setViewport();input.scrollIntoView({block:'nearest'})},180));
    input.addEventListener('blur',()=>setTimeout(setViewport,120));
  }

  function init(){
    setViewport(); repairShell(); installReliableTap(); keyboardRepair();
    window.visualViewport?.addEventListener('resize',()=>{setViewport();repairShell()});
    window.visualViewport?.addEventListener('scroll',setViewport);
    window.addEventListener('resize',()=>{setViewport();repairShell()});
    window.addEventListener('orientationchange',()=>setTimeout(()=>{setViewport();repairShell();closeDrawers()},220));
    document.addEventListener('visibilitychange',()=>{if(!document.hidden){setViewport();repairShell()}});
    window.addEventListener('pichat:room-changed',closeDrawers);
    new MutationObserver(repairShell).observe(document.body,{attributes:true,subtree:true,attributeFilter:['style','class']});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();

;
/* ===== economy113.js ===== */
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

;
/* ===== spaces_switcher_v2.js ===== */
(()=>{async function init(){const panel=document.querySelector('.channel-panel');const header=panel?.querySelector('.server-header');if(!panel||!header)return;try{const r=await fetch('/api/spaces',{credentials:'same-origin',cache:'no-store'});if(!r.ok)return;const spaces=await r.json();if(!spaces.length)return;const strip=document.createElement('div');strip.className='v2-space-strip';spaces.forEach(s=>{const b=document.createElement('button');b.className='v2-space-pill'+(s.active?' active':'');b.innerHTML=`<span>${s.icon||'🏫'}</span>${s.name}`;b.onclick=async()=>{if(s.active){location.href='/spaces';return}const x=await fetch(`/api/spaces/${s.id}/switch`,{method:'POST',credentials:'same-origin'});if(x.ok)location.reload()};strip.append(b)});header.after(strip)}catch{}}document.addEventListener('DOMContentLoaded',init)})();
;
/* ===== v21.js ===== */
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

;
/* ===== final_packs.js ===== */
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

