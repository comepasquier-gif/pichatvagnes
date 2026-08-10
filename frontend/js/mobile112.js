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
