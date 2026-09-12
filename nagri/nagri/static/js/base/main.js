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

// Navigate to checkout page
function checkout() {
    window.location.href = '/orders/checkout/';
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

    // Detect HTML/login redirect returned by the server for unauthenticated requests
    if (payload && payload.detail && typeof payload.detail === 'string' && payload.detail.includes('<form')) {
        // Redirect to login with next back to current page
        const loginUrl = '/accounts/auth/';
        window.location.href = loginUrl + '?next=' + encodeURIComponent(window.location.pathname + window.location.search);
        return;
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

    // Handle login redirect returning HTML
    if (payload && payload.detail && typeof payload.detail === 'string' && payload.detail.includes('<form')) {
        const loginUrl = '/accounts/auth/';
        window.location.href = loginUrl + '?next=' + encodeURIComponent(window.location.pathname + window.location.search);
        return;
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

function formatCountdownValue(value) {
    return String(value).padStart(2, '0');
}

function initializeFlashSaleCountdowns() {
    document.querySelectorAll('.flash-sale-section[data-flash-sale-end-time]').forEach((section) => {
        const timerNode = section.querySelector('[data-flash-sale-timer]');
        const statusNode = section.querySelector('[data-flash-sale-status-message]');
        const targetTime = new Date(section.dataset.flashSaleEndTime);
        const endedText = section.dataset.flashSaleEndedText || 'Flash Sale Ended';

        if (!timerNode || Number.isNaN(targetTime.getTime())) {
            if (timerNode) {
                timerNode.textContent = endedText;
            }
            if (statusNode) {
                statusNode.textContent = endedText;
            }
            return;
        }

        const dayNode = timerNode.querySelector('[data-countdown-days]');
        const hourNode = timerNode.querySelector('[data-countdown-hours]');
        const minuteNode = timerNode.querySelector('[data-countdown-minutes]');
        const secondNode = timerNode.querySelector('[data-countdown-seconds]');

        const endSale = () => {
            section.classList.add('flash-sale-ended');
            timerNode.textContent = endedText;
            if (statusNode) {
                statusNode.textContent = endedText;
            }

            section.querySelectorAll('.add-to-cart').forEach((button) => {
                button.disabled = true;
                button.classList.add('is-disabled');
            });
        };

        const renderCountdown = () => {
            const remainingMs = targetTime.getTime() - Date.now();

            if (remainingMs <= 0) {
                endSale();
                clearInterval(intervalId);
                return;
            }

            const totalSeconds = Math.floor(remainingMs / 1000);
            const days = Math.floor(totalSeconds / 86400);
            const hours = Math.floor((totalSeconds % 86400) / 3600);
            const minutes = Math.floor((totalSeconds % 3600) / 60);
            const seconds = totalSeconds % 60;

            if (dayNode) dayNode.textContent = formatCountdownValue(days);
            if (hourNode) hourNode.textContent = formatCountdownValue(hours);
            if (minuteNode) minuteNode.textContent = formatCountdownValue(minutes);
            if (secondNode) secondNode.textContent = formatCountdownValue(seconds);
        };

        const intervalId = window.setInterval(renderCountdown, 1000);
        renderCountdown();
    });
}

function initializeMysteryRewardWidget() {
    const widget = document.querySelector('[data-mystery-reward-widget]');
    if (!widget) return;

    const claimUrl = widget.dataset.claimUrl;
    const loginUrl = widget.dataset.loginUrl || '/accounts/auth/';
    const trigger = widget.querySelector('[data-mystery-reward-open]');
    const result = widget.querySelector('[data-mystery-reward-result]');
    const titleNode = result ? result.querySelector('[data-mystery-reward-result-title]') : null;
    const messageNode = result ? result.querySelector('[data-mystery-reward-result-message]') : null;
    const detailsNode = result ? result.querySelector('[data-mystery-reward-result-details]') : null;
    const box = result ? result.querySelector('[data-mystery-reward-box]') : null;
    const existingClaim = widget.querySelector('.mystery-reward-status-panel');
    const isAuthenticated = !trigger?.dataset.loginRequired;

    if (!trigger || !claimUrl) return;

    const renderClaim = (claim, fallbackMessage = 'Your reward is ready') => {
        if (!result || !titleNode || !messageNode || !detailsNode) return;
        result.hidden = false;
        titleNode.textContent = fallbackMessage;
        messageNode.textContent = claim?.reward_label || claim?.reward_name || 'Reward unlocked';
        detailsNode.innerHTML = [
            `<span class="reward-detail-pill">Reward: ${claim?.reward_label || claim?.reward_name || 'Mystery Reward'}</span>`,
            `<span class="reward-detail-pill reward-detail-code">Code: ${claim?.reward_code || '—'}</span>`,
            `<span class="reward-detail-pill">Expires: ${claim?.expires_at ? new Date(claim.expires_at).toLocaleDateString() : 'Today'}</span>`,
        ].join('');
    };

    const showStoredClaim = () => {
        if (!existingClaim || !titleNode || !messageNode || !detailsNode) return;
        result.hidden = false;
        titleNode.textContent = 'Your current reward';
        messageNode.textContent = existingClaim.innerText.trim();
        detailsNode.innerHTML = '';
    };

    trigger.addEventListener('click', async () => {
        if (!isAuthenticated) {
            window.location.href = loginUrl + '?next=' + encodeURIComponent(window.location.pathname + window.location.search);
            return;
        }

        if (widget.classList.contains('has-claim') && existingClaim) {
            showStoredClaim();
            return;
        }

        try {
            trigger.disabled = true;
            trigger.classList.add('is-loading');
            trigger.textContent = 'Opening...';
            if (result) result.hidden = false;
            if (titleNode) titleNode.textContent = 'Opening your mystery box...';
            if (messageNode) messageNode.textContent = 'Please wait while we reveal your reward.';
            if (detailsNode) detailsNode.innerHTML = '';
            if (box) box.classList.add('is-opening');

            const response = await fetchJson(claimUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });

            if (response.success && response.claim) {
                renderClaim(response.claim, response.message || 'Reward Claimed');
                widget.classList.add('has-claim');
                trigger.textContent = 'View Reward';
                if (existingClaim) {
                    existingClaim.innerHTML = `
                        <div class="status-pill status-pill-active">${response.claim.state || 'Active'}</div>
                        <strong>${response.claim.reward_label || response.claim.reward_name || 'Mystery Reward'}</strong>
                        <span>Code: ${response.claim.reward_code || '—'}</span>
                        <span>Claimed: ${response.claim.claimed_date || 'Today'}</span>
                    `;
                }
                return;
            }

            if (titleNode) titleNode.textContent = 'Reward unavailable';
            if (messageNode) messageNode.textContent = response.message || 'Unable to claim reward.';
        } catch (error) {
            if (error.message && error.message.toLowerCase().includes('already claimed')) {
                if (titleNode) titleNode.textContent = 'Reward already claimed';
                if (messageNode) messageNode.textContent = error.message;
                widget.classList.add('has-claim');
                trigger.textContent = 'View Reward';
            } else {
                if (titleNode) titleNode.textContent = 'Reward unavailable';
                if (messageNode) messageNode.textContent = error.message || 'Please try again later.';
            }
        } finally {
            trigger.disabled = false;
            trigger.classList.remove('is-loading');
            if (box) {
                window.setTimeout(() => box.classList.remove('is-opening'), 900);
            }
            if (!widget.classList.contains('has-claim') && trigger.textContent === 'Opening...') {
                trigger.textContent = 'Open Mystery Box';
            }
        }
    });
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
    initializeFlashSaleCountdowns();
    initializeMysteryRewardWidget();
    // Make any product-card with data-url clickable across the site
    document.querySelectorAll('.product-card, .wishlist-card').forEach(function (card) {
        const url = card.dataset.url;
        if (!url) return;
        if (card.dataset.linkBound === 'true') return;
        card.dataset.linkBound = 'true';
        card.addEventListener('click', function (e) {
            const actionable = e.target.closest('a, button, input, select, label');
            if (actionable) return;
            window.location.href = url;
        });
        card.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                window.location.href = url;
            }
        });
    });
});

