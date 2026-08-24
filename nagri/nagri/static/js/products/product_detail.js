document.addEventListener('DOMContentLoaded', function () {
    const quantityInput = document.getElementById('quantity');
    const minusButton = document.querySelector('.qty-minus');
    const plusButton = document.querySelector('.qty-plus');
    const addToCartButton = document.querySelector('.add-to-cart-btn');
    const buyNowButton = document.querySelector('.buy-now-btn');
    const wishlistButton = document.querySelector('.add-to-wishlist-btn');

    const getMaxQuantity = () => {
        const maxValue = Number(quantityInput?.max || 1);
        return Number.isFinite(maxValue) && maxValue > 0 ? maxValue : 1;
    };

    const updateQuantity = (nextValue) => {
        if (!quantityInput) return;
        const maxValue = getMaxQuantity();
        const safeValue = Math.min(Math.max(nextValue, 1), maxValue);
        quantityInput.value = safeValue;
    };

    if (minusButton && quantityInput) {
        minusButton.addEventListener('click', function () {
            updateQuantity(Number(quantityInput.value || 1) - 1);
        });
    }

    if (plusButton && quantityInput) {
        plusButton.addEventListener('click', function () {
            updateQuantity(Number(quantityInput.value || 1) + 1);
        });
    }

    if (quantityInput) {
        quantityInput.addEventListener('change', function () {
            const rawValue = Number(this.value || 1);
            updateQuantity(rawValue);
        });
    }

    if (addToCartButton) {
        addToCartButton.addEventListener('click', async function (event) {
            event.preventDefault();
            const productId = this.dataset.productId;
            const quantity = Number(quantityInput?.value || 1);
            try {
                this.disabled = true;
                await addToCart(productId, quantity);
                if (typeof updateNavbarCounts === 'function') {
                    await updateNavbarCounts();
                }
            } catch (error) {
                console.error(error);
                alert(error.message || 'Unable to add to cart.');
            } finally {
                this.disabled = false;
            }
        });
    }

    if (buyNowButton) {
        buyNowButton.addEventListener('click', async function (event) {
            event.preventDefault();
            const productId = this.dataset.productId;
            const quantity = Number(quantityInput?.value || 1);

            try {
                this.disabled = true;
                await addToCart(productId, quantity);
                window.location.href = '/orders/checkout/';
            } catch (error) {
                console.error(error);
                alert(error.message || 'Unable to proceed to checkout.');
            } finally {
                this.disabled = false;
            }
        });
    }

    if (wishlistButton) {
        wishlistButton.addEventListener('click', async function (event) {
            event.preventDefault();
            const productId = this.dataset.productId;
            try {
                this.disabled = true;
                const result = await toggleWishlist(productId);
                const isAdded = Boolean(result && result.added);
                const icon = this.querySelector('i');
                if (icon) {
                    icon.classList.toggle('far', !isAdded);
                    icon.classList.toggle('fas', isAdded);
                }
                this.title = isAdded ? 'Remove from Wishlist' : 'Add to Wishlist';
            } catch (error) {
                console.error(error);
                alert(error.message || 'Unable to update wishlist.');
            } finally {
                this.disabled = false;
            }
        });
    }
});
