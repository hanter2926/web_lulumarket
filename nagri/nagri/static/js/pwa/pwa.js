// Register service worker at root-scoped URL and handle install prompt UI
(function(){
  // Service worker registration
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/service-worker.js').then(function(reg){
      // registration successful
    }).catch(function(err){
      console.warn('SW registration failed:', err);
    });
  }

  // Install prompt handling
  let deferredPrompt;
  const installBtn = document.getElementById('installBtn');
  if (installBtn) installBtn.style.display = 'none';

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    if (installBtn) {
      installBtn.style.display = 'inline-block';
      installBtn.addEventListener('click', async () => {
        installBtn.style.display = 'none';
        deferredPrompt.prompt();
        const choiceResult = await deferredPrompt.userChoice;
        deferredPrompt = null;
      });
    }
  });

  window.addEventListener('appinstalled', () => {
    if (installBtn) installBtn.style.display = 'none';
  });
})();
