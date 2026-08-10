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
