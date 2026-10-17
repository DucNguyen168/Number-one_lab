/* Shared interaction layer. Native dialogs provide focus trapping and inert backgrounds. */
(() => {
  const closing = new WeakMap();
  const openers = new WeakMap();
  let pageAnimation;
  const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function syncDialogLock() {
    document.body.classList.toggle('dialog-open', Boolean(document.querySelector('dialog[open]')));
  }

  function openDialog(dialog) {
    closing.get(dialog)?.cancel();
    closing.delete(dialog);
    if (dialog.open) return;
    openers.set(dialog, document.activeElement);
    dialog.showModal();
    syncDialogLock();
    if (!reducedMotion() && dialog.animate) {
      dialog.animate([{ opacity: 0, transform: 'translateY(12px) scale(.985)' },
        { opacity: 1, transform: 'translateY(0) scale(1)' }], { duration: 180, easing: 'ease-out' });
    }
  }

  function closeDialog(dialog) {
    if (!dialog.open || closing.has(dialog)) return;
    const finish = () => {
      closing.delete(dialog);
      dialog.close();
      syncDialogLock();
      const opener = openers.get(dialog);
      if (opener?.isConnected) opener.focus({ preventScroll: true });
      openers.delete(dialog);
    };
    if (reducedMotion() || !dialog.animate) return finish();
    const animation = dialog.animate([{ opacity: 1, transform: 'translateY(0)' },
      { opacity: 0, transform: 'translateY(8px)' }], { duration: 140, easing: 'ease-in' });
    closing.set(dialog, animation);
    animation.finished.then(finish, () => {});
  }

  document.querySelectorAll('dialog').forEach(dialog => {
    let backdropPress = false;
    dialog.addEventListener('close', syncDialogLock);
    if (dialog.dataset.dismissible !== 'true') return;
    const outside = event => {
      const bounds = dialog.getBoundingClientRect();
      return event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right
        || event.clientY < bounds.top || event.clientY > bounds.bottom);
    };
    dialog.addEventListener('pointerdown', event => { backdropPress = outside(event); });
    dialog.addEventListener('click', event => {
      if (backdropPress && outside(event)) closeDialog(dialog);
      backdropPress = false;
    });
    dialog.addEventListener('cancel', event => {
      event.preventDefault();
      closeDialog(dialog);
    });
  });

  function transitionPage() {
    pageAnimation?.cancel();
    const main = document.getElementById('main-content');
    if (!reducedMotion() && main?.animate) {
      pageAnimation = main.animate([{ opacity: .35, transform: 'translateY(8px)' },
        { opacity: 1, transform: 'translateY(0)' }], { duration: 200, easing: 'ease-out' });
    }
  }

  // Scrollable data regions can also be reached and scrolled with a keyboard.
  document.querySelectorAll('.table-wrap').forEach(region => {
    region.tabIndex = 0;
    region.setAttribute('role', 'region');
    region.setAttribute('aria-label', region.closest('section')?.querySelector('h2, h3')?.textContent
      || 'Bảng dữ liệu, cuộn ngang để xem thêm');
  });
  window.DashboardUI = { openDialog, closeDialog, transitionPage };
})();
