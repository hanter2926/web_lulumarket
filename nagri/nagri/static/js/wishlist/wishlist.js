document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.btn-remove-wishlist').forEach((button) => {
        button.addEventListener('click', async function () {
            const productId = this.dataset.productId;
            if (!productId) return;
            try {
                await toggleWishlist(productId);
                window.location.reload();
            } catch (error) {
                console.error(error);
            }
        });
    });
});
