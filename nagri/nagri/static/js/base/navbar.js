document.addEventListener('DOMContentLoaded', function () {
    if (typeof updateNavbarCounts === 'function') {
        updateNavbarCounts();
    }
});

// Mobile drawer toggle
document.addEventListener('DOMContentLoaded', function(){
    var mobileBtn = document.getElementById('mobileMenuBtn');
    if (!mobileBtn) return;
    var drawer = document.querySelector('.mobile-drawer');
    if (!drawer) {
        drawer = document.createElement('div');
        drawer.className = 'mobile-drawer';
        drawer.innerHTML = '<div style="padding:16px"><button class="btn btn-sm btn-outline-secondary" id="closeDrawer">Close</button></div>' + document.querySelector('.cats-list')?.outerHTML || '';
        document.body.appendChild(drawer);
    }

    mobileBtn.addEventListener('click', function(){
        drawer.classList.toggle('open');
    });

    document.addEventListener('click', function(e){
        if (!drawer.classList.contains('open')) return;
        if (e.target.closest('.mobile-drawer') || e.target.closest('#mobileMenuBtn')) return;
        drawer.classList.remove('open');
    });
});
