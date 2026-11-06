// Copies a link from a [data-tk-copy-link] button: to this page when it is empty, to one comment on it with
// "#comment-12", or to another page by its path, such as the ticket in the quick view.
document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-tk-copy-link]');
  if (!button || button.dataset.copied) {
    return;
  }
  const url = new URL(button.dataset.tkCopyLink, window.location.origin + window.location.pathname).href;
  navigator.clipboard.writeText(url).then(() => {
    const before = button.innerHTML;
    button.dataset.copied = 'true';
    // A button with words says so; an icon alone just turns into a tick.
    button.innerHTML = button.textContent.trim() ? `<i class="bi bi-check2"></i> ${gettext('Copied')}` : '<i class="bi bi-check2"></i>';
    setTimeout(() => {
      button.innerHTML = before;
      delete button.dataset.copied;
    }, 1500);
  });
});
