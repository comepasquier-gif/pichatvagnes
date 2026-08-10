(()=>{
'use strict';
const $=id=>document.getElementById(id);
function fit(el,max=128){if(!el)return;el.style.height='auto';el.style.height=Math.min(max,Math.max(40,el.scrollHeight))+'px'}
function bindComposer(){
  const input=$('message-input'),form=$('message-form');
  if(input&&form&&!input.dataset.fix362){
    input.dataset.fix362='1';
    input.addEventListener('input',()=>fit(input,128));
    input.addEventListener('keydown',e=>{
      if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){
        e.preventDefault();
        if(input.value.trim())form.requestSubmit();
      }
    });
    form.addEventListener('submit',()=>requestAnimationFrame(()=>fit(input,128)));
    fit(input,128);
  }
}
function bindDM(){
  const input=$('dm-input'),form=$('dm-form');
  if(input&&form&&!input.dataset.fix362){
    input.dataset.fix362='1';
    input.addEventListener('input',()=>fit(input,130));
    input.addEventListener('keydown',e=>{
      if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(input.value.trim())form.requestSubmit()}
    });
    form.addEventListener('submit',()=>setTimeout(()=>fit(input,130),0));
    fit(input,130);
  }
}
function init(){bindComposer();bindDM();document.documentElement.dataset.pichatUx='3.6.2'}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
