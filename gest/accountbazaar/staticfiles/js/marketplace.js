document.addEventListener('DOMContentLoaded', () => {
  const search = document.querySelector('[data-marketplace-search]');
  if (search) search.addEventListener('submit', () => document.body.classList.add('is-loading'));
});
