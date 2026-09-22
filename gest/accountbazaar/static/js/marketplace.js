document.addEventListener('DOMContentLoaded', () => {
  const search = document.querySelector('[data-marketplace-search]');
  if (search) search.addEventListener('submit', () => document.body.classList.add('is-loading'));
  document.querySelectorAll('[data-listing-form]').forEach((form) => {
    const category = form.querySelector('[data-category-input]');
    const categoryFields = form.querySelectorAll('.category-specific-field');
    const updateCategoryFields = () => {
      const selected = category?.value || '';
      categoryFields.forEach((field) => {
        const visible = field.dataset.categoryField === selected;
        field.hidden = !visible;
        field.querySelectorAll('input, select, textarea').forEach((input) => {
          input.disabled = !visible;
        });
      });
    };
    category?.addEventListener('change', updateCategoryFields);
    updateCategoryFields();
  });
  document.querySelectorAll('[data-listing-form]').forEach((form) => {
    const input = form.querySelector('[data-image-input]');
    const preview = form.querySelector('[data-image-preview]');
    const previewImage = form.querySelector('[data-image-preview-image]');
    const remove = form.querySelector('[data-image-remove]');
    if (!input || !preview || !previewImage || !remove) return;
    input.addEventListener('change', () => {
      const file = input.files[0];
      if (!file) return;
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
        input.setCustomValidity('Choose a JPG, PNG, or WebP image smaller than 5 MB.');
        preview.hidden = true;
        input.value = '';
        input.reportValidity();
        return;
      }
      input.setCustomValidity('');
      previewImage.src = URL.createObjectURL(file);
      preview.hidden = false;
    });
    remove.addEventListener('click', () => {
      input.value = '';
      input.setCustomValidity('');
      previewImage.removeAttribute('src');
      preview.hidden = true;
    });
  });
});
