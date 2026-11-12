(function () {
    const button = document.getElementById("detect-shop-location");
    const latitudeInput = document.getElementById("id_latitude");
    const longitudeInput = document.getElementById("id_longitude");
    const status = document.getElementById("shop-location-status");

    if (!button || !latitudeInput || !longitudeInput || !status) return;

    button.addEventListener("click", function () {
        if (!navigator.geolocation) {
            status.textContent = "Location detection is unavailable in this browser or page context. Enter coordinates manually.";
            return;
        }

        button.disabled = true;
        status.textContent = "Requesting your location. Approve the browser permission prompt...";

        navigator.geolocation.getCurrentPosition(
            function (position) {
                const latitude = position.coords.latitude;
                const longitude = position.coords.longitude;
                if (
                    !Number.isFinite(latitude)
                    || !Number.isFinite(longitude)
                    || latitude < -90
                    || latitude > 90
                    || longitude < -180
                    || longitude > 180
                ) {
                    status.textContent = "The browser returned invalid coordinates. Please enter the location manually.";
                    button.disabled = false;
                    return;
                }

                latitudeInput.value = latitude.toFixed(6);
                longitudeInput.value = longitude.toFixed(6);
                const accuracy = Number.isFinite(position.coords.accuracy)
                    && position.coords.accuracy >= 0
                    ? `Reported accuracy: about ${Math.round(position.coords.accuracy)} m.`
                    : "Accuracy information was not provided; verify these coordinates manually.";
                status.textContent = `Location detected: ${latitudeInput.value}, ${longitudeInput.value}. ${accuracy} Review or edit the coordinates before saving.`;
                button.disabled = false;
            },
            function (error) {
                if (error.code === error.PERMISSION_DENIED) {
                    status.textContent = "Location permission was denied. Allow location access in your browser settings or enter coordinates manually.";
                } else if (error.code === error.POSITION_UNAVAILABLE) {
                    status.textContent = "Your location is unavailable right now. Try again or enter coordinates manually.";
                } else if (error.code === error.TIMEOUT) {
                    status.textContent = "Location detection timed out. Try again or enter coordinates manually.";
                } else {
                    status.textContent = "Unable to detect your location. Try again or enter coordinates manually.";
                }
                button.disabled = false;
            },
            {
                enableHighAccuracy: true,
                timeout: 15000,
                maximumAge: 0,
            },
        );
    });
})();
