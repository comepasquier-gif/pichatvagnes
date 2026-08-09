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
