// The ticket page: title and description edited in place, and the sidebar's properties saved as
// soon as they change. Runs after DOMContentLoaded, once editor.js and selects.js (deferred) exist.
document.addEventListener('DOMContentLoaded', () => {
  // In-place editing: [data-tk-editable] holds a view and a form; [data-editing] shows the form.
  const openEditor = (editable) => {
    editable.setAttribute('data-editing', '');
    const textarea = editable.querySelector('textarea[data-markdown-editor="lazy"]');
    if (textarea) {
      window.gildeMarkdownEditor(textarea).codemirror.focus();
    } else {
      editable.querySelector('input[type=text]')?.focus();
    }
  };
  const setUpEditable = (editable) => {
    editable.querySelector('[data-tk-edit]').addEventListener('click', () => openEditor(editable));
    editable.querySelector('[data-tk-cancel]').addEventListener('click', () => {
      const form = editable.querySelector('form');
      form.reset();
      const textarea = form.querySelector('textarea');
      if (textarea?.easyMDE) {
        textarea.easyMDE.value(textarea.defaultValue);
      }
      editable.removeAttribute('data-editing');
    });
    // A refused save comes back open, with the text that was typed.
    if (editable.hasAttribute('data-editing')) {
      openEditor(editable);
    }
  };
  document.querySelectorAll('[data-tk-editable]').forEach(setUpEditable);
  // A save replaces its block with the one from the page it returns (hx-select), which needs its
  // buttons wired again.
  document.body.addEventListener('htmx:load', (event) => {
    if (event.detail.elt.matches('[data-tk-editable]')) {
      setUpEditable(event.detail.elt);
    }
  });
  // htmx leaves the page as it was when a save fails; say so, and keep the text in the editor.
  document.body.addEventListener('htmx:responseError', (event) => {
    alert(interpolate(gettext('Saving failed (HTTP %s). Your text is still in the editor.'), [event.detail.xhr.status]));
  });
  // A reply, and editing a comment or reply, open the Markdown editor in their <details> (editor.js).

  // "Hide done" above the relations table, on by default; a viewer who turns it off is remembered.
  const hideDone = document.getElementById('tk-hide-done');
  if (hideDone) {
    const table = document.querySelector('.tk-relations');
    const apply = () => table.classList.toggle('tk-hide-done', hideDone.checked);
    try {
      hideDone.checked = localStorage.getItem('tk-hide-done') !== '0';
    } catch {
      // Storage can be unavailable (private window); the box then keeps its default, ticked.
    }
    apply();
    hideDone.addEventListener('change', () => {
      apply();
      try {
        localStorage.setItem('tk-hide-done', hideDone.checked ? '1' : '0');
      } catch {
        // Not remembered, but the table still follows the box.
      }
    });
  }

  // Properties, in the sidebar and in the relations table: each [data-tk-property] posts itself on
  // change, to the URL of the nearest [data-update-url], which names the ticket it belongs to.
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
  document.querySelectorAll('[data-tk-property]').forEach((control) => {
    const holder = control.closest('[data-update-url]');
    const status = holder.querySelector('.tk-saved');
    control.addEventListener('change', () => {
      const body = new FormData();
      body.append('field', control.dataset.tkProperty);
      body.append('value', control.value);
      if (status) status.textContent = gettext('Saving…');
      fetch(holder.dataset.updateUrl, { method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body })
        .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
          if (!ok) {
            throw new Error(data.error);
          }
          // A new status or group changes the status options and the activity, so show them fresh.
          if ('reload' in control.dataset || control.dataset.tkProperty === 'column') {
            window.location.reload();
            return;
          }
          if (status) {
            status.innerHTML = `<i class="bi bi-check2"></i> ${gettext('Saved')}`;
            setTimeout(() => { status.textContent = ''; }, 1500);
          }
        })
        .catch((error) => {
          alert(interpolate(gettext('Saving failed: %s. The page will reload.'), [error.message]));
          window.location.reload();
        });
    });
  });

  // Related tickets are dragged within their kind. A drop posts the ticket the row now sits above, or
  // the one it sits below at the end of the list; the server moves it there in the board's order.
  document.querySelectorAll('.tk-relations tbody').forEach((list) => {
    Sortable.create(list, {
      animation: 150,
      draggable: 'tr[data-ticket]',
      handle: '.tk-drag-handle',
      onEnd: (event) => {
        if (event.oldDraggableIndex === event.newDraggableIndex) {
          return;
        }
        const row = event.item;
        const next = row.nextElementSibling;
        const body = new FormData();
        if (next) {
          body.append('before', next.dataset.ticket);
        } else {
          body.append('after', row.previousElementSibling.dataset.ticket);
        }
        fetch(row.dataset.reorderUrl, { method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body })
          .then((response) => {
            if (!response.ok) {
              throw new Error(`HTTP ${response.status}`);
            }
          })
          .catch((error) => {
            alert(interpolate(gettext('Moving the ticket failed (%s). The page will reload.'), [error.message]));
            window.location.reload();
          });
      },
    });
  });

  // Files dropped anywhere on the page, or an image pasted outside a text field, are attached to the
  // ticket. An open editor handles its own drops and pastes: there the image goes into the text.
  const overlay = document.getElementById('tk-drop-overlay');
  const inEditor = (target) => target instanceof Element && target.closest('.EasyMDEContainer, input, textarea');
  const hasFiles = (event) => event.dataTransfer && [...event.dataTransfer.types].includes('Files');
  const attach = async (files) => {
    overlay.classList.add('tk-drop-busy');
    overlay.querySelector('span').textContent = interpolate(
      ngettext('Attaching %s file…', 'Attaching %s files…', files.length), [files.length],
    );
    for (const file of files) {
      const body = new FormData();
      body.append('action', 'attachment');
      body.append('file', file, file.name || 'pasted-image.png');
      const response = await fetch(window.location.pathname, { method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body });
      if (!response.ok) {
        alert(interpolate(gettext('Attaching %s failed (HTTP %s).'), [file.name, response.status]));
        break;
      }
    }
    window.location.reload();
  };
  let dragDepth = 0;
  document.addEventListener('dragenter', (event) => {
    if (hasFiles(event) && dragDepth++ === 0) overlay.classList.add('tk-drop-visible');
  });
  document.addEventListener('dragleave', (event) => {
    if (hasFiles(event) && --dragDepth === 0) overlay.classList.remove('tk-drop-visible');
  });
  document.addEventListener('dragover', (event) => {
    if (!hasFiles(event)) return;
    // Over an open editor the drop is the editor's, so the page's overlay steps aside.
    overlay.classList.toggle('tk-drop-visible', !inEditor(event.target));
    if (!inEditor(event.target)) event.preventDefault();
  });
  document.addEventListener('drop', (event) => {
    dragDepth = 0;
    overlay.classList.remove('tk-drop-visible');
    if (!hasFiles(event) || inEditor(event.target)) return;
    event.preventDefault();
    attach([...event.dataTransfer.files]);
  });
  document.addEventListener('paste', (event) => {
    const files = [...(event.clipboardData?.files || [])];
    if (!files.length || inEditor(event.target) || event.target.isContentEditable) return;
    event.preventDefault();
    attach(files);
  });

  // The sidebar stays in view while it fits on the screen; a taller one scrolls with the page, so its
  // lower panels stay reachable. Checked again when the window or the sidebar changes size.
  const sidebar = document.querySelector('.tk-sidebar');
  if (sidebar) {
    const fit = () => sidebar.classList.toggle('tk-sidebar-sticky', sidebar.offsetHeight + 32 <= window.innerHeight);
    new ResizeObserver(fit).observe(sidebar);
    window.addEventListener('resize', fit);
    fit();
  }
});
