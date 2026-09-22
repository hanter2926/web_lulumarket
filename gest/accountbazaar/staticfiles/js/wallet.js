document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-coming-soon]').forEach((button) => button.addEventListener('click', () => {
    button.closest('[data-wallet-action]')?.querySelector('[role="status"]')?.replaceChildren(document.createTextNode('Available after wallet backend activation.'));
  }));
});
