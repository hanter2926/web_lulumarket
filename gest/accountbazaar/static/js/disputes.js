document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('[data-dispute-form]');
  if (form) form.addEventListener('submit', () => form.querySelector('button[type="submit"]').disabled = true);
});
