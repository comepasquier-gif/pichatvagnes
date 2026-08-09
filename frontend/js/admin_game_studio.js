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
