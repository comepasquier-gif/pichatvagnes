(() => {
  'use strict';
  const TARGET=50, samples=[];
  let timer=null, active=true, wsActiveUntil=0;
  function ensurePill(){
    let pill=document.getElementById('ping-status');if(pill)return pill;
    pill=document.createElement('span');pill.id='ping-status';pill.className='p35-ping-pill';pill.innerHTML='<i class="p35-ping-dot"></i><span>Ping…</span>';
    const ws=document.getElementById('ws-status');if(ws?.parentNode)ws.after(pill);else{const wrap=document.createElement('div');wrap.className='p35-ping-floating';wrap.append(pill);document.body.append(wrap)}return pill;
  }
  function record(ms,source='http'){
    if(String(source).toLowerCase().includes('websocket'))wsActiveUntil=Date.now()+15000;
    ms=Math.max(0,Math.round(Number(ms)||0));if(!ms)return;
    samples.push(ms);if(samples.length>8)samples.shift();const median=[...samples].sort((a,b)=>a-b)[Math.floor(samples.length/2)];const value=Math.round(median);
    const pill=ensurePill();const cls=value<=TARGET?'good':value<=110?'ok':'slow';pill.className='p35-ping-pill '+cls;pill.innerHTML=`<i class="p35-ping-dot"></i><span>${value} ms</span><small class="p35-perf-mode">objectif &lt;${TARGET}</small>`;pill.title=`Latence ${source} · médiane des ${samples.length} dernières mesures`;
    window.dispatchEvent(new CustomEvent('pichat:ping',{detail:{ms:value,raw:ms,target:TARGET,source}}));
  }
  async function httpPing(){
    if(!active||document.hidden||Date.now()<wsActiveUntil)return;const start=performance.now();
    try{const r=await fetch('/api/ping?ts='+Date.now(),{cache:'no-store',credentials:'same-origin'});if(r.ok)record(performance.now()-start,'HTTP')}
    catch(_){const p=ensurePill();p.className='p35-ping-pill slow';p.innerHTML='<i class="p35-ping-dot"></i><span>Hors ligne</span>'}
  }
  function start(){ensurePill();httpPing();clearInterval(timer);timer=setInterval(httpPing,12000)}
  document.addEventListener('visibilitychange',()=>{active=!document.hidden;if(active)httpPing()});
  window.PiChatPerf35={record,httpPing,target:TARGET};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
