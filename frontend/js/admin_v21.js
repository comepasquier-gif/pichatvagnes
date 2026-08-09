(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function api(url, options={}) {
    const response = await fetch(url, {credentials:'same-origin',cache:'no-store',...options});
    let data={}; try { data=await response.json(); } catch {}
    if(!response.ok) throw new Error(data.detail || `Erreur ${response.status}`);
    return data;
  }
  function flash(text, ok=true){
    if(typeof window.msg==='function') return window.msg(text,ok);
    alert(text);
  }
  function render(data){
    const settings=data.settings||{};
    $('deployment-public-url').value=settings.public_url||'';
    $('deployment-hosts').value=settings.allowed_hosts||'localhost,127.0.0.1';
    $('deployment-proxy').checked=!!settings.proxy_headers;
    $('deployment-https').checked=!!settings.https_enabled;
    $('deployment-ready').checked=!!settings.internet_ready;
    const state=$('deployment-state'); state.textContent=data.ready?'Prêt ✓':'À configurer'; state.classList.toggle('good',!!data.ready);
    const checks=$('deployment-checks'); checks.innerHTML='';
    const labels={public_url_https:'URL en HTTPS',allowed_hosts:'Hôtes autorisés',proxy_headers:'Reverse proxy',https_enabled:'HTTPS confirmé',caddyfile_exists:'Caddyfile généré',production_env_exists:'Fichier production .env'};
    Object.entries(data.checks||{}).forEach(([key,value])=>{
      const row=document.createElement('div'); row.className='deployment-check '+(value?'good':'warn');
      row.innerHTML=`<span>${esc(labels[key]||key)}</span><b>${value?'OK':'À faire'}</b>`; checks.append(row);
    });
  }
  async function load(){
    if(!$('deployment-form')) return;
    try { const [data,caddy]=await Promise.all([api('/api/admin/deployment'),fetch('/api/admin/deployment/caddyfile',{credentials:'same-origin',cache:'no-store'}).then(r=>r.text())]); render(data); $('deployment-caddy').textContent=caddy; }
    catch(e){ $('deployment-caddy').textContent=e.message; }
  }
  async function save(event){
    event.preventDefault();
    try{
      await api('/api/admin/deployment',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({public_url:$('deployment-public-url').value.trim(),allowed_hosts:$('deployment-hosts').value.trim(),proxy_headers:$('deployment-proxy').checked,https_enabled:$('deployment-https').checked,internet_ready:$('deployment-ready').checked})});
      flash('Configuration Internet enregistrée.',true); await load();
    }catch(e){flash(e.message,false)}
  }
  async function generate(){
    try{const result=await api('/api/admin/deployment/generate',{method:'POST'});$('deployment-caddy').textContent=result.caddyfile;flash(`Fichiers générés dans ${result.directory}`,true);await load()}
    catch(e){flash(e.message,false)}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    $('deployment-form')?.addEventListener('submit',save);
    $('deployment-generate')?.addEventListener('click',generate);
    $('deployment-refresh')?.addEventListener('click',load);
    document.querySelector('[data-tab="deployment"]')?.addEventListener('click',load);
    if(location.hash==='#deployment') load();
  });
})();
