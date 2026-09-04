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

// Mobile search panel toggle
document.addEventListener('DOMContentLoaded', function(){
    var mobileSearchBtn = document.getElementById('mobileSearchBtn');
    if (!mobileSearchBtn) return;

    // Create panel if missing. Reuse an existing `.mobile-only-search` form on the page
    // to avoid duplicating the search input on mobile pages like home.
    var mobilePanel = document.querySelector('.mobile-search-panel');
    if (!mobilePanel) {
        var existingMobileOnly = document.querySelector('.mobile-only-search');
        mobilePanel = document.createElement('div');
        mobilePanel.className = 'mobile-search-panel mobile-search-container';

        if (existingMobileOnly) {
            // Clone the existing mobile-only form (do not remove original)
            var cloned = existingMobileOnly.cloneNode(true);
            // Ensure cloned form uses expected dialog class
            cloned.classList.add('mobile-search-form');
            mobilePanel.appendChild(cloned);
        } else {
            // Fallback: build a simple mobile search form reusing desktop action if possible
            var desktopForm = document.querySelector('.topnav-center form');
            var action = (desktopForm && desktopForm.action) ? desktopForm.action : (window.location.pathname || '/');
            mobilePanel.innerHTML = '' +
                '<form class="mobile-search-form" action="' + action + '" method="get">' +
                    '<input type="search" name="search" class="mobile-search-input" placeholder="Search for products, brands and categories" aria-label="Search">' +
                    '<button type="submit" class="mobile-search-submit" aria-label="Search"><i class="fas fa-search"></i></button>' +
                    '<button type="button" class="mobile-search-close" aria-label="Close search">&times;</button>' +
                '</form>';
        }

        // Insert after the topnav so it appears below the header
        var topnav = document.querySelector('.nagri-topnav');
        if (topnav && topnav.parentNode) {
            topnav.parentNode.insertBefore(mobilePanel, topnav.nextSibling);
        } else {
            document.body.insertBefore(mobilePanel, document.body.firstChild);
        }
    }

    // Toggle open/close
    function openPanel(){
        mobilePanel.classList.add('open');
        var input = mobilePanel.querySelector('.mobile-search-input');
        if (input) input.focus();
    }
    function closePanel(){
        mobilePanel.classList.remove('open');
    }

    mobileSearchBtn.addEventListener('click', function(e){
        e.stopPropagation();
        if (mobilePanel.classList.contains('open')) { closePanel(); } else { openPanel(); }
    });

    // Close when clicking the close button
    mobilePanel.addEventListener('click', function(e){
        if (e.target.closest('.mobile-search-close')) { closePanel(); }
    });

    // Close when tapping outside
    document.addEventListener('click', function(e){
        if (!mobilePanel.classList.contains('open')) return;
        if (e.target.closest('.mobile-search-panel') || e.target.closest('#mobileSearchBtn')) return;
        closePanel();
    });
});
