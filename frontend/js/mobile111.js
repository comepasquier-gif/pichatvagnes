(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  function setViewport(){
    const h=window.visualViewport?.height||window.innerHeight;
    document.documentElement.style.setProperty('--pichat-viewport-height',`${Math.round(h)}px`);
  }
  function repairMobileShell(){
    if(!matchMedia('(max-width: 820px)').matches)return;
    const shell=$('chat-section');
    if(shell && shell.style.display!=='none') shell.style.display='grid';
    const nav=$('mobile-bottom-nav');
    if(nav && shell && shell.style.display!=='none') nav.style.display='grid';
    document.body.classList.add('pichat-mobile-ready');
  }
  function detectZoom(){
    const scale=window.visualViewport?.scale||1;
    if(scale<0.9||scale>1.15){
      window.PiChatPWA?.toast?.('Affichage zoomé : remets le zoom Safari à 100 %');
    }
  }
  function init(){
    setViewport();repairMobileShell();detectZoom();
    window.visualViewport?.addEventListener('resize',()=>{setViewport();repairMobileShell()});
    window.addEventListener('orientationchange',()=>setTimeout(()=>{setViewport();repairMobileShell()},180));
    window.addEventListener('resize',repairMobileShell);
    new MutationObserver(repairMobileShell).observe(document.documentElement,{attributes:true,subtree:true,attributeFilter:['style','class']});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
