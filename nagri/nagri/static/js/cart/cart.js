document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.qty-plus').forEach((button) => {
        button.addEventListener('click', function () {
            const row = this.closest('.cart-item');
            const input = row?.querySelector('.qty-value');
            if (!input) return;
            input.value = Number(input.value || 1) + 1;
        });
    });

    document.querySelectorAll('.qty-minus').forEach((button) => {
        button.addEventListener('click', function () {
            const row = this.closest('.cart-item');
            const input = row?.querySelector('.qty-value');
            if (!input) return;
            input.value = Math.max(1, Number(input.value || 1) - 1);
        });
    });

    document.querySelectorAll('.remove-item').forEach((button) => {
        button.addEventListener('click', function () {
            const itemId = this.dataset.itemId;
            if (!itemId) return;
            fetch(`/cart/${itemId}/remove/`, {
                method: 'POST',
                headers: getCsrfHeaders({ 'Content-Type': 'application/json' }),
            }).then(() => window.location.reload());
        });
    });
});
