(function(){
'use strict';
const $=id=>document.getElementById(id);
const COMMANDS=[
 ['/duel @pseudo','Défier un membre en duel'],['/roll 20','Lancer un dé'],['/coin','Pile ou face'],
 ['/rps pierre','Pierre-feuille-ciseaux'],['/8ball question','Poser une question à la boule magique'],
 ['/choose A | B','Choisir au hasard'],['/poll Question | A | B','Créer un sondage'],['/stats','Afficher ton profil de jeu']
];
let searchOverlay, switcherOverlay, commandBox;
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function initials(n){return String(n||'?').slice(0,2).toUpperCase()}
function makeOverlay(id,placeholder){
 const root=document.createElement('div');root.id=id;root.className='d104-overlay';
 root.innerHTML=`<section class="d104-dialog"><div class="d104-search-head"><input autocomplete="off" placeholder="${esc(placeholder)}"></div><div class="d104-search-meta">PiChat 1.1.0</div><div class="d104-results"></div></section>`;
 document.body.append(root);root.addEventListener('mousedown',e=>{if(e.target===root)closeOverlay(root)});return root;
}
function closeOverlay(root){root?.classList.remove('open')}
function openSearch(){
 if(!searchOverlay){searchOverlay=makeOverlay('d104-search','Rechercher dans les messages du salon');const input=searchOverlay.querySelector('input');input.addEventListener('input',()=>renderSearch(input.value));}
 searchOverlay.classList.add('open');const input=searchOverlay.querySelector('input');input.value='';renderSearch('');setTimeout(()=>input.focus(),30);
}
function renderSearch(q){
 const out=searchOverlay.querySelector('.d104-results');const meta=searchOverlay.querySelector('.d104-search-meta');q=q.trim().toLowerCase();
 const rows=[...document.querySelectorAll('.message-item')].map(el=>({el,author:el.querySelector('.message-author')?.textContent||'?',text:el.querySelector('.message-content')?.textContent||el.querySelector('.message-card')?.textContent||''})).filter(x=>!q||`${x.author} ${x.text}`.toLowerCase().includes(q)).slice(-80).reverse();
 meta.textContent=q?`${rows.length} résultat(s) dans #${$('current-room-name')?.textContent||'salon'}`:`Messages récents dans #${$('current-room-name')?.textContent||'salon'}`;
 out.innerHTML='';if(!rows.length){out.innerHTML='<div class="d104-empty">Aucun message trouvé.</div>';return}
 rows.forEach(x=>{const b=document.createElement('button');b.className='d104-result';b.innerHTML=`<span class="d104-result-icon">${esc(initials(x.author))}</span><span><strong>${esc(x.author)}</strong><small>${esc(x.text.slice(0,180)||'Message interactif')}</small></span>`;b.onclick=()=>{closeOverlay(searchOverlay);x.el.scrollIntoView({block:'center',behavior:'smooth'});x.el.classList.remove('highlight-search');requestAnimationFrame(()=>x.el.classList.add('highlight-search'));};out.append(b)});
}
function openSwitcher(){
 if(!switcherOverlay){switcherOverlay=makeOverlay('d104-switcher','Où veux-tu aller ?');const input=switcherOverlay.querySelector('input');input.addEventListener('input',()=>renderSwitcher(input.value));}
 switcherOverlay.classList.add('open');const input=switcherOverlay.querySelector('input');input.value='';renderSwitcher('');setTimeout(()=>input.focus(),30);
}
function renderSwitcher(q){
 const out=switcherOverlay.querySelector('.d104-results');const rooms=window.CURRENT_ROOMS||[];q=q.trim().toLowerCase();const filtered=rooms.filter(r=>!q||`${r.name} ${r.class_code||''}`.toLowerCase().includes(q));
 switcherOverlay.querySelector('.d104-search-meta').textContent=`${filtered.length} salon(s) disponible(s)`;out.innerHTML='';filtered.forEach((r,i)=>{const b=document.createElement('button');b.className='d104-result'+(i===0?' active':'');b.innerHTML=`<span class="d104-result-icon">#</span><span><strong>${esc(r.name)}</strong><small>${esc(r.class_code?`Serveur de classe ${r.class_code}`:'Salon général')}</small></span>`;b.onclick=()=>{closeOverlay(switcherOverlay);window.switchRoom?.(r.id)};out.append(b)});if(!filtered.length)out.innerHTML='<div class="d104-empty">Aucun salon trouvé.</div>';
}
function showContext(e,item){
 e.preventDefault();document.querySelector('.d104-context')?.remove();const menu=document.createElement('div');menu.className='d104-context';
 const add=(label,icon,fn,cls='')=>{const b=document.createElement('button');b.className=cls;b.innerHTML=`<span>${esc(label)}</span><span>${icon}</span>`;b.onclick=()=>{menu.remove();fn()};menu.append(b)};
 add('Ajouter une réaction','☺',()=>item.querySelector('.message-actions button:first-child')?.click());
 add('Copier le texte','⌘C',async()=>{const text=item.querySelector('.message-content')?.textContent||item.querySelector('.message-card')?.textContent||'';try{await navigator.clipboard.writeText(text)}catch{}});
 add('Signaler le message','⚑',()=>item.querySelector('.message-actions button:last-child')?.click(),'danger');
 document.body.append(menu);const w=200,h=110;menu.style.left=Math.min(innerWidth-w-8,Math.max(8,e.clientX))+'px';menu.style.top=Math.min(innerHeight-h-8,Math.max(8,e.clientY))+'px';
 setTimeout(()=>document.addEventListener('mousedown',ev=>{if(!menu.contains(ev.target))menu.remove()},{once:true}),0);
}
function decorateText(root){
 if(!root||root.dataset.d104Decorated)return;root.dataset.d104Decorated='1';const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement?.closest('.profanity-blur,.mention-token,.chat-link')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
 nodes.forEach(n=>{const s=n.nodeValue;if(!/(@[\wÀ-ÿ.-]+|https?:\/\/[^\s]+)/i.test(s))return;const frag=document.createDocumentFragment();let last=0;const re=/(@[\wÀ-ÿ.-]+|https?:\/\/[^\s]+)/gi;for(const m of s.matchAll(re)){if(m.index>last)frag.append(document.createTextNode(s.slice(last,m.index)));if(m[0][0]==='@'){const sp=document.createElement('span');sp.className='mention-token';sp.textContent=m[0];frag.append(sp)}else{const a=document.createElement('a');a.className='chat-link';a.href=m[0];a.target='_blank';a.rel='noopener noreferrer';a.textContent=m[0];frag.append(a)}last=m.index+m[0].length}if(last<s.length)frag.append(document.createTextNode(s.slice(last)));n.replaceWith(frag)});
}
function bindMessageEnhancements(){
 const list=$('messages-list');if(!list)return;const enhance=item=>{if(item.dataset.d104Bound)return;item.dataset.d104Bound='1';item.addEventListener('contextmenu',e=>showContext(e,item));let timer;item.addEventListener('touchstart',e=>{timer=setTimeout(()=>{item.classList.toggle('mobile-actions');navigator.vibrate?.(18)},520)},{passive:true});['touchend','touchmove','touchcancel'].forEach(x=>item.addEventListener(x,()=>clearTimeout(timer),{passive:true}));decorateText(item.querySelector('.message-content'))};
 [...list.querySelectorAll('.message-item')].forEach(enhance);new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(n=>{if(n.nodeType!==1)return;if(n.matches?.('.message-item'))enhance(n);n.querySelectorAll?.('.message-item').forEach(enhance)}))).observe(list,{childList:true,subtree:true});
}
function setupHeader(){
 const spacer=document.querySelector('.channel-header-spacer');if(!spacer)return;
 const quick=document.createElement('button');quick.id='d104-quick-switcher';quick.className='header-action hide-mobile';quick.title='Changer de salon (⌘K)';quick.textContent='⌘K';quick.onclick=openSwitcher;spacer.after(quick);
 const search=document.createElement('button');search.id='d104-search-trigger';search.className='discord-search-trigger';search.innerHTML='<span>Rechercher</span><kbd>⌘F</kbd>';search.onclick=openSearch;quick.after(search);
 const help=document.createElement('button');help.className='header-action hide-mobile';help.title='Aide';help.textContent='?';help.onclick=()=>$('help-button')?.click();search.after(help);
}
function setupDock(){
 const profile=$('dock-profile-button');if(!profile)return;const controls=document.createElement('span');controls.className='dock-voice-controls';controls.innerHTML='<button type="button" class="dock-action" id="d104-mute" title="Couper le micro (visuel)">🎙</button><button type="button" class="dock-action" id="d104-deafen" title="Mode silencieux (visuel)">🎧</button>';profile.after(controls);
 $('d104-mute').onclick=e=>{e.currentTarget.classList.toggle('is-muted');e.currentTarget.textContent=e.currentTarget.classList.contains('is-muted')?'🔇':'🎙'};
 $('d104-deafen').onclick=e=>{e.currentTarget.classList.toggle('is-deafened');e.currentTarget.textContent=e.currentTarget.classList.contains('is-deafened')?'🔕':'🎧'};
}
function setupCommandSuggestions(){
 const form=$('message-form'),input=$('message-input');if(!form||!input)return;commandBox=document.createElement('div');commandBox.className='command-suggestions';form.parentElement.append(commandBox);
 const render=()=>{const v=input.value.trimStart();if(!v.startsWith('/')){commandBox.classList.remove('open');return}const q=v.toLowerCase();const xs=COMMANDS.filter(([c,d])=>`${c} ${d}`.toLowerCase().includes(q)).slice(0,8);commandBox.innerHTML='';xs.forEach(([c,d],i)=>{const b=document.createElement('button');b.type='button';b.className='command-suggestion'+(i===0?' active':'');b.innerHTML=`<b>${esc(c)}</b><small>${esc(d)}</small>`;b.onclick=()=>{input.value=c;input.focus();commandBox.classList.remove('open')};commandBox.append(b)});commandBox.classList.toggle('open',xs.length>0)};input.addEventListener('input',render);input.addEventListener('keydown',e=>{if(e.key==='Escape')commandBox.classList.remove('open')});document.addEventListener('mousedown',e=>{if(!commandBox.contains(e.target)&&e.target!==input)commandBox.classList.remove('open')});
}
function setTooltips(){document.querySelectorAll('.server-icon').forEach(x=>x.dataset.tooltip=x.title||x.getAttribute('aria-label')||'PiChat');const rail=$('server-list');if(rail)new MutationObserver(()=>document.querySelectorAll('.server-icon').forEach(x=>x.dataset.tooltip=x.title||'Serveur')).observe(rail,{childList:true})}
function init(){
 document.body.classList.add('d104-ready');setupHeader();setupDock();setupCommandSuggestions();bindMessageEnhancements();setTooltips();
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeOverlay(searchOverlay);closeOverlay(switcherOverlay);document.querySelector('.d104-context')?.remove()}if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openSwitcher()}if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='f'&&!['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)){e.preventDefault();openSearch()}});
}
window.PiChatDiscord104={openSearch,openSwitcher,decorateText};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
