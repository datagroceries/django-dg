// Drag and drop on a group's board. A drop posts the target column and the ticket the card now
// sits above; the server works out the rank, which stays right on a filtered board.
const csrfToken = document.querySelector('#ticket-board [name=csrfmiddlewaretoken]').value;

function updateCounts() {
  document.querySelectorAll('.tk-lane').forEach((lane) => {
    lane.querySelector('.ticket-lane-count').textContent = lane.querySelectorAll('.tk-card').length;
  });
}

document.querySelectorAll('.tk-lane-cards[data-column]').forEach((list) => {
  Sortable.create(list, {
    group: 'tickets',
    animation: 150,
    draggable: '.tk-card',
    // On a touchscreen a card is picked up only after a moment's press, so scrolling stays scrolling.
    delay: 250,
    delayOnTouchOnly: true,
    touchStartThreshold: 5,
    filter: '.tk-insert',
    preventOnFilter: false,
    onEnd: (event) => {
      if (event.from === event.to && event.oldDraggableIndex === event.newDraggableIndex) {
        return;
      }
      const card = event.item;
      let next = card.nextElementSibling;
      while (next && !next.classList.contains('tk-card')) {
        next = next.nextElementSibling;
      }
      const body = new FormData();
      body.append('column', event.to.dataset.column);
      if (next) {
        body.append('before', next.dataset.ticket);
      }
      fetch(card.dataset.moveUrl, { method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          updateCounts();
          const folded = event.to.closest('.tk-collapsed');
          if (folded) {
            folded.classList.add('tk-dropped');
            folded.addEventListener('animationend', () => folded.classList.remove('tk-dropped'), { once: true });
          }
        })
        .catch((error) => {
          alert(interpolate(gettext('Moving the ticket failed (%s). The board will reload.'), [error.message]));
          window.location.reload();
        });
    },
  });
});

// A "+" on the board opens a title field right there: Enter adds the ticket and keeps the field open
// for the next one, Escape (or leaving it empty) closes it. Cmd- or Ctrl-click opens the full form.
const board = document.getElementById('ticket-board');

function closeQuickCreate() {
  document.querySelector('.tk-quick-create')?.remove();
}

function openQuickCreate(list, beforeCard) {
  closeQuickCreate();
  const form = document.createElement('form');
  form.className = 'tk-quick-create';
  form.innerHTML = '<textarea class="form-control form-control-sm" rows="2"></textarea>';
  form.querySelector('textarea').placeholder = gettext('Title, then Enter · Esc to stop');
  list.insertBefore(form, beforeCard);
  const input = form.querySelector('textarea');
  input.focus();
  const submit = () => {
    const title = input.value.trim();
    if (!title) {
      return;
    }
    const body = new FormData();
    body.append('column', list.dataset.column);
    body.append('title', title);
    if (beforeCard) {
      body.append('before', beforeCard.dataset.ticket);
    }
    input.disabled = true;
    fetch(board.dataset.quickCreateUrl, { method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body })
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          throw new Error(data.error);
        }
        form.insertAdjacentHTML('beforebegin', data.html);
        input.value = '';
        input.disabled = false;
        input.focus();
        updateCounts();
      })
      .catch((error) => {
        input.disabled = false;
        alert(interpolate(gettext('Creating the ticket failed: %s'), [error.message]));
      });
  };
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    } else if (event.key === 'Escape') {
      closeQuickCreate();
    }
  });
  input.addEventListener('blur', () => {
    if (!input.value.trim() && !input.disabled) {
      setTimeout(closeQuickCreate, 150);
    }
  });
}

board.addEventListener('click', (event) => {
  const plus = event.target.closest('[data-quick-create]');
  if (!plus || event.metaKey || event.ctrlKey || event.shiftKey) {
    return;
  }
  event.preventDefault();
  const lane = plus.closest('.tk-lane');
  const card = plus.closest('.tk-card');
  openQuickCreate(lane.querySelector('.tk-lane-cards'), card);
});

