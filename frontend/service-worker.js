const VERSION = 'pichat-v3-3400';
const SHELL_CACHE = `${VERSION}-shell`;
const RUNTIME_CACHE = `${VERSION}-runtime`;
const APP_SHELL = [
  '/', '/login', '/register', '/spaces', '/offline.html', '/manifest.webmanifest',
  '/css/style.css?v=3200', '/css/neo23.css?v=3200', '/css/v2.css?v=3200', '/css/spaces_v2.css?v=3200',
  '/css/discord.css?v=3200', '/css/ui_settings.css?v=3200', '/css/discord104.css?v=3200',
  '/css/pwa.css?v=3200', '/css/pro31.css?v=3200', '/css/mobile112.css?v=3200', '/css/features113.css?v=3200', '/css/v21.css?v=3200', '/css/gaming_profiles.css?v=3200', '/css/arcade.css?v=3200', '/css/game_studio.css?v=3200', '/css/final_packs.css?v=3200',
  '/js/app.js?v=3200', '/js/spaces_switcher_v2.js?v=3200', '/js/spaces_v2.js?v=3200',
  '/js/pwa.js?v=3200', '/js/websocket.js?v=3200', '/js/gaming_profiles.js?v=3200', '/js/arcade.js?v=3200', '/js/game_studio.js?v=3200', '/js/final_packs.js?v=3200', '/js/community.js?v=3200', '/js/debug.js?v=3200',
  '/js/ui_settings.js?v=3200', '/js/trolls.js?v=3200', '/js/discord104.js?v=3200',
  '/js/mobile112.js?v=3200', '/js/pro31.js?v=3200', '/js/economy113.js?v=3200', '/js/v21.js?v=3200',
  '/assets/icons/pichat-192.png', '/assets/icons/pichat-512.png', '/assets/icons/pichat-maskable-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL_CACHE).then(cache => cache.addAll(APP_SHELL)).catch(() => null));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil((async()=>{
    const keys=await caches.keys();
    await Promise.all(keys.filter(k=>![SHELL_CACHE,RUNTIME_CACHE].includes(k)).map(k=>caches.delete(k)));
    await self.clients.claim();
    const clientsList=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    clientsList.forEach(c=>c.postMessage({type:'PICHAT_UPDATED',version:'3.4.0'}));
  })());
});

async function networkFirst(req, fallback){
  try{
    const fresh=await fetch(req,{cache:'no-store'});
    if(fresh.ok){const cache=await caches.open(RUNTIME_CACHE);cache.put(req,fresh.clone())}
    return fresh;
  }catch(_){return (await caches.match(req))||(fallback?await caches.match(fallback):Response.error())}
}
async function staleWhileRevalidate(req){
  const cached=await caches.match(req);
  const refresh=fetch(req,{cache:'no-store'}).then(async fresh=>{if(fresh.ok){const c=await caches.open(RUNTIME_CACHE);await c.put(req,fresh.clone())}return fresh}).catch(()=>null);
  return cached || await refresh || Response.error();
}
self.addEventListener('fetch', event=>{
  const req=event.request;if(req.method!=='GET')return;
  const url=new URL(req.url);if(url.origin!==location.origin)return;
  if(url.pathname.startsWith('/api/')||url.pathname.startsWith('/ws')||url.pathname.startsWith('/uploads/'))return;
  if(req.mode==='navigate'){event.respondWith(networkFirst(req,'/offline.html'));return}
  if(['style','script','manifest'].includes(req.destination)){event.respondWith(networkFirst(req));return}
  if(req.destination==='image'||req.destination==='font'){event.respondWith(staleWhileRevalidate(req));return}
});
self.addEventListener('notificationclick',event=>{event.notification.close();const target=event.notification.data?.url||'/';event.waitUntil((async()=>{const windows=await clients.matchAll({type:'window',includeUncontrolled:true});for(const client of windows){if('focus'in client){await client.focus();client.postMessage({type:'pichat:notification-click',roomId:event.notification.data?.roomId||null});return}}if(clients.openWindow)await clients.openWindow(target)})())});
self.addEventListener('message',event=>{
  if(event.data?.type==='SKIP_WAITING')self.skipWaiting();
  if(event.data?.type==='CHECK_UPDATE')event.waitUntil(self.registration.update());
  if(event.data?.type==='SHOW_NOTIFICATION'){
    const d=event.data.payload||{};
    event.waitUntil(self.registration.showNotification(d.title||'PiChat',{body:d.body||'Nouveau message',icon:'/assets/icons/pichat-192.png',badge:'/assets/icons/pichat-96.png',tag:d.tag||`pichat-${Date.now()}`,renotify:true,silent:!!d.silent,data:{url:d.url||'/',roomId:d.roomId||null}}));
  }
});
