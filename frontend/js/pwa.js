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
      registration=await navigator.serviceWorker.register('/service-worker.js?v=3630',{scope:'/',updateViaCache:'none'});
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
