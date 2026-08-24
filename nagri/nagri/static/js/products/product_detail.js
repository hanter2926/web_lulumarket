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

    // Gallery thumbnail click -> update main image
    const mainImage = document.getElementById('mainProductImage');
    const thumbnailNodes = Array.from(document.querySelectorAll('.product-thumb'));
    const galleryPrev = document.getElementById('galleryPrev');
    const galleryNext = document.getElementById('galleryNext');

    // Build images array in order from thumbnails. If none, fallback to main image src.
    let images = thumbnailNodes.map((t) => t.dataset.src || t.getAttribute('src'));
    if (!images.length && mainImage && mainImage.getAttribute('src')) {
        images = [mainImage.getAttribute('src')];
    }

    let currentIndex = 0;

    const setMainImage = (index) => {
        if (!images.length) return;
        index = (index + images.length) % images.length;
        currentIndex = index;
        const src = images[index];
        if (mainImage && src) {
            mainImage.setAttribute('src', src);
        }
        // Update active thumbnail
        thumbnailNodes.forEach((t, i) => {
            t.classList.toggle('active', i === index);
        });
    };

    // Attach thumbnail click handlers
    thumbnailNodes.forEach((thumb, idx) => {
        thumb.addEventListener('click', function (e) {
            e.preventDefault();
            setMainImage(idx);
        });
    });

    // Prev/Next handlers
    if (galleryPrev) galleryPrev.addEventListener('click', function (e) { e.preventDefault(); setMainImage(currentIndex - 1); });
    if (galleryNext) galleryNext.addEventListener('click', function (e) { e.preventDefault(); setMainImage(currentIndex + 1); });

    // Advance on main image click/tap (respect single-image behavior)
    // Use touch timing guard to avoid double-firing on some mobile browsers
    let lastTouchTime = 0;
    const advanceOnMain = function (e) {
        if (!images || images.length <= 1) return; // nothing to do
        // Prevent clicks originating from other actionable controls
        const actionable = e.target.closest('a, button, input, select, label');
        if (actionable) return;

        // If this is a click and a touch occurred very recently, ignore to avoid double event
        if (e.type === 'click' && (Date.now() - lastTouchTime) < 500) return;

        e.preventDefault();
        setMainImage(currentIndex + 1);
    };

    if (mainImage) {
        mainImage.addEventListener('click', advanceOnMain);
        mainImage.addEventListener('touchend', function (e) { lastTouchTime = Date.now(); advanceOnMain(e); });
        // pointerup is also helpful for stylus/fancy devices
        mainImage.addEventListener('pointerup', advanceOnMain);
    }

    // Initialize
    setMainImage(0);
});
