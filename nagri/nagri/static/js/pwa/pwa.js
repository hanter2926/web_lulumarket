// Register service worker at root-scoped URL and handle install prompt UI
(function(){
  // Service worker registration
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/service-worker.js', { scope: '/' }).then(function(reg){
      console.log('Service worker registered with scope:', reg.scope);
    }).catch(function(err){
      console.warn('SW registration failed:', err);
    });
  }

  // Install prompt handling
  let deferredPrompt;
  const installBtn = document.getElementById('installBtn');
  if (installBtn) installBtn.style.display = 'none';

  window.addEventListener('beforeinstallprompt', (e) => {
    console.log('beforeinstallprompt fired');
    e.preventDefault();
    deferredPrompt = e;
    if (installBtn) {
      installBtn.style.display = 'inline-block';
      // remove existing listener if any
      installBtn.replaceWith(installBtn.cloneNode(true));
      const newBtn = document.getElementById('installBtn');
      newBtn.addEventListener('click', async () => {
        newBtn.style.display = 'none';
        try {
          deferredPrompt.prompt();
          const choiceResult = await deferredPrompt.userChoice;
          console.log('User choice', choiceResult);
        } catch (err) {
          console.warn('Error showing install prompt', err);
        }
        deferredPrompt = null;
      });
    }
  });

  window.addEventListener('appinstalled', () => {
    if (installBtn) installBtn.style.display = 'none';
  });
})();
