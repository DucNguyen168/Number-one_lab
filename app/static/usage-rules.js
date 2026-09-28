(() => {
  const dialog = document.getElementById('usage-rules');
  const form = document.getElementById('usage-rules-form');
  const agree = document.getElementById('usage-rules-agree');
  const continueButton = document.getElementById('usage-rules-continue');

  function openRules() {
    agree.checked = false;
    continueButton.disabled = true;
    document.body.classList.add('usage-rules-open');
    if (!dialog.open) dialog.showModal();
    // Start at the heading so long notices can be read from the beginning.
    const heading = document.getElementById('usage-rules-title');
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
    dialog.scrollTop = 0;
  }

  agree.addEventListener('change', () => {
    continueButton.disabled = !agree.checked;
  });
  dialog.addEventListener('cancel', (event) => event.preventDefault());
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!agree.checked) return;
    dialog.close();
    document.body.classList.remove('usage-rules-open');
    document.querySelector('.app-brand')?.focus({ preventScroll: true });
  });
  // A restored page is also a new visit; never persist acceptance in storage.
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) openRules();
  });
  openRules();
})();
