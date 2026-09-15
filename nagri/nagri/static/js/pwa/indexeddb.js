(function (window) {
    'use strict';
    const DB_NAME = 'nagri-offline-v1';
    const DB_VERSION = 1;
    const STORES = ['offline_actions', 'cached_alerts', 'cached_local_updates', 'sync_queue'];

    function openDatabase() {
        return new Promise(function (resolve, reject) {
            if (!('indexedDB' in window)) { reject(new Error('IndexedDB is not available')); return; }
            const request = window.indexedDB.open(DB_NAME, DB_VERSION);
            request.onupgradeneeded = function () {
                const database = request.result;
                STORES.forEach(function (storeName) {
                    if (!database.objectStoreNames.contains(storeName)) database.createObjectStore(storeName, { keyPath: 'id', autoIncrement: true });
                });
            };
            request.onsuccess = function () { resolve(request.result); };
            request.onerror = function () { reject(request.error || new Error('Unable to open IndexedDB')); };
        });
    }

    function transaction(storeName, mode, operation) {
        return openDatabase().then(function (database) {
            return new Promise(function (resolve, reject) {
                const request = operation(database.transaction(storeName, mode).objectStore(storeName));
                request.onsuccess = function () { resolve(request.result); };
                request.onerror = function () { reject(request.error || new Error('IndexedDB request failed')); };
            });
        });
    }

    window.NAGRIIndexedDB = {
        add: function (storeName, value) { return transaction(storeName, 'readwrite', function (store) { return store.add(value); }); },
        get: function (storeName, key) { return transaction(storeName, 'readonly', function (store) { return store.get(key); }); },
        update: function (storeName, value) { return transaction(storeName, 'readwrite', function (store) { return store.put(value); }); },
        delete: function (storeName, key) { return transaction(storeName, 'readwrite', function (store) { return store.delete(key); }); },
        list: function (storeName) { return transaction(storeName, 'readonly', function (store) { return store.getAll(); }); },
        clear: function (storeName) { return transaction(storeName, 'readwrite', function (store) { return store.clear(); }); },
        stores: STORES.slice()
    };
}(window));