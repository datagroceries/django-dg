// Keyboard shortcuts on the tracker's pages: "/" puts the cursor in the board's search field, "c"
// starts a new ticket: in the first column of the board's group, else on the form, where the group is
// chosen. Typing anywhere, in a field or the Markdown editor, is left alone.
(() => {
  const newTicketUrl = document.currentScript.dataset.newTicketUrl;
  document.addEventListener('keydown', (event) => {
    const target = event.target;
    const typing = target.closest('input, textarea, select, [contenteditable], .CodeMirror, .ts-wrapper');
    if (typing || event.metaKey || event.ctrlKey || event.altKey) {
      return;
    }
    if (event.key === '/') {
      const search = document.querySelector('.tk-filters input[name=q]');
      if (search) {
        event.preventDefault();
        search.focus();
        search.select();
      }
    } else if (event.key === 'c') {
      event.preventDefault();
      window.location.href = document.querySelector('[data-tk-new-ticket]')?.href || newTicketUrl;
    }
  });
})();
