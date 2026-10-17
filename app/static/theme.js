// Apply the saved theme before styles paint, including when storage is unavailable.
(() => {
  let theme;
  try { theme = localStorage.getItem('xsmb-theme'); } catch { /* Private storage may be blocked. */ }
  if (!['light', 'dark'].includes(theme)) {
    theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  document.documentElement.dataset.theme = theme;
})();
