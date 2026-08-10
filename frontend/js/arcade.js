(()=>{
  const $=id=>document.getElementById(id);
  let dashboard=null,currentSession=null,currentGame='clicker',memoryTimer=null,clickerTimer=null,reflexTimer=null;

  async function api(url,options={}){
    const response=await fetch(url,{credentials:'same-origin',...options});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.detail||'Erreur Arcade.');
    return data;
  }
  function esc(value){return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
  function clearTimers(){if(memoryTimer)clearInterval(memoryTimer);if(clickerTimer)clearInterval(clickerTimer);if(reflexTimer)clearTimeout(reflexTimer);memoryTimer=clickerTimer=reflexTimer=null}
  function setResult(text,type=''){const el=$('arcade-result');if(!el)return;el.textContent=text||'';el.className='arcade-result '+type}

  async function loadDashboard(game=currentGame){
    try{
      dashboard=await api('/api/arcade/dashboard?game='+encodeURIComponent(game));
      currentGame=dashboard.leaderboard_game||game;
      renderDashboard();
    }catch(error){setResult(error.message,'error');const list=$('arcade-game-list');if(list)list.innerHTML='<p class="muted">'+esc(error.message)+'</p>'}
  }

  function renderDashboard(){
    if(!dashboard)return;
    const list=$('arcade-game-list');
    if(list){list.innerHTML=dashboard.catalog.map(game=>`<button class="arcade-game-card ${currentSession?.game_key===game.key?'active':''}" data-arcade-game="${game.key}"><span class="icon">${game.icon}</span><span><b>${esc(game.name)}</b><small>${esc(game.description)}</small></span></button>`).join('');list.querySelectorAll('[data-arcade-game]').forEach(button=>button.onclick=()=>startGame(button.dataset.arcadeGame))}
    const select=$('arcade-leaderboard-game');
    if(select){const old=select.value;select.innerHTML=dashboard.catalog.map(game=>`<option value="${game.key}">${game.icon} ${esc(game.name)}</option>`).join('');select.value=dashboard.leaderboard_game||old||'clicker'}
    const challenge=dashboard.daily_challenge;const progress=Math.min(100,Math.round((challenge.today_best||0)/Math.max(1,challenge.target_score)*100));
    const daily=$('arcade-daily');if(daily)daily.innerHTML=`<strong>${challenge.completed?'✅':'🎯'} Défi du jour</strong><p>${challenge.icon} Atteins <b>${challenge.target_score} points</b> à ${esc(challenge.game_name)}.</p><div class="arcade-daily-progress"><span style="width:${progress}%"></span></div><small class="${challenge.completed?'arcade-daily-done':''}">${challenge.completed?'Récompense récupérée':`${challenge.today_best||0} / ${challenge.target_score}`} · 🪙 ${challenge.reward_coins} · ✨ ${challenge.reward_xp} XP</small>`;
    const sum=dashboard.summary;const summary=$('arcade-summary');if(summary)summary.innerHTML=`<div class="arcade-stat"><b>${sum.plays}</b><small>parties</small></div><div class="arcade-stat"><b>${sum.coins_earned}</b><small>PyCoins gagnés</small></div><div class="arcade-stat"><b>${sum.wallet}</b><small>dans le portefeuille</small></div><div class="arcade-stat"><b>${sum.xp}</b><small>XP total</small></div>`;
    const board=$('arcade-leaderboard');if(board)board.innerHTML=dashboard.leaderboard.length?dashboard.leaderboard.map((row,index)=>`<div class="arcade-rank"><span>${index<3?['🥇','🥈','🥉'][index]:index+1}</span><strong>${esc(row.username)}</strong><small>${row.best_score}</small></div>`).join(''):'<p class="muted">Aucun score pour le moment.</p>';
  }

  function gameHead(session){return `<div class="arcade-game-head"><div class="arcade-big-icon">${session.game.icon}</div><h3>${esc(session.game.name)}</h3><p>${esc(session.game.description)}</p></div>`}

  async function startGame(gameKey){
    clearTimers();setResult('');
    const stage=$('arcade-stage');if(stage)stage.innerHTML='<div class="arcade-welcome"><span>⏳</span><h3>Préparation de la partie…</h3></div>';
    try{
      currentSession=await api('/api/arcade/start/'+encodeURIComponent(gameKey),{method:'POST'});
      currentGame=gameKey;renderDashboard();renderGame(currentSession);
    }catch(error){setResult(error.message,'error');if(stage)stage.innerHTML='<div class="arcade-welcome"><span>⚠️</span><h3>Impossible de lancer le jeu</h3><p>'+esc(error.message)+'</p></div>'}
  }

  function renderGame(session){
    if(session.game_key==='number')return renderNumber(session);
    if(session.game_key==='quiz')return renderQuiz(session);
    if(session.game_key==='memory')return renderMemory(session);
    if(session.game_key==='reflex')return renderReflex(session);
    if(session.game_key==='clicker')return renderClicker(session);
    if(session.game_key==='tictactoe')return renderTicTacToe(session.board||Array(9).fill(''),'À toi de jouer : tu es X.');
  }

  async function action(payload){return api('/api/arcade/sessions/'+encodeURIComponent(currentSession.session_id)+'/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})}

  function renderNumber(session){
    const stage=$('arcade-stage');stage.innerHTML=`<div class="arcade-game-screen">${gameHead(session)}<div id="number-hint" class="arcade-hint">Entre ton premier nombre.</div><div class="arcade-number-box"><input id="number-guess" type="number" min="1" max="100" value="50"><button id="number-submit" class="arcade-primary">Essayer</button></div><div id="number-attempts" class="arcade-attempts">0 tentative</div></div>`;
    const submit=async()=>{try{const value=Number($('number-guess').value);const result=await action({action:'guess',guess:value});if(result.completed)return completeGame(result);$('number-hint').textContent=result.hint==='higher'?'⬆️ Plus haut !':'⬇️ Plus bas !';$('number-attempts').textContent=result.attempts+' tentative'+(result.attempts>1?'s':'');$('number-guess').focus();$('number-guess').select()}catch(error){setResult(error.message,'error')}};
    $('number-submit').onclick=submit;$('number-guess').onkeydown=e=>{if(e.key==='Enter')submit()};$('number-guess').focus();
  }

  function renderQuiz(session){
    const stage=$('arcade-stage');stage.innerHTML=`<form id="arcade-quiz-form" class="arcade-game-screen"><div>${gameHead(session)}</div><div class="arcade-quiz">${session.questions.map((item,index)=>`<div class="arcade-question"><strong>${index+1}. ${esc(item.question)}</strong>${item.options.map((option,opt)=>`<label><input type="radio" name="q${index}" value="${opt}"> ${esc(option)}</label>`).join('')}</div>`).join('')}</div><button class="arcade-primary">Valider les réponses</button></form>`;
    $('arcade-quiz-form').onsubmit=async event=>{event.preventDefault();const answers=session.questions.map((_,index)=>{const picked=document.querySelector(`input[name="q${index}"]:checked`);return picked?Number(picked.value):-1});if(answers.some(x=>x<0)){setResult('Réponds à toutes les questions.','error');return}try{completeGame(await action({action:'submit',answers}))}catch(error){setResult(error.message,'error')}};
  }

  function renderMemory(session){
    const stage=$('arcade-stage');const started=Date.now();let first=null,lock=false,matches=0,moves=0;
    stage.innerHTML=`<div class="arcade-game-screen">${gameHead(session)}<div class="arcade-memory-meta"><span id="memory-moves">0 coup</span><span id="memory-time">0.0 s</span></div><div id="memory-grid" class="arcade-memory-grid">${session.cards.map((_,index)=>`<button class="arcade-memory-card" data-index="${index}">❔</button>`).join('')}</div></div>`;
    memoryTimer=setInterval(()=>{const el=$('memory-time');if(el)el.textContent=((Date.now()-started)/1000).toFixed(1)+' s'},100);
    const cards=[...$('memory-grid').querySelectorAll('.arcade-memory-card')];
    cards.forEach(button=>button.onclick=async()=>{if(lock||button.classList.contains('matched')||button===first)return;const index=Number(button.dataset.index);button.textContent=session.cards[index];button.classList.add('revealed');if(!first){first=button;return}moves++;$('memory-moves').textContent=moves+' coup'+(moves>1?'s':'');const firstIndex=Number(first.dataset.index);if(session.cards[firstIndex]===session.cards[index]){first.classList.add('matched');button.classList.add('matched');first=null;matches++;if(matches===session.pairs){clearTimers();try{completeGame(await action({action:'finish',moves,elapsed_ms:Date.now()-started}))}catch(error){setResult(error.message,'error')}}}else{lock=true;setTimeout(()=>{first.textContent='❔';button.textContent='❔';first.classList.remove('revealed');button.classList.remove('revealed');first=null;lock=false},650)}});
  }

  function renderReflex(session){
    const stage=$('arcade-stage');stage.innerHTML=`<div class="arcade-game-screen">${gameHead(session)}<button id="reflex-pad" class="arcade-reflex-pad">Attends le vert…</button><p class="muted" style="text-align:center">Un clic trop tôt termine la manche.</p></div>`;
    const pad=$('reflex-pad');let ready=false;reflexTimer=setTimeout(()=>{ready=true;pad.classList.add('ready');pad.textContent='CLIQUE !'},session.wait_ms);
    pad.onclick=async()=>{pad.disabled=true;clearTimers();try{const result=await action({action:'tap'});if(result.failed){setResult('Trop tôt ! Relance une partie.','error');return renderFailed(session,'⏱️','Trop tôt !')}completeGame(result)}catch(error){setResult(error.message,'error')}};
  }

  function renderClicker(session){
    const stage=$('arcade-stage');let clicks=0;let remaining=session.duration_ms;const started=Date.now();stage.innerHTML=`<div class="arcade-game-screen">${gameHead(session)}<div class="arcade-clicker-meta"><span id="clicker-count">0 clic</span><span id="clicker-time">10.0 s</span></div><button id="clicker-button" class="arcade-clicker-button">CLIQUE !</button></div>`;
    const button=$('clicker-button');button.onclick=()=>{clicks++;$('clicker-count').textContent=clicks+' clic'+(clicks>1?'s':'')};
    clickerTimer=setInterval(async()=>{remaining=Math.max(0,session.duration_ms-(Date.now()-started));const timeEl=$('clicker-time');if(timeEl)timeEl.textContent=(remaining/1000).toFixed(1)+' s';if(remaining<=0){clearTimers();button.disabled=true;button.textContent='TERMINÉ';try{completeGame(await action({action:'finish',clicks}))}catch(error){setResult(error.message,'error')}}},50);
  }

  function renderTicTacToe(board,status){
    const session=currentSession;const stage=$('arcade-stage');stage.innerHTML=`<div class="arcade-game-screen">${gameHead(session)}<div id="ttt-status" class="arcade-ttt-status">${esc(status)}</div><div class="arcade-ttt-grid">${board.map((value,index)=>`<button class="arcade-ttt-cell" data-cell="${index}" ${value?'disabled':''}>${value==='X'?'❌':value==='O'?'⭕':''}</button>`).join('')}</div></div>`;
    stage.querySelectorAll('[data-cell]').forEach(button=>button.onclick=async()=>{stage.querySelectorAll('[data-cell]').forEach(x=>x.disabled=true);try{const result=await action({action:'move',cell:Number(button.dataset.cell)});if(result.completed)return completeGame(result);renderTicTacToe(result.board,'PiBot a joué. À toi !')}catch(error){setResult(error.message,'error');renderTicTacToe(board,'À toi de jouer.')}});
  }

  function renderFailed(session,icon,title){const stage=$('arcade-stage');stage.innerHTML=`<div class="arcade-end-card"><div class="result-icon">${icon}</div><h3>${esc(title)}</h3><p>Cette manche n’est pas comptabilisée.</p><button id="arcade-replay" class="arcade-primary">Rejouer</button></div>`;$('arcade-replay').onclick=()=>startGame(session.game_key)}

  async function completeGame(result){
    clearTimers();const game=currentSession?.game||{icon:'🎮',name:'Mini-jeu'};const reward=result.reward||{};const daily=result.daily_challenge_bonus||{};const stage=$('arcade-stage');
    stage.innerHTML=`<div class="arcade-end-card"><div class="result-icon">${result.failed?'⏱️':game.icon}</div><h3>${esc(result.result_label||'Partie terminée')}</h3><p>Score : <strong>${result.score||0} points</strong></p><div class="arcade-reward-line">${reward.coins?`<span class="arcade-reward-chip">🪙 +${reward.coins}</span>`:''}${reward.xp?`<span class="arcade-reward-chip">✨ +${reward.xp} XP</span>`:''}${daily.claimed?`<span class="arcade-reward-chip daily">🎯 Défi réussi · +${daily.coins} 🪙 · +${daily.xp} XP</span>`:''}${!reward.coins&&!reward.xp&&!daily.claimed?'<span class="arcade-reward-chip">Record enregistré</span>':''}</div><button id="arcade-replay" class="arcade-primary">Rejouer</button> <button id="arcade-other" class="arcade-secondary">Choisir un autre jeu</button></div>`;
    setResult(daily.claimed?'Défi du jour réussi !':reward.coins?'Récompense ajoutée à ton portefeuille.':'Score enregistré.',daily.claimed||reward.coins?'reward':'success');
    $('arcade-replay').onclick=()=>startGame(currentSession.game_key);$('arcade-other').onclick=()=>{currentSession=null;stage.innerHTML='<div class="arcade-welcome"><span>🕹️</span><h3>Choisis un mini-jeu</h3><p>Les cartes sont disponibles à gauche.</p></div>';renderDashboard()};
    await loadDashboard(currentGame);
  }

  function bind(){
    $('open-games')?.addEventListener('click',()=>loadDashboard(currentGame));
    $('arcade-refresh')?.addEventListener('click',()=>loadDashboard(currentGame));
    $('arcade-leaderboard-game')?.addEventListener('change',event=>loadDashboard(event.target.value));
  }
  bind();
  window.PiChatArcade={load:loadDashboard,start:startGame};
})();
