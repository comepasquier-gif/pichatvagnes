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
