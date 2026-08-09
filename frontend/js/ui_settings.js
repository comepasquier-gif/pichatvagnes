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
