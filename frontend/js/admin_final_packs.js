(()=>{
  'use strict';
  const $=id=>document.getElementById(id);
  async function api(url,options={}){const r=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||`Erreur ${r.status}`);return d}
  function note(text,ok=false){const id=ok?'success-message':'error-message';const box=$(id);if(box){box.textContent=text;box.classList.add('show');setTimeout(()=>box.classList.remove('show'),3500)}else alert(text)}
  function fmtDate(value){if(!value)return 'Jamais';const d=new Date(value.replace(' ','T')+'Z');return Number.isNaN(d.getTime())?value:d.toLocaleString()}
  function setValue(id,value){const el=$(id);if(!el)return;if(el.type==='checkbox')el.checked=!!value;else el.value=value??''}
  async function load(){
    const root=$('final-pack-admin-status');if(root)root.innerHTML='<p class="muted">Chargement…</p>';
    try{
      const data=await api('/api/admin/final-packs');const s=data.settings,stats=data.stats;
      setValue('pack-scheduled-enabled',s.scheduled_messages_enabled);setValue('pack-social-enabled',s.social_enabled);setValue('pack-sessions-enabled',s.session_manager_enabled);setValue('pack-backup-enabled',s.auto_backup_enabled);
      setValue('pack-scheduled-days',s.scheduled_max_days);setValue('pack-edit-window',s.edit_window_minutes);setValue('pack-delete-window',s.delete_window_minutes);setValue('pack-backup-hours',s.backup_interval_hours);setValue('pack-backup-retention',s.backup_retention);
      if(root)root.innerHTML=`<article><span>Messages programmés</span><strong>${stats.scheduled.pending}</strong><small>${stats.scheduled.failed} échec(s)</small></article><article><span>Relations d’amitié</span><strong>${stats.social.friends}</strong><small>${stats.social.pending} demande(s)</small></article><article><span>Sessions actives</span><strong>${stats.sessions}</strong><small>tous les comptes</small></article><article><span>Backups automatiques</span><strong>${stats.backups.count}</strong><small>${stats.backups.last?'Dernier : '+fmtDate(stats.backups.last.created_at):'Aucun'}</small></article>`;
    }catch(error){if(root)root.innerHTML=`<p class="error">${error.message}</p>`}
  }
  async function save(event){event.preventDefault();const payload={scheduled_messages_enabled:$('pack-scheduled-enabled').checked,social_enabled:$('pack-social-enabled').checked,session_manager_enabled:$('pack-sessions-enabled').checked,auto_backup_enabled:$('pack-backup-enabled').checked,scheduled_max_days:Number($('pack-scheduled-days').value),edit_window_minutes:Number($('pack-edit-window').value),delete_window_minutes:Number($('pack-delete-window').value),backup_interval_hours:Number($('pack-backup-hours').value),backup_retention:Number($('pack-backup-retention').value)};try{await api('/api/admin/final-packs',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});note('Packs finaux enregistrés.',true);await load()}catch(error){note(error.message)}}
  async function backupNow(){const button=$('pack-backup-now');button.disabled=true;button.textContent='Sauvegarde…';try{const data=await api('/api/admin/final-packs/backup-now',{method:'POST'});note('Backup créé : '+(data.backup?.name||'OK'),true);await load()}catch(error){note(error.message)}finally{button.disabled=false;button.textContent='Créer un backup maintenant'}}
  function bind(){
    $('final-packs-admin-form')?.addEventListener('submit',save);$('pack-backup-now')?.addEventListener('click',backupNow);$('pack-final-refresh')?.addEventListener('click',load);
    document.querySelector('[data-tab="final-packs"]')?.addEventListener('click',load);load();
  }
  document.addEventListener('DOMContentLoaded',bind);
})();