// WhatsApp widget behavior
(function () {
    const popup = document.getElementById('whatsapp-popup');
    const floatingBtn = document.getElementById('whatsapp-floating-btn');
    const closeBtn = document.getElementById('whatsapp-popup-close');
    const popupChat = document.getElementById('whatsapp-popup-chat');

    if (!popup || !floatingBtn) return;

    // Track whether popup was shown/closed during this page session (in-memory only)
    let popupShownThisSession = false;
    let popupTimeoutId = null;

    function showPopupOnce() {
        if (popupShownThisSession) return;
        popupShownThisSession = true;
        popup.setAttribute('aria-hidden', 'false');

        // Auto hide after 10 seconds
        popupTimeoutId = setTimeout(() => {
            hidePopup();
        }, 10000);
    }

    function hidePopup() {
        if (popupTimeoutId) {
            clearTimeout(popupTimeoutId);
            popupTimeoutId = null;
        }
        popup.setAttribute('aria-hidden', 'true');
    }

    // Show immediately on page load (only once per page session)
    document.addEventListener('DOMContentLoaded', function () {
        // Slight microtask delay to ensure layout is ready
        setTimeout(showPopupOnce, 10);
    });

    // Close button manually hides popup for the rest of session
    closeBtn && closeBtn.addEventListener('click', function (e) {
        e.preventDefault();
        hidePopup();
        popupShownThisSession = true;
    });

    // Clicking chat in popup opens wa link immediately (anchor handles it)
    // Floating button should open wa link immediately; keep it always visible
    floatingBtn.addEventListener('click', function (e) {
        // Let anchor behave normally and also ensure popup is hidden
        hidePopup();
    });
})();
