let CURRENT_USER = null;

document.addEventListener("DOMContentLoaded", () => {
  checkServerStatus();
  checkAuthentication();
});

async function checkAuthentication(){
  try{
    const response=await fetch('/api/me',{credentials:'same-origin',cache:'no-store'});
    if(!response.ok){location.href='/login';return;}
    CURRENT_USER=await response.json();
    window.CURRENT_USER=CURRENT_USER;
    displayUserInfo(CURRENT_USER);
  }catch(e){console.error('Session PiChat',e);}
}

function initials(name){return (name||'?').slice(0,2).toUpperCase()}

function displayUserInfo(user){
  const box=document.getElementById('user-info');
  const name=document.getElementById('username-display');
  const avatar=document.getElementById('me-avatar');
  const status=document.getElementById('me-status');
  const admin=document.getElementById('admin-link');
  const moderation=document.getElementById('moderation-link');
  const section=document.getElementById('chat-section');
  name.textContent=user.username;
  avatar.textContent=initials(user.username);
  if(user.profile_color) avatar.style.background=user.profile_color;
  status.textContent=user.status_message || (user.role_label ? user.role_label : 'En ligne');
  box.style.display='flex'; section.style.display='grid';
  document.getElementById('mobile-bottom-nav').style.display='grid';
  if(user.is_admin) admin.style.display='grid';
  if(user.is_admin||user.is_moderator) moderation.style.display='grid';
  document.getElementById('logout-button').addEventListener('click',handleLogout);
  initChat();
  loadAIStatus();
  window.dispatchEvent(new CustomEvent('pichat:user-ready',{detail:user}));
}

async function handleLogout(){
  if(CURRENT_USER?.support_mode){
    try{await fetch('/api/support/end',{method:'POST',credentials:'same-origin'});}catch{}
    location.href='/admin#users';return;
  }
  try{await fetch('/api/logout',{method:'POST',credentials:'same-origin'});}catch{}
  location.href='/login';
}

async function checkServerStatus(){
  const box=document.getElementById('server-status');
  try{
    const r=await fetch('/api/health',{cache:'no-store'}); if(!r.ok) throw new Error(r.status);
    const d=await r.json(); box.textContent=`${d.app} v${d.version} opérationnel`;box.className='server-status-hidden ok';
  }catch(e){box.textContent='Serveur indisponible';box.className='server-status-hidden error';}
}

async function loadAIStatus(){
  try{
    const r=await fetch('/api/ai/status',{cache:'no-store'});if(!r.ok)return;
    const s=await r.json();const input=document.getElementById('message-input');
    if(input&&s.enabled)input.placeholder=`Message…  @${s.trigger_name} pour appeler l’IA`;
  }catch{}
}
