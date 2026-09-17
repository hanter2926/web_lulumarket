(function () {
    function setActivePanel(panelName) {
        var layout = document.querySelector('[data-active-panel]');
        if (!layout) {
            return;
        }

        layout.dataset.activePanel = panelName;
        layout.querySelectorAll('[data-auth-panel]').forEach(function (panel) {
            var isActive = panel.dataset.authPanel === panelName;
            panel.classList.toggle('is-active', isActive);
            panel.setAttribute('aria-hidden', String(!isActive));
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var layout = document.querySelector('[data-active-panel]');
        if (!layout) {
            return;
        }

        setActivePanel(layout.dataset.activePanel || 'login');
        layout.querySelectorAll('[data-auth-switch]').forEach(function (control) {
            control.addEventListener('click', function () {
                setActivePanel(control.dataset.authSwitch);
            });
        });
    });
})();