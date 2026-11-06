// Turns a textarea[data-markdown-editor] into an EasyMDE editor. The stored value is the plain
// Markdown the user typed; pasted or dropped images are uploaded to the URL on the nearest
// [data-upload-url] ancestor and inserted as a Markdown image. A textarea marked "lazy" waits for
// window.tkMarkdownEditor(textarea), because an editor built while hidden renders blank.

// @-mentions: "@" and the start of a handle, first or last name lists the colleagues it may mean
// (mention_people); ↑/↓ choose, Enter or Tab fill in the handle that reaches them, Esc closes. Not in code.
const mentionPeople = JSON.parse(document.getElementById('tk-mention-people').textContent);
// "@" and what follows it up to the cursor, where a mention can start: not inside a word or an email address.
const MENTION_BEFORE_CURSOR = /(?:^|[^\w@.])@([\w.-]*)$/;
const mentionHandles = new Set(mentionPeople.map((person) => person.handle));

// Marks each @handle that reaches a colleague while it is written, read as notifications.MENTION_RE reads
// it: in any case, not after a letter, "@" or ".", and without a sentence's closing full stop.
const mentionOverlay = {
  token(stream) {
    const after = stream.pos === 0 ? '' : stream.string.charAt(stream.pos - 1);
    const found = !/[\w@.]/.test(after) && stream.match(/^@([a-z0-9][\w.-]*)/i);
    if (found) {
      const handle = found[1].replace(/\.+$/, '');
      if (mentionHandles.has(handle.toLowerCase())) {
        stream.backUp(found[1].length - handle.length);
        return 'tk-mention';
      }
      return null;
    }
    stream.next();
    while (!stream.eol() && stream.peek() !== '@') {
      stream.next();
    }
    return null;
  },
};

function attachMentions(cm) {
  cm.addOverlay(mentionOverlay);
  const menu = document.createElement('ul');
  menu.className = 'tk-mention-menu';
  menu.hidden = true;
  document.body.append(menu);
  let matches = [];
  let active = 0;
  let start = null;

  const close = () => {
    menu.hidden = true;
    matches = [];
  };
  const pick = (person) => {
    cm.replaceRange(`@${person.handle} `, start, cm.getCursor());
    close();
    cm.focus();
  };
  const render = () => {
    menu.replaceChildren(...matches.map((person, index) => {
      const item = document.createElement('li');
      item.classList.toggle('active', index === active);
      const name = document.createElement('span');
      name.textContent = person.name;
      const handle = document.createElement('span');
      handle.className = 'tk-mention-handle';
      handle.textContent = `@${person.handle}`;
      item.append(name, handle);
      // On mousedown, so the editor keeps its focus and its cursor.
      item.addEventListener('mousedown', (event) => {
        event.preventDefault();
        pick(person);
      });
      return item;
    }));
  };
  const update = () => {
    const cursor = cm.getCursor();
    const found = MENTION_BEFORE_CURSOR.exec(cm.getLine(cursor.line).slice(0, cursor.ch));
    // The markdown mode marks code as "comment".
    if (!found || (cm.getTokenTypeAt(cursor) || '').includes('comment')) {
      close();
      return;
    }
    const typed = found[1].toLowerCase();
    matches = mentionPeople
      .filter((person) => person.handle.startsWith(typed) || person.name.toLowerCase().split(/\s+/).some((word) => word.startsWith(typed)))
      .slice(0, 8);
    if (!matches.length) {
      close();
      return;
    }
    start = { line: cursor.line, ch: cursor.ch - found[1].length - 1 };
    active = 0;
    const place = cm.cursorCoords(start, 'page');
    menu.style.left = `${place.left}px`;
    menu.style.top = `${place.bottom + 2}px`;
    menu.hidden = false;
    render();
  };

  cm.on('change', update);
  // Moving the cursor away from the mention closes the list; moving into one does not open it.
  cm.on('cursorActivity', () => {
    if (!menu.hidden) {
      update();
    }
  });
  cm.on('blur', close);
  // The list's keys go before the editor's own, and no further, so Esc closes only the list.
  cm.on('keydown', (_cm, event) => {
    if (menu.hidden) {
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      active = (active + (event.key === 'ArrowDown' ? 1 : matches.length - 1)) % matches.length;
      render();
    } else if (event.key === 'Enter' || event.key === 'Tab') {
      pick(matches[active]);
    } else if (event.key === 'Escape') {
      close();
    } else {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
  });
}

window.tkMarkdownEditor = (textarea) => {
  if (textarea.easyMDE) {
    return textarea.easyMDE;
  }
  const form = textarea.closest('form');
  const uploadHolder = textarea.closest('[data-upload-url]');
  textarea.easyMDE = new EasyMDE({
    element: textarea,
    spellChecker: false,
    status: false,
    forceSync: true,
    autoDownloadFontAwesome: false,
    minHeight: textarea.rows > 6 ? '220px' : '90px',
    uploadImage: Boolean(uploadHolder),
    imageUploadEndpoint: uploadHolder ? uploadHolder.dataset.uploadUrl : undefined,
    imageCSRFToken: form.querySelector('[name=csrfmiddlewaretoken]').value,
    imagePathAbsolute: true,
    imageMaxSize: 20 * 1024 * 1024,
    imageAccept: 'image/png, image/jpeg, image/gif, image/webp',
    // An image on a line of its own shows under it while writing.
    previewImagesInEditor: true,
    toolbar: [
      { name: 'bold', action: EasyMDE.toggleBold, className: 'bi bi-type-bold', title: gettext('Bold') },
      { name: 'italic', action: EasyMDE.toggleItalic, className: 'bi bi-type-italic', title: gettext('Italic') },
      { name: 'heading', action: EasyMDE.toggleHeadingSmaller, className: 'bi bi-type-h2', title: gettext('Heading') },
      '|',
      { name: 'quote', action: EasyMDE.toggleBlockquote, className: 'bi bi-quote', title: gettext('Quote') },
      { name: 'unordered-list', action: EasyMDE.toggleUnorderedList, className: 'bi bi-list-ul', title: gettext('List') },
      { name: 'ordered-list', action: EasyMDE.toggleOrderedList, className: 'bi bi-list-ol', title: gettext('Numbered list') },
      { name: 'code', action: EasyMDE.toggleCodeBlock, className: 'bi bi-code', title: gettext('Code') },
      { name: 'link', action: EasyMDE.drawLink, className: 'bi bi-link-45deg', title: gettext('Link') },
      ...(uploadHolder
        ? [{ name: 'upload-image', action: EasyMDE.drawUploadedImage, className: 'bi bi-image', title: gettext('Image') }]
        : []),
      '|',
      { name: 'preview', action: EasyMDE.togglePreview, className: 'bi bi-eye', title: gettext('Preview'), noDisable: true },
    ],
  });
  attachMentions(textarea.easyMDE.codemirror);
  return textarea.easyMDE;
};

document.querySelectorAll('textarea[data-markdown-editor]:not([data-markdown-editor="lazy"])').forEach(window.tkMarkdownEditor);
