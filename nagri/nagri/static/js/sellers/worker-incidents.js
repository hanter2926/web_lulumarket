document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('worker-incident-form');
    const status = document.getElementById('incident-sync-status');
    if (!form || !window.NAGRISyncManager) return;

    window.addEventListener('nagri-sync-status', function (event) {
        const labels = { pending: 'Offline - saved locally', syncing: 'Syncing...', synced: 'Synced' };
        if (labels[event.detail]) status.textContent = labels[event.detail];
    });

    form.addEventListener('submit', async function (event) {
        event.preventDefault();
        const formData = new FormData(form);
        const payload = {
            incident_type: formData.get('incident_type'),
            severity: formData.get('severity'),
            title: formData.get('title'),
            description: formData.get('description'),
            latitude: formData.get('latitude') || null,
            longitude: formData.get('longitude') || null
        };
        const assignmentMatch = window.location.pathname.match(/assignments\/(\d+)\/report-problem/);
        if (assignmentMatch) payload.delivery_assignment = Number(assignmentMatch[1]);

        try {
            await window.NAGRISyncManager.request({
                endpoint: form.dataset.syncEndpoint,
                method: 'POST',
                payload: payload
            });
            status.textContent = navigator.onLine ? 'Incident reported successfully.' : 'Offline - saved locally';
            if (navigator.onLine) window.setTimeout(function () { window.location.href = '/sellers/delivery/dashboard/'; }, 500);
        } catch (error) {
            status.textContent = error.message || 'Unable to report incident.';
        }
    });
});
