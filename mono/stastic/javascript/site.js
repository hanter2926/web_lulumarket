document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('[data-confirm]').forEach(function (element) {
    element.addEventListener('click', function (event) {
      if (!window.confirm(element.dataset.confirm)) event.preventDefault();
    });
  });
});
