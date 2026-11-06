// A card's assignee changes on the board itself: a click on it opens the board's one assignee picker
// beside it, and a pick saves at once, as on the ticket page (ticket_update), and puts the card's new
// assignee in its place. The live search replaces the cards, so their clicks are caught on the page.
(() => {
  const picker = document.querySelector('.tk-assignee-picker');
  const csrfToken = document.querySelector('#ticket-board [name=csrfmiddlewaretoken]').value;
  // The card's assignee the picker is open for.
  let current = null;

  document.addEventListener('click', (event) => {
    const clicked = event.target.closest('.tk-card .tk-assignee');
    if (!clicked) {
      return;
    }
    event.preventDefault();
    current = clicked;
    const tom = picker.querySelector('select').tomselect;
    const place = clicked.getBoundingClientRect();
    picker.hidden = false;
    picker.style.top = `${place.bottom + window.scrollY + 4}px`;
    picker.style.left = `${Math.max(8, place.right + window.scrollX - picker.offsetWidth)}px`;
    tom.setValue(clicked.dataset.assignee, true);
    tom.focus();
  });

  // Tom Select takes the select over in selects.js, which runs deferred: after this script.
  document.addEventListener('DOMContentLoaded', () => {
    const tom = picker.querySelector('select').tomselect;
    tom.on('change', (value) => {
      const assignee = current;
      const body = new FormData();
      body.append('field', 'assignee');
      body.append('value', value);
      fetch(assignee.dataset.assignUrl, { method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body })
        .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
          if (!ok) {
            throw new Error(data.error);
          }
          assignee.outerHTML = data.card_assignee;
        })
        .catch((error) => {
          alert(interpolate(gettext('Assigning the ticket failed (%s). The board will reload.'), [error.message]));
          window.location.reload();
        });
    });
    tom.on('dropdown_close', () => {
      picker.hidden = true;
      tom.blur();
    });
  });
})();
