document.addEventListener("DOMContentLoaded", () => {
    const imageInput = document.getElementById("id_image");
    const preview = document.getElementById("product-image-preview");
    const previewImage = document.getElementById("product-image-preview-image");
    if (!imageInput || !preview || !previewImage) return;

    const clearInput = document.querySelector('input[name="image-clear"]');
    const initialImageUrl = previewImage.getAttribute("src") || "";
    let objectUrl = null;

    const releaseObjectUrl = () => {
        if (objectUrl) {
            URL.revokeObjectURL(objectUrl);
            objectUrl = null;
        }
    };

    imageInput.addEventListener("change", () => {
        releaseObjectUrl();
        const [file] = imageInput.files || [];
        if (file) {
            if (clearInput) clearInput.checked = false;
            objectUrl = URL.createObjectURL(file);
            previewImage.src = objectUrl;
            preview.hidden = false;
        } else if (clearInput?.checked) {
            preview.hidden = true;
        } else {
            preview.hidden = !initialImageUrl;
            if (initialImageUrl) previewImage.src = initialImageUrl;
        }
    });

    clearInput?.addEventListener("change", () => {
        if (clearInput.checked && !imageInput.files.length) {
            preview.hidden = true;
        } else if (!clearInput.checked && !imageInput.files.length) {
            preview.hidden = !initialImageUrl;
            if (initialImageUrl) previewImage.src = initialImageUrl;
        }
    });

    window.addEventListener("beforeunload", releaseObjectUrl, { once: true });
});
