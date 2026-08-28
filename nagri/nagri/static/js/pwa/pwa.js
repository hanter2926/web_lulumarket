// Register service worker at root-scoped URL and handle install prompt UI
(function(){
  // Service worker registration
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/service-worker.js', { scope: '/' }).then(function(reg){
      console.log('Service worker registered with scope:', reg.scope);
      // Log controller state for diagnostics
      console.log('Service worker controller:', navigator.serviceWorker.controller);
    }).catch(function(err){
      console.warn('SW registration failed:', err);
    });
  }

  // Install prompt handling
  let deferredPrompt = null;
  const installBtn = document.getElementById('installBtn');
  function hideBtn(){ if(!installBtn) return; installBtn.classList.add('d-none'); installBtn.setAttribute('aria-hidden','true'); }
  function showBtn(){ if(!installBtn) return; installBtn.classList.remove('d-none'); installBtn.setAttribute('aria-hidden','false'); }
  if (installBtn) hideBtn();

  // If app is already installed (standalone), hide the button
  try{
    const isStandalone = window.matchMedia && window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
    if (isStandalone) hideBtn();
  }catch(e){}

  window.addEventListener('beforeinstallprompt', (e) => {
    console.log('beforeinstallprompt fired');
    e.preventDefault();
    deferredPrompt = e;
    // show install button
    showBtn();

    // Replace to remove duplicate listeners if any
    installBtn.replaceWith(installBtn.cloneNode(true));
    const newBtn = document.getElementById('installBtn');
    if (newBtn) newBtn.addEventListener('click', async () => {
      hideBtn();
      try {
        await deferredPrompt.prompt();
        const choiceResult = await deferredPrompt.userChoice;
        console.log('User choice', choiceResult);
      } catch (err) {
        console.warn('Error showing install prompt', err);
      }
      deferredPrompt = null;
    });
  });

  // If beforeinstallprompt does not fire within a short time, provide a fallback when clicked
  setTimeout(()=>{
    if (!deferredPrompt && installBtn){
      // Show the button as a fallback for browsers that do not fire beforeinstallprompt
      showBtn();
      installBtn.replaceWith(installBtn.cloneNode(true));
      const fallbackBtn = document.getElementById('installBtn');
      if (fallbackBtn) fallbackBtn.addEventListener('click', ()=>{
        alert('Use your browser menu and select Install App.');
      });
    }
  }, 3000);

  window.addEventListener('appinstalled', () => {
    if (installBtn) hideBtn();
  });
})();
