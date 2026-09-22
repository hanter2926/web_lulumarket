document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-password-toggle]').forEach((button) => button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.passwordToggle);
    if (input) input.type = input.type === 'password' ? 'text' : 'password';
  }));
});
