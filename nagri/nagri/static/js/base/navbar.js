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
        const categories = document.querySelector('.cats-list');
        const drawerHeader = document.createElement('div');
        drawerHeader.className = 'drawer-header';
        drawerHeader.innerHTML = '<button class="btn btn-sm btn-outline-secondary" id="closeDrawer" type="button">Close</button>';
        drawer.appendChild(drawerHeader);
        if (categories) {
            const drawerCategories = categories.cloneNode(true);
            drawerCategories.classList.add('mobile-drawer-categories');
            drawer.appendChild(drawerCategories);
        }
        document.body.appendChild(drawer);
    }

    const closeDrawer = drawer.querySelector('#closeDrawer');
    if (closeDrawer) {
        closeDrawer.addEventListener('click', function () {
            drawer.classList.remove('open');
        });
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

// Ensure original and cloned mobile category lists share the same click behavior.
document.addEventListener('DOMContentLoaded', function () {
    const categoryLists = Array.from(document.querySelectorAll('.cats-list'));
    if (!categoryLists.length) return;

    function closeAllDropdowns(exceptEl) {
        categoryLists.flatMap(list => Array.from(list.querySelectorAll('.dropdown-toggle'))).forEach(t => {
            const parent = t.closest('.dropdown');
            const menu = parent && parent.querySelector(':scope > .dropdown-menu');
            if (!parent || !menu) return;
            if (t === exceptEl) return;
            parent.classList.remove('show');
            menu.classList.remove('show');
            t.setAttribute('aria-expanded', 'false');
        });
    }

    categoryLists.forEach(function (catsNav) {
        catsNav.querySelectorAll('.dropdown-toggle').forEach(function (t) {
        // Ensure aria attributes exist
        if (!t.hasAttribute('role')) t.setAttribute('role', 'button');
        if (!t.hasAttribute('aria-expanded')) t.setAttribute('aria-expanded', 'false');

        t.addEventListener('click', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            const parent = t.closest('.dropdown');
            if (!parent) return;
            const menu = parent.querySelector(':scope > .dropdown-menu');
            if (!menu) return;

            const isOpen = parent.classList.contains('show') || menu.classList.contains('show');
            if (isOpen) {
                // close
                parent.classList.remove('show');
                menu.classList.remove('show');
                t.setAttribute('aria-expanded', 'false');
            } else {
                // open this, close others
                closeAllDropdowns(t);
                parent.classList.add('show');
                menu.classList.add('show');
                t.setAttribute('aria-expanded', 'true');
            }
        });
        });
    });

    // Close when clicking outside
    document.addEventListener('click', function (e) {
        if (!e.target.closest('.cats-list')) {
            closeAllDropdowns();
        }
    }, true);

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeAllDropdowns();
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
