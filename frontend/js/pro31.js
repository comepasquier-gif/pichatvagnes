(()=>{
  const $=id=>document.getElementById(id);
  const actions=[
    {label:'Chat',icon:'💬',run:()=>location.href='/'},
    {label:'Messages privés',icon:'✉️',run:()=>document.getElementById('open-direct-messages')?.click()},
    {label:'PiTutor+',icon:'📚',run:()=>document.getElementById('open-tutor')?.click()},
    {label:'Arcade & mini-jeux',icon:'🕹️',run:()=>document.getElementById('open-games')?.click()},
    {label:'PiGame Studio',icon:'🧪',run:()=>document.getElementById('open-game-studio')?.click()},
    {label:'Importer un jeu',icon:'📦',run:()=>{document.getElementById('open-game-studio')?.click();setTimeout(()=>{document.querySelector('[data-studio-tab="create"]')?.click();document.getElementById('studio-drop-zone')?.scrollIntoView({behavior:'smooth',block:'center'})},120)}},
    {label:'Profil gaming',icon:'🏅',run:()=>document.getElementById('open-gaming-profile')?.click()},
    {label:'PyCoins',icon:'🪙',run:()=>document.getElementById('open-economy')?.click()},
    {label:'Mon profil',icon:'👤',run:()=>document.getElementById('open-profile')?.click()},
    {label:'Personnalisation',icon:'🎨',run:()=>document.getElementById('open-personalization')?.click()},
    {label:'Établissements',icon:'🏫',run:()=>location.href='/spaces'},
    {label:'Railway Online',icon:'🌍',admin:true,run:()=>location.href='/admin#railway'},
    {label:'Administration',icon:'⚙️',admin:true,run:()=>location.href='/admin'},
  ];
  let modal,input,list;
  function available(){return actions.filter(a=>!a.admin||document.getElementById('admin-link')?.style.display!=='none')}
  function build(){if(modal)return;modal=document.createElement('div');modal.className='pro31-palette-backdrop';modal.id='pro31-palette';modal.innerHTML=`<section class="pro31-palette"><header><span>⌘K</span><input id="pro31-palette-input" placeholder="Ouvrir une fonction…" autocomplete="off"><button type="button">×</button></header><div id="pro31-palette-list"></div><footer>↑↓ naviguer · Entrée ouvrir · Échap fermer</footer></section>`;document.body.appendChild(modal);input=$('pro31-palette-input');list=$('pro31-palette-list');modal.addEventListener('click',e=>{if(e.target===modal)close()});modal.querySelector('button').addEventListener('click',close);input.addEventListener('input',render);input.addEventListener('keydown',key);render()}
  function render(){const q=(input?.value||'').trim().toLowerCase();const items=available().filter(a=>a.label.toLowerCase().includes(q));list.innerHTML=items.map((a,i)=>`<button type="button" data-i="${i}" class="${i===0?'active':''}"><span>${a.icon}</span><strong>${a.label}</strong><kbd>↵</kbd></button>`).join('')||'<p class="pro31-empty">Aucun raccourci.</p>';list.querySelectorAll('button').forEach((b,i)=>b.addEventListener('click',()=>{items[i].run();close()}));list._items=items}
  function key(e){const buttons=[...list.querySelectorAll('button')];let i=Math.max(0,buttons.findIndex(b=>b.classList.contains('active')));if(e.key==='ArrowDown'){e.preventDefault();buttons[i]?.classList.remove('active');i=(i+1)%buttons.length;buttons[i]?.classList.add('active');buttons[i]?.scrollIntoView({block:'nearest'})}else if(e.key==='ArrowUp'){e.preventDefault();buttons[i]?.classList.remove('active');i=(i-1+buttons.length)%buttons.length;buttons[i]?.classList.add('active');buttons[i]?.scrollIntoView({block:'nearest'})}else if(e.key==='Enter'){e.preventDefault();buttons[i]?.click()}else if(e.key==='Escape')close()}
  function open(){build();modal.classList.add('show');input.value='';render();setTimeout(()=>input.focus(),20)}
  function close(){modal?.classList.remove('show')}
  document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();open()}else if(e.key==='Escape'&&modal?.classList.contains('show'))close()});
  document.addEventListener('DOMContentLoaded',()=>{const btn=document.createElement('button');btn.type='button';btn.className='pro31-command-button';btn.textContent='⌘K';btn.title='Recherche rapide';btn.addEventListener('click',open);document.body.appendChild(btn)});
})();
