(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let current = null;
  let timer = null;

  async function api(url, options={}) {
    const response = await fetch(url, {credentials:'same-origin',cache:'no-store',...options});
    let data={};
    try { data=await response.json(); } catch {}
    if(!response.ok) throw new Error(data.detail || `Erreur ${response.status}`);
    return data;
  }
  function flash(text, ok=true){
    if(typeof window.msg==='function') return window.msg(text,ok);
    alert(text);
  }
  function busy(button, on, text='Patiente…'){
    if(!button) return;
    if(on){button.dataset.label=button.textContent;button.disabled=true;button.textContent=text}
    else{button.disabled=false;button.textContent=button.dataset.label||button.textContent}
  }
  function statusLabel(data){
    if(data.running && data.mode==='quick') return 'URL temporaire active';
    if(data.running && data.mode==='permanent') return 'Domaine permanent actif';
    if(data.installed) return 'Prêt à mettre en ligne';
    return 'Installation nécessaire';
  }
  function render(data){
    current=data;
    const state=$('cloud-state');
    state.textContent=statusLabel(data);
    state.className='chip '+(data.running?'good':data.installed?'':'warn');
    $('cloud-platform').textContent=data.platform||'Mac';
    $('cloud-version').textContent=data.installed?(data.version||'Installé'):'Non installé';
    $('cloud-process').textContent=data.running?`Actif · PID ${data.pid}`:'Arrêté';
    $('cloud-mode').textContent=data.mode==='quick'?'Temporaire':data.mode==='permanent'?'Permanent':'—';

    const url=data.public_url||'';
    const box=$('cloud-public-box');
    box.classList.toggle('active',!!url && data.running);
    $('cloud-public-url').textContent=url||'Aucune adresse publique active';
    $('cloud-open').disabled=!url;
    $('cloud-copy').disabled=!url;
    $('cloud-share').disabled=!url;
    $('cloud-stop').disabled=!data.running;
    $('cloud-quick').disabled=!data.installed || data.running;
    $('cloud-permanent-start').disabled=!data.installed || !data.token_configured || data.running;
    $('cloud-install').textContent=data.installed?'Réinstaller cloudflared':'Installer cloudflared';
    $('cloud-token-state').textContent=data.token_configured?'Jeton enregistré sur ce Mac':'Aucun jeton enregistré';
    $('cloud-autostart-state').textContent=data.autostart?'Démarrage automatique activé':'Démarrage automatique désactivé';
    $('cloud-log').textContent=data.log_tail||data.last_error||'Aucun journal pour le moment.';
    $('cloud-error').textContent=data.last_error||'';
    $('cloud-error').hidden=!data.last_error;

    if(url){
      $('cloud-permanent-url').value ||= url.includes('trycloudflare.com')?'':url;
      $('cloud-qr').src=`/api/admin/cloud/qr?url=${encodeURIComponent(url)}&t=${Date.now()}`;
      $('cloud-qr-wrap').hidden=false;
    }else{
      $('cloud-qr-wrap').hidden=true;
      $('cloud-qr').removeAttribute('src');
    }
  }
  async function load(silent=false){
    try{render(await api('/api/admin/cloud'))}
    catch(e){if(!silent) flash(e.message,false)}
  }
  async function action(button, url, options={}, wait='Patiente…'){
    busy(button,true,wait);
    try{const data=await api(url,{method:'POST',...options});render(data);return data}
    catch(e){flash(e.message,false);await load(true);return null}
    finally{busy(button,false)}
  }
  async function copyUrl(){
    const url=current?.public_url;
    if(!url) return;
    try{await navigator.clipboard.writeText(url);flash('Adresse HTTPS copiée.',true)}
    catch{window.prompt('Copie cette adresse :',url)}
  }
  async function shareUrl(){
    const url=current?.public_url;
    if(!url) return;
    if(navigator.share){
      try{await navigator.share({title:'PiChat',text:'Rejoins PiChat',url});return}catch(e){if(e.name==='AbortError')return}
    }
    await copyUrl();
  }
  function openUrl(){
    const url=current?.public_url;
    if(url) window.open(url,'_blank','noopener,noreferrer');
  }
  async function configurePermanent(event){
    event.preventDefault();
    const button=$('cloud-permanent-save');
    const token=$('cloud-token').value.trim();
    const publicUrl=$('cloud-permanent-url').value.trim();
    const autostart=$('cloud-autostart').checked;
    busy(button,true,'Configuration…');
    try{
      const data=await api('/api/admin/cloud/permanent/configure',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({token,public_url:publicUrl,autostart})
      });
      $('cloud-token').value='';render(data);flash('Configuration permanente enregistrée.',true);
    }catch(e){flash(e.message,false)}finally{busy(button,false)}
  }
  async function deleteToken(){
    if(!confirm('Supprimer le jeton Cloudflare enregistré sur ce Mac ?')) return;
    try{render(await api('/api/admin/cloud/token',{method:'DELETE'}));flash('Jeton supprimé.',true)}
    catch(e){flash(e.message,false)}
  }
  function startPolling(){
    clearInterval(timer);
    timer=setInterval(()=>{
      const panel=document.querySelector('[data-panel="deployment"]');
      if(panel?.classList.contains('active')) load(true);
    },4000);
  }
  document.addEventListener('DOMContentLoaded',()=>{
    $('cloud-install')?.addEventListener('click',()=>action($('cloud-install'),'/api/admin/cloud/install',{},'Téléchargement…'));
    $('cloud-quick')?.addEventListener('click',()=>action($('cloud-quick'),'/api/admin/cloud/quick/start',{},'Création de l’URL…'));
    $('cloud-stop')?.addEventListener('click',()=>action($('cloud-stop'),'/api/admin/cloud/stop',{},'Arrêt…'));
    $('cloud-permanent-start')?.addEventListener('click',()=>action($('cloud-permanent-start'),'/api/admin/cloud/permanent/start',{},'Connexion…'));
    $('cloud-permanent-form')?.addEventListener('submit',configurePermanent);
    $('cloud-token-delete')?.addEventListener('click',deleteToken);
    $('cloud-copy')?.addEventListener('click',copyUrl);
    $('cloud-share')?.addEventListener('click',shareUrl);
    $('cloud-open')?.addEventListener('click',openUrl);
    $('cloud-refresh')?.addEventListener('click',()=>load());
    document.querySelector('[data-tab="deployment"]')?.addEventListener('click',()=>load());
    if(location.hash==='#deployment') load();
    startPolling();
  });
})();
