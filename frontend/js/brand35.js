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
