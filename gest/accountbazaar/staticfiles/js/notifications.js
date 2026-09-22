document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-notification-read]').forEach((form) => form.addEventListener('submit', () => form.closest('.notification-item')?.classList.remove('unread')));
});
