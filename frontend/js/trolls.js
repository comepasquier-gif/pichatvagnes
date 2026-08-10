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
