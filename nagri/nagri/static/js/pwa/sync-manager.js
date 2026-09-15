(function (window) {
    'use strict';
    const STORE = 'sync_queue';
    const MAX_RETRIES = 5;
    const BASE_DELAY = 2000;
    let flushing = false;

    function createClientId() {
        if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
        return 'nagri-' + Date.now() + '-' + Math.random().toString(16).slice(2);
    }

    function waitForBackoff(retryCount) {
        const delay = Math.min(BASE_DELAY * Math.pow(2, retryCount), 60000);
        return new Promise(function (resolve) { window.setTimeout(resolve, delay); });
    }

    async function registerBackgroundSync() {
        if (!('serviceWorker' in navigator)) return;
        const registration = await navigator.serviceWorker.ready;
        if (registration.sync && registration.sync.register) {
            try { await registration.sync.register('nagri-sync'); } catch (error) {}
        }
    }

    async function queueAction(action) {
        const record = Object.assign({ client_id: createClientId(), action_type: 'request', method: 'POST', payload: null, created_at: new Date().toISOString(), retry_count: 0, status: 'pending' }, action);
        const existing = await window.NAGRIIndexedDB.list(STORE);
        const duplicate = existing.find(function (item) { return item.client_id === record.client_id; });
        if (duplicate) return duplicate;
        record.id = await window.NAGRIIndexedDB.add(STORE, record);
        await registerBackgroundSync();
        window.dispatchEvent(new CustomEvent('nagri-sync-status', { detail: 'pending' }));
        return record;
    }

    async function sendAction(action) {
        const headers = { 'Content-Type': 'application/json', 'X-NAGRI-Idempotency-Key': action.client_id };
        const response = await fetch(action.endpoint, { method: action.method, headers: headers, body: action.payload == null ? undefined : JSON.stringify(action.payload), credentials: 'same-origin' });
        if (!response.ok) throw new Error('Sync failed with HTTP ' + response.status);
        return response;
    }

    async function request(action) {
        if (navigator.onLine) return sendAction(Object.assign({ client_id: createClientId() }, action));
        return queueAction(action);
    }

    async function flush() {
        if (flushing || !navigator.onLine || !window.NAGRIIndexedDB) return;
        flushing = true;
        window.dispatchEvent(new CustomEvent('nagri-sync-status', { detail: 'syncing' }));
        try {
            const actions = await window.NAGRIIndexedDB.list(STORE);
            for (const action of actions.filter(function (item) { return item.status === 'pending' || item.status === 'failed'; })) {
                if (action.retry_count >= MAX_RETRIES) continue;
                action.status = 'syncing';
                await window.NAGRIIndexedDB.update(STORE, action);
                try {
                    await sendAction(action);
                    action.status = 'synced';
                    await window.NAGRIIndexedDB.update(STORE, action);
                } catch (error) {
                    action.retry_count += 1;
                    action.status = 'failed';
                    action.last_error = String(error.message || error);
                    await window.NAGRIIndexedDB.update(STORE, action);
                    await waitForBackoff(action.retry_count);
                }
            }
            window.dispatchEvent(new CustomEvent('nagri-sync-status', { detail: 'synced' }));
        } finally { flushing = false; }
    }

    window.NAGRISyncManager = { request: request, queueAction: queueAction, flush: flush, registerBackgroundSync: registerBackgroundSync };
}(window));