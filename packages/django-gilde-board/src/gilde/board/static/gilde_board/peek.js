// The quick view: a link with data-tk-peek (the eye on a card or a related ticket's row, a related ticket in
// the panel) shows that ticket in a panel on the right instead of opening its page. The next eye can be
// clicked straight away; the same eye again, a click anywhere else beside the panel, Esc or the cross
// closes it. Cmd-, Ctrl- or Shift-click opens the page instead. A click anywhere else on a card opens the
// page, as its title does.
(() => {
  let panel = null;
  let offcanvas = null;
  let latest = 0;
  let pressedInPanel = false;
  // The quick view URL of the ticket in the panel, while it is open.
  let shown = null;

  const create = () => {
    panel = document.createElement('aside');
    panel.className = 'offcanvas offcanvas-end tk-peek';
    panel.tabIndex = -1;
    panel.setAttribute('aria-label', gettext('Ticket quick view'));
    panel.innerHTML = '<div class="offcanvas-body"></div>';
    document.body.append(panel);
    // No backdrop and no scroll lock, so the page beside the panel can still be scrolled and clicked.
    offcanvas = new bootstrap.Offcanvas(panel, { backdrop: false, scroll: true });
    panel.addEventListener('hidden.bs.offcanvas', () => mark(null));
  };

  // Marks the cards and rows of the ticket the panel shows, so it can be found on the page; also when it
  // was reached through a related ticket in the panel itself.
  const mark = (peekUrl) => {
    shown = peekUrl;
    document.querySelectorAll('.tk-peeked').forEach((element) => element.classList.remove('tk-peeked'));
    if (!peekUrl) {
      return;
    }
    document.querySelectorAll(`a[data-tk-peek="${CSS.escape(peekUrl)}"]`).forEach((link) => {
      if (!panel.contains(link)) {
        link.closest('.tk-card, tr')?.classList.add('tk-peeked');
      }
    });
  };

  const show = (link) => {
    if (!panel) {
      create();
    }
    mark(link.dataset.tkPeek);
    const body = panel.querySelector('.offcanvas-body');
    body.innerHTML = '<div class="tk-peek-loading"><div class="spinner-border spinner-border-sm"></div> Loading…</div>';
    offcanvas.show();
    // A slow answer for a ticket clicked earlier never replaces the one clicked last.
    const request = ++latest;
    fetch(link.dataset.tkPeek)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.text();
      })
      .then((html) => {
        if (request === latest) {
          body.innerHTML = html;
          body.scrollTop = 0;
        }
      })
      .catch((error) => {
        if (request === latest) {
          body.innerHTML = `<p class="tk-small">Loading the ticket failed (${error.message}). <a href="${link.href}">Open its page</a>.</p>`;
        }
      });
  };

  // Where a click started: selecting text in the panel ends in a click outside it, which must not close it.
  document.addEventListener('pointerdown', (event) => {
    pressedInPanel = Boolean(panel?.contains(event.target));
  });

  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[data-tk-peek]');
    if (link) {
      if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && event.button === 0) {
        event.preventDefault();
        // The eye of the ticket the panel already shows closes it again.
        if (panel?.classList.contains('show') && shown === link.dataset.tkPeek) {
          offcanvas.hide();
        } else {
          show(link);
        }
      }
      return;
    }
    // A card opens its page from anywhere on it, except from its other links and buttons: a label, its parent, a "+".
    const card = !event.target.closest('a, button, input, textarea') && event.target.closest('.tk-card');
    if (card) {
      const page = card.querySelector('.tk-card-title').href;
      if (event.metaKey || event.ctrlKey || event.shiftKey) {
        window.open(page, '_blank');
      } else {
        window.location.assign(page);
      }
      return;
    }
    // A target that left the page meanwhile, such as the panel's own content being replaced, says nothing
    // about where the click was.
    if (!panel?.classList.contains('show')) {
      return;
    }
    if (event.target.isConnected && !panel.contains(event.target) && !pressedInPanel) {
      offcanvas.hide();
    }
  });

  // Esc closes the panel wherever the focus is, unless it is in a field or an open dropdown.
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || !panel?.classList.contains('show')) {
      return;
    }
    if (event.target.closest('input, textarea, select, [contenteditable], .CodeMirror, .ts-wrapper')) {
      return;
    }
    offcanvas.hide();
  });
})();
