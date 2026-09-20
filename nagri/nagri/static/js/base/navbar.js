(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        const mobileButton = document.getElementById('mobileMenuBtn');
        const mobileSearchButton = document.getElementById('mobileSearchBtn');
        const categoryLists = Array.from(document.querySelectorAll('.cats-list'));
        let drawer = document.querySelector('.mobile-drawer');
        let searchPanel = document.querySelector('.mobile-search-panel');

        function closeDropdowns(exceptToggle) {
            categoryLists.forEach((list) => {
                list.querySelectorAll(':scope > .dropdown').forEach((dropdown) => {
                    const toggle = dropdown.querySelector(':scope > .dropdown-toggle');
                    const menu = dropdown.querySelector(':scope > .dropdown-menu');
                    if (toggle === exceptToggle) return;
                    dropdown.classList.remove('show');
                    menu?.classList.remove('show');
                    toggle?.setAttribute('aria-expanded', 'false');
                });
            });
        }

        categoryLists.forEach((list) => {
            list.querySelectorAll(':scope > .dropdown > .dropdown-toggle').forEach((toggle) => {
                toggle.setAttribute('role', 'button');
                toggle.setAttribute('aria-expanded', 'false');
                toggle.addEventListener('click', (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    const dropdown = toggle.closest('.dropdown');
                    const menu = dropdown?.querySelector(':scope > .dropdown-menu');
                    const isOpen = dropdown?.classList.contains('show');
                    closeDropdowns(isOpen ? null : toggle);
                    if (!dropdown || !menu || isOpen) return;
                    dropdown.classList.add('show');
                    menu.classList.add('show');
                    toggle.setAttribute('aria-expanded', 'true');
                });
            });
        });

        function closeDrawer() {
            if (!drawer) return;
            drawer.classList.remove('open');
            drawer.setAttribute('aria-hidden', 'true');
        }

        function buildDrawer() {
            if (drawer || !mobileButton) return drawer;
            drawer = document.createElement('aside');
            drawer.className = 'mobile-drawer';
            drawer.setAttribute('aria-hidden', 'true');
            drawer.innerHTML = '<div class="drawer-header"><strong>Shop NAGRI</strong><button class="drawer-close" type="button" aria-label="Close menu">&times;</button></div>';
            const categories = document.querySelector('.cats-list');
            if (categories) {
                const clonedCategories = categories.cloneNode(true);
                clonedCategories.classList.add('mobile-drawer-categories');
                drawer.appendChild(clonedCategories);
            }
            const accountMenu = document.querySelector('.account-menu .dropdown-menu');
            if (accountMenu) {
                const account = document.createElement('div');
                account.className = 'drawer-account';
                account.innerHTML = '<div class="drawer-account-title">Account</div>';
                const clonedAccount = accountMenu.cloneNode(true);
                clonedAccount.classList.remove('dropdown-menu-end');
                clonedAccount.classList.add('drawer-account-menu');
                account.appendChild(clonedAccount);
                drawer.appendChild(account);
            }
            document.body.appendChild(drawer);
            drawer.querySelector('.drawer-close')?.addEventListener('click', closeDrawer);
            return drawer;
        }

        function openDrawer() {
            const activeDrawer = buildDrawer();
            if (!activeDrawer) return;
            activeDrawer.classList.add('open');
            activeDrawer.setAttribute('aria-hidden', 'false');
        }

        mobileButton?.addEventListener('click', (event) => {
            event.stopPropagation();
            if (drawer?.classList.contains('open')) closeDrawer();
            else openDrawer();
        });

        function buildSearchPanel() {
            if (searchPanel || !mobileSearchButton) return searchPanel;
            searchPanel = document.createElement('div');
            searchPanel.className = 'mobile-search-panel mobile-search-container';
            const desktopForm = document.querySelector('.desktop-search');
            searchPanel.innerHTML = desktopForm
                ? desktopForm.outerHTML.replace('desktop-search', 'mobile-search-form')
                : '<form class="mobile-search-form" action="/products/" method="get"><input type="search" name="search" placeholder="Search products" aria-label="Search products"><button type="submit" aria-label="Search"><i class="fas fa-search"></i></button></form>';
            document.querySelector('.nagri-topnav')?.after(searchPanel);
            return searchPanel;
        }

        function closeSearch() { searchPanel?.classList.remove('open'); }
        mobileSearchButton?.addEventListener('click', (event) => {
            event.stopPropagation();
            const panel = buildSearchPanel();
            panel?.classList.toggle('open');
            panel?.querySelector('input')?.focus();
        });

        document.addEventListener('click', (event) => {
            if (!event.target.closest('.cats-list')) closeDropdowns();
            if (drawer?.classList.contains('open') && !event.target.closest('.mobile-drawer, #mobileMenuBtn')) closeDrawer();
            if (searchPanel?.classList.contains('open') && !event.target.closest('.mobile-search-panel, #mobileSearchBtn')) closeSearch();
        });

        document.addEventListener('keydown', (event) => {
            if (event.key !== 'Escape') return;
            closeDropdowns();
            closeDrawer();
            closeSearch();
        });
    });
}());