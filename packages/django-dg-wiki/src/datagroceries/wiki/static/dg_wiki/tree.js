// Dragging a page in the tree: onto the top or bottom edge of another page puts it before or after that
// one, onto its middle puts it under it, last. The server answers with the tree as it is now. The Move
// page does the same without a mouse.
(() => {
  const holder = document.querySelector('.wk-tree-holder');
  if (!holder) {
    return;
  }
  const csrfToken = holder.querySelector('[name=csrfmiddlewaretoken]').value;
  // The page being dragged (its <li>), and the link it would drop onto, and where.
  let dragged = null;
  let target = null;
  let zone = null;

  const pageOf = (item) => item.querySelector('a[data-page]').dataset.page;

  function clear() {
    if (target) {
      target.classList.remove('wk-drop-before', 'wk-drop-after', 'wk-drop-into');
    }
    target = null;
    zone = null;
  }

  holder.addEventListener('dragstart', (event) => {
    const link = event.target.closest && event.target.closest('a[data-page]');
    if (!link) {
      return;
    }
    dragged = link.closest('li');
    dragged.classList.add('wk-dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', link.href);
  });

  holder.addEventListener('dragover', (event) => {
    if (!dragged) {
      return;
    }
    const link = event.target.closest('a[data-page]');
    // Not onto itself or a page under it.
    if (!link || dragged.contains(link)) {
      clear();
      return;
    }
    event.preventDefault();
    const box = link.getBoundingClientRect();
    const share = (event.clientY - box.top) / box.height;
    const where = share < 0.25 ? 'before' : share > 0.75 ? 'after' : 'into';
    if (link !== target || where !== zone) {
      clear();
      target = link;
      zone = where;
      link.classList.add(`wk-drop-${where}`);
    }
  });

  holder.addEventListener('dragend', () => {
    clear();
    if (dragged) {
      dragged.classList.remove('wk-dragging');
    }
    dragged = null;
  });

  holder.addEventListener('drop', (event) => {
    event.preventDefault();
    if (!dragged || !target) {
      return;
    }
    const item = target.closest('li');
    const body = new FormData();
    body.append('page', pageOf(dragged));
    if (zone === 'into') {
      body.append('parent', pageOf(item));
    } else {
      const above = item.parentElement.closest('li');
      if (above) {
        body.append('parent', pageOf(above));
      }
      let before = zone === 'before' ? item : item.nextElementSibling;
      if (before === dragged) {
        before = before.nextElementSibling;
      }
      if (before) {
        body.append('before', pageOf(before));
      }
    }
    if (holder.dataset.current) {
      body.append('current', holder.dataset.current);
    }
    clear();
    fetch(holder.dataset.arrangeUrl, { method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then((answer) => {
        // The page shown moved along: it has another address now, and other crumbs.
        if (answer.url && answer.url !== window.location.pathname) {
          window.location.assign(answer.url);
          return;
        }
        holder.querySelector('.wk-tree, p').outerHTML = answer.tree;
      })
      .catch(() => {
        alert(holder.dataset.failed);
        window.location.reload();
      });
  });
})();
