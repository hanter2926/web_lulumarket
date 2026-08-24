function getCookie(name) {
    const cookie = document.cookie.split('; ').find((row) => row.startsWith(name + '='));
    return cookie ? decodeURIComponent(cookie.split('=')[1]) : null;
}

function getCsrfHeaders(extraHeaders = {}) {
    const csrfToken = getCookie('csrftoken');
    if (!csrfToken) return extraHeaders;
    return {
        ...extraHeaders,
        'X-CSRFToken': csrfToken,
    };
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: getCsrfHeaders(options.headers || {}),
    });

    const contentType = response.headers.get('content-type') || '';
    let payload = {};
    if (contentType.includes('application/json')) {
        payload = await response.json();
    } else {
        const text = await response.text();
        if (text) {
            try {
                payload = JSON.parse(text);
            } catch (error) {
                payload = { detail: text };
            }
        }
    }

    if (!response.ok) {
        throw new Error(payload.detail || payload.error || 'Request failed');
    }

    return payload;
}

async function addToCart(productId, quantity = 1) {
    if (!productId) {
        throw new Error('No product selected.');
    }

    const payload = await fetchJson('/cart/add/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            product_id: Number(productId),
            quantity: Number(quantity) || 1,
        }),
    });

    if (payload && payload.success) {
        await updateNavbarCounts();
        return payload;
    }

    throw new Error(payload.detail || payload.error || 'Unable to add product to cart.');
}

async function toggleWishlist(productId) {
    if (!productId) {
        throw new Error('No product selected.');
    }

    const payload = await fetchJson('/wishlist/toggle/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            product_id: Number(productId),
        }),
    });

    if (payload && payload.success) {
        await updateNavbarCounts();
        return payload;
    }

    throw new Error(payload.detail || payload.error || 'Unable to update wishlist.');
}

async function updateNavbarCounts() {
    try {
        const cartPayload = await fetchJson('/cart/count/', { method: 'GET' });
        const wishlistPayload = await fetchJson('/wishlist/count/', { method: 'GET' });

        document.querySelectorAll('.cart-count').forEach((countNode) => {
            countNode.textContent = cartPayload.count || 0;
            countNode.style.display = Number(cartPayload.count || 0) > 0 ? 'inline-flex' : 'none';
        });

        document.querySelectorAll('.wishlist-count').forEach((countNode) => {
            countNode.textContent = wishlistPayload.count || 0;
            countNode.style.display = Number(wishlistPayload.count || 0) > 0 ? 'inline-flex' : 'none';
        });
    } catch (error) {
        document.querySelectorAll('.cart-count').forEach((countNode) => {
            countNode.textContent = '0';
            countNode.style.display = 'none';
        });
        document.querySelectorAll('.wishlist-count').forEach((countNode) => {
            countNode.textContent = '0';
            countNode.style.display = 'none';
        });
    }
}

function bindGenericActionButtons() {
    document.querySelectorAll('.add-to-cart, .add-to-cart-btn').forEach((button) => {
        if (button.dataset.bound === 'true') return;
        button.dataset.bound = 'true';
        button.addEventListener('click', async function (event) {
            event.preventDefault();
            const productId = this.dataset.productId;
            const quantityInput = this.closest('.product-actions')?.querySelector('.qty-value');
            const quantity = quantityInput ? Number(quantityInput.value || 1) : 1;

            try {
                button.disabled = true;
                button.classList.add('loading');
                await addToCart(productId, quantity);
                const message = document.createElement('div');
                message.className = 'alert alert-success mt-2';
                message.textContent = 'Product added to cart.';
                const parent = this.closest('.product-actions') || this.parentElement;
                if (parent) {
                    const existingAlert = parent.querySelector('.alert-success');
                    if (existingAlert) existingAlert.remove();
                    parent.appendChild(message);
                }
            } catch (error) {
                const message = document.createElement('div');
                message.className = 'alert alert-danger mt-2';
                message.textContent = error.message || 'Unable to add to cart.';
                const parent = this.closest('.product-actions') || this.parentElement;
                if (parent) {
                    const existingAlert = parent.querySelector('.alert-danger');
                    if (existingAlert) existingAlert.remove();
                    parent.appendChild(message);
                }
            } finally {
                button.disabled = false;
                button.classList.remove('loading');
            }
        });
    });

    document.querySelectorAll('.add-to-wishlist, .add-to-wishlist-btn').forEach((button) => {
        if (button.dataset.bound === 'true') return;
        button.dataset.bound = 'true';
        button.addEventListener('click', async function (event) {
            event.preventDefault();
            const productId = this.dataset.productId;
            try {
                button.disabled = true;
                const result = await toggleWishlist(productId);
                const isAdded = Boolean(result && result.added);
                const heartIcon = this.querySelector('i');
                if (heartIcon) {
                    heartIcon.classList.toggle('fas', isAdded);
                    heartIcon.classList.toggle('far', !isAdded);
                }
                if (this.classList.contains('btn-outline-primary')) {
                    this.classList.toggle('btn-primary', isAdded);
                    this.classList.toggle('btn-outline-primary', !isAdded);
                }
            } catch (error) {
                console.error(error);
            } finally {
                button.disabled = false;
            }
        });
    });
}

document.addEventListener('DOMContentLoaded', function () {
    bindGenericActionButtons();
    updateNavbarCounts();
});
