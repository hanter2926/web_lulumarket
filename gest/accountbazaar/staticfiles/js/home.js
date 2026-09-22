document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-faq] summary').forEach((summary) => summary.addEventListener('click', () => {
    const current = summary.parentElement;
    document.querySelectorAll('[data-faq] details').forEach((item) => { if (item !== current) item.removeAttribute('open'); });
  }));
});
