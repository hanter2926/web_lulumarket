document.addEventListener('DOMContentLoaded', function () {
    const dialog = document.getElementById('cancellation-dialog');
    const form = document.getElementById('cancellation-form');
    if (!dialog || !form) return;

    let orderId = null;
    const reasonStep = form.querySelector('[data-cancellation-step="reason"]');
    const confirmStep = form.querySelector('[data-cancellation-step="confirm"]');
    const comment = form.querySelector('[name="comment"]');
    const confirmButton = form.querySelector('[data-cancellation-confirm]');
    const guidance = form.querySelectorAll('[data-guidance]');

    function showError(message) {
        form.querySelectorAll('[data-cancellation-error]').forEach(function (node) {
            node.textContent = message || '';
        });
    }

    function closeDialog() {
        if (dialog.open) dialog.close();
        reasonStep.hidden = false;
        confirmStep.hidden = true;
        showError('');
        form.reset();
        orderId = null;
    }

    function updateGuidance() {
        const selected = form.querySelector('input[name="reason"]:checked');
        guidance.forEach(function (node) {
            node.hidden = !selected || node.dataset.guidance !== selected.value;
        });
    }

    form.addEventListener('change', function (event) {
        if (event.target.name === 'reason') updateGuidance();
    });

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        const selected = form.querySelector('input[name="reason"]:checked');
        if (!selected) {
            showError('Please select a cancellation reason.');
            return;
        }
        showError('');
        reasonStep.hidden = true;
        confirmStep.hidden = false;
    });

    form.querySelectorAll('[data-cancel-dialog]').forEach(function (button) {
        button.addEventListener('click', closeDialog);
    });
    form.querySelector('[data-cancellation-back]').addEventListener('click', function () {
        confirmStep.hidden = true;
        reasonStep.hidden = false;
        showError('');
    });

    document.querySelectorAll('.cancel-order-trigger').forEach(function (button) {
        button.addEventListener('click', function () {
            orderId = button.dataset.orderId;
            dialog.showModal();
            updateGuidance();
        });
    });

    dialog.addEventListener('click', function (event) {
        if (event.target === dialog) closeDialog();
    });

    confirmButton.addEventListener('click', async function () {
        if (!orderId) return;
        const selected = form.querySelector('input[name="reason"]:checked');
        confirmButton.disabled = true;
        confirmButton.textContent = 'Cancelling...';
        showError('');
        try {
            const csrfCookie = document.cookie.split('; ').find(function (row) { return row.startsWith('csrftoken='); });
            const response = await fetch('/orders/orders/' + orderId + '/cancel/', {
                method: 'PATCH',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-CSRFToken': csrfCookie ? decodeURIComponent(csrfCookie.split('=')[1]) : ''
                },
                body: JSON.stringify({ reason: selected.value, comment: comment.value })
            });
            const data = await response.json();
            if (!response.ok) {
                showError(data.reason || data.comment || data.detail || 'Unable to cancel this order.');
                return;
            }
            window.location.reload();
        } catch (error) {
            showError('Unable to cancel this order right now. Please try again.');
        } finally {
            confirmButton.disabled = false;
            confirmButton.textContent = 'Cancel Order';
        }
    });
});
