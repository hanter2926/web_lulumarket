document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-confirm-join]').forEach((form) => form.addEventListener('submit', (event) => {
    if (!window.confirm('Join this tournament?')) event.preventDefault();
  }));
});
