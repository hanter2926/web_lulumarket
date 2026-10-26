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

        if (layout.dataset.passwordToggleReady !== 'true') {
            layout.dataset.passwordToggleReady = 'true';
            layout.addEventListener('click', function (event) {
                var target = event.target;
                if (!(target instanceof Element)) {
                    return;
                }

                var toggle = target.closest('.password-toggle');
                if (!toggle || !layout.contains(toggle)) {
                    return;
                }

                var field = toggle.closest('.password-field');
                var input = field && field.querySelector(':scope > input');
                var icon = toggle.querySelector('i');
                if (!input || !icon || input.id !== toggle.getAttribute('aria-controls')) {
                    return;
                }

                event.preventDefault();
                var shouldShow = input.type === 'password';
                input.type = shouldShow ? 'text' : 'password';
                toggle.setAttribute('aria-label', shouldShow ? 'Hide password' : 'Show password');
                toggle.setAttribute('aria-pressed', String(shouldShow));
                icon.classList.toggle('fa-eye', !shouldShow);
                icon.classList.toggle('fa-eye-slash', shouldShow);
            });
        }

        setActivePanel(layout.dataset.activePanel || 'login');
        layout.querySelectorAll('[data-auth-switch]').forEach(function (control) {
            control.addEventListener('click', function () {
                setActivePanel(control.dataset.authSwitch);
            });
        });
    });
})();