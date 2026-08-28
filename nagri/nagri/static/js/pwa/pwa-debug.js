// PWA Installability Debug Panel
(function(){
  // Show only on localhost or when ?pwa_debug=1 is present
  const isLocal = ['localhost','127.0.0.1'].includes(location.hostname);
  const showFlag = new URLSearchParams(location.search).get('pwa_debug') === '1';
  if (!(isLocal || showFlag)) return;

  function el(tag, attrs, text){ const e = document.createElement(tag); if(attrs) Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v)); if(text) e.textContent = text; return e; }

  const panel = el('div',{id:'pwaDebugPanel','aria-hidden':'false'});
  const style = el('style');
  style.textContent = `
    #pwaDebugPanel{position:fixed;right:12px;bottom:12px;width:320px;max-width:calc(100% - 24px);background:rgba(255,255,255,0.98);border:1px solid #ddd;border-radius:8px;padding:12px;box-shadow:0 6px 18px rgba(0,0,0,0.12);font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',Arial;color:#111;z-index:99999;font-size:13px}
    #pwaDebugPanel h4{margin:0 0 8px 0;font-size:14px}
    #pwaDebugPanel ul{list-style:none;margin:0;padding:0}
    #pwaDebugPanel li{display:flex;align-items:center;margin:6px 0}
    #pwaDebugPanel li span.status{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:8px}
    #pwaDebugPanel .small{font-size:12px;color:#666}
    #pwaDebugPanel button.close{position:absolute;right:8px;top:6px;border:0;background:transparent;font-size:16px;cursor:pointer}
  `;
  panel.appendChild(style);
  const closeBtn = el('button',{class:'close',title:'Close'}, '×');
  closeBtn.onclick = ()=>panel.remove();
  panel.appendChild(closeBtn);
  panel.appendChild(el('h4',null,'PWA Installability Debug'));
  const list = el('ul'); panel.appendChild(list);
  panel.appendChild(el('div',{class:'small'}, 'Open console for more details. Use ?pwa_debug=1 to show on prod.'));
  document.body.appendChild(panel);

  function addItem(name, ok, details){
    const li = el('li');
    const status = el('span',{class:'status'});
    status.style.background = ok ? '#28a745' : '#dc3545';
    li.appendChild(status);
    const txt = el('div');
    txt.appendChild(el('div',null,name + (ok ? ' — OK' : ' — Problem')));
    if(details) txt.appendChild(el('div',{class:'small'}, details));
    li.appendChild(txt);
    list.appendChild(li);
  }

  const results = {
    manifestLoaded:false,
    manifest:null,
    swRegistered:false,
    swControlling:false,
    beforeInstallPromptFired:false,
    isSecureContext: (location.protocol === 'https:' || isLocal),
    iconsValid:false,
    installable:false
  };

  // Listen for beforeinstallprompt
  window.addEventListener('beforeinstallprompt', (e)=>{
    console.log('PWA Debug: beforeinstallprompt fired', e);
    results.beforeInstallPromptFired = true;
    updateUI();
  });
  window.addEventListener('appinstalled', ()=>{ console.log('PWA Debug: appinstalled event fired'); });

  // Check service worker registration and control
  async function checkServiceWorker(){
    if(!('serviceWorker' in navigator)){
      results.swRegistered = false; results.swControlling = false; return;
    }
    try{
      const reg = await navigator.serviceWorker.getRegistration('/service-worker.js');
      results.swRegistered = !!reg;
      results.swControlling = !!navigator.serviceWorker.controller;
      console.log('PWA Debug: SW registration', reg, 'controller', navigator.serviceWorker.controller);
    }catch(err){ console.warn('PWA Debug: SW check failed', err); results.swRegistered=false; results.swControlling=false; }
  }

  // Fetch and validate manifest and icons
  async function checkManifest(){
    try{
      const resp = await fetch('/static/manifest.json', {cache:'no-store'});
      if(!resp.ok) throw new Error('HTTP ' + resp.status);
      const mf = await resp.json();
      results.manifestLoaded = true; results.manifest = mf;
      console.log('PWA Debug: manifest', mf);

      // basic required fields
      const required = ['name','short_name','start_url','scope','display','theme_color','background_color'];
      const missing = required.filter(k=>!mf[k]);
      if(missing.length) console.warn('PWA Debug: manifest missing fields', missing);

      // check icons
      if(Array.isArray(mf.icons) && mf.icons.length){
        let ok = true;
        for(const icon of mf.icons){
          try{
            const img = new Image();
            await new Promise((res,rej)=>{
              img.onload = ()=>res(true);
              img.onerror = ()=>res(false);
              img.src = icon.src.startsWith('/') ? icon.src : ('/static/' + icon.src);
            }).then(loaded=>{
              if(!loaded) { ok=false; console.warn('PWA Debug: icon failed to load', icon.src); }
              else{
                // check size if provided
                if(icon.sizes){
                  const [w,h] = icon.sizes.split('x').map(Number);
                  if(img.naturalWidth !== w || img.naturalHeight !== h){
                    console.warn('PWA Debug: icon size mismatch', icon.src, img.naturalWidth, img.naturalHeight, 'expected', icon.sizes);
                    ok=false;
                  }
                }
              }
            });
          }catch(e){ ok=false; console.warn('PWA Debug: error loading icon', icon.src, e); }
        }
        results.iconsValid = ok;
      } else {
        results.iconsValid = false;
        console.warn('PWA Debug: no icons in manifest');
      }
    }catch(err){ console.warn('PWA Debug: manifest fetch failed', err); results.manifestLoaded=false; }
  }

  function computeInstallable(){
    const mf = results.manifest || {};
    const displayOk = mf.display === 'standalone';
    results.installable = results.manifestLoaded && results.iconsValid && results.swRegistered && results.swControlling && results.isSecureContext && displayOk;
    console.log('PWA Debug: computed installable =', results.installable, 'details=', results);
  }

  function updateUI(){
    // Clear list
    list.innerHTML = '';
    addItem('Manifest loaded', results.manifestLoaded, results.manifest ? ('name: ' + results.manifest.name) : '');
    addItem('Service worker registered', results.swRegistered, results.swRegistered ? 'SW available' : 'No SW registration');
    addItem('Service worker controlling page', results.swControlling, results.swControlling ? 'Controller present' : 'Page not controlled by SW');
    addItem('beforeinstallprompt fired', results.beforeInstallPromptFired, results.beforeInstallPromptFired ? 'Event fired' : 'No event yet');
    addItem('Secure context (HTTPS or localhost)', results.isSecureContext, results.isSecureContext ? location.protocol : 'Not secure');
    addItem('Icons valid (192/512)', results.iconsValid, results.iconsValid ? 'Icons OK' : 'Missing or size mismatch');
    addItem('Display: standalone', !!(results.manifest && results.manifest.display==='standalone'), results.manifest ? ('display: ' + results.manifest.display) : '');
    computeInstallable();
    addItem('Computed installable', results.installable, results.installable ? 'Should be installable' : 'Not installable - see above');
  }

  // Run checks
  (async function(){
    await checkServiceWorker();
    await checkManifest();
    // Sometimes SW takes control after reload; delay a bit and re-check
    setTimeout(async ()=>{ await checkServiceWorker(); computeInstallable(); updateUI(); }, 1200);
    updateUI();
  })();

})();
