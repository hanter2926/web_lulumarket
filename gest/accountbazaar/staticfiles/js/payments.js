document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('[data-payment-form]');
  if (!form) return;
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    form.querySelector('[role="status"]').textContent = 'Payment provider integration is required before payment can be submitted.';
  });
});
