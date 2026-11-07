// Searchable selects (Tom Select) for the tracker's pages.
//   select[data-tk-select]           searchable select: the field shows the value and the search sits in the
//                                    dropdown, a pick closes it, and an empty option ("Unassigned") is a
//                                    choice like any other. An option's data-data '{"choice": "Assign to me"}'
//                                    is what the list shows for it, and a select with such quick choices
//                                    opens at the top; any other at its value. With `multiple`, a multi-select with
//                                    remove buttons that stays open for the next pick.
//     data-submit-on-close           close the dropdown after each pick, and submit the form once it closes
//                                    on a changed value.
//   input[data-tk-labels]            comma-separated tags; data-options holds the existing names as JSON.
//   input[data-tk-ticket-search]     one ticket key, found by key or title via the URL in the attribute.

// Tom Select keeps the typed search after picking an option in a multi-select; clear it, so the
// next pick starts from the full list.
function clearSearch() {
  this.setTextboxValue('');
  this.refreshOptions(false);
}

const escapeHtml = (text) => text.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

document.querySelectorAll('select[data-tk-select]').forEach((select) => {
  // A single select with its search in the field looks as if it wants a second value, and left open
  // after a pick a backspace there clears the value.
  const settings = {
    maxOptions: null,
    plugins: select.multiple ? ['remove_button'] : ['dropdown_input'],
    hidePlaceholder: true,
    closeAfterSelect: !select.multiple,
    allowEmptyOption: !select.multiple,
    // Backspace in an empty search would delete a single select's value, and saving it at once:
    // emptying one takes its empty option ("Unassign") instead.
    onDelete: select.multiple ? null : () => false,
    dataAttr: 'data',
    searchField: ['text', 'choice'],
    render: {
      option: (data, escape) => `<div>${escape(data.choice || data.text)}</div>`,
      no_results: noResults,
    },
  };
  // In a scrolling table the dropdown would be clipped by the table's edge.
  if (select.closest('.table-responsive')) {
    settings.dropdownParent = 'body';
  }
  if (select.multiple) {
    settings.onItemAdd = clearSearch;
  }
  if ('submitOnClose' in select.dataset) {
    // Most filters want one value: a pick closes the dropdown, which applies it. Another value is one
    // more pick away.
    settings.closeAfterSelect = true;
    let before = null;
    settings.onDropdownOpen = function () { before = JSON.stringify(this.getValue()); };
    settings.onDropdownClose = function () {
      if (JSON.stringify(this.getValue()) !== before) select.form.submit();
    };
    // Removing a value with its x never opens the dropdown.
    settings.onItemRemove = function () { if (!this.isOpen) select.form.submit(); };
  }
  const tom = new TomSelect(select, settings);
  // Tom Select opens a single select scrolled to its value, with that value marked. A select with
  // quick choices at the top ("Unassign", "Assign to me", as data-data) opens at the top instead, where
  // they are. It scrolls once the dropdown is open, so this waits a frame.
  if (!select.multiple && select.querySelector('option[data-data]')) {
    tom.on('dropdown_open', () => requestAnimationFrame(() => {
      tom.setActiveOption(tom.selectable()[0], false);
      tom.dropdown_content.scrollTop = 0;
    }));
  }
});

// Tom Select's own texts, in the page's language (Django's JavaScript catalog).
function noResults() {
  return `<div class="no-results">${gettext('No results found')}</div>`;
}

document.querySelectorAll('input[data-tk-labels]').forEach((input) => {
  const names = JSON.parse(input.dataset.options);
  new TomSelect(input, {
    create: true,
    createOnBlur: true,
    delimiter: ',',
    persist: false,
    plugins: ['remove_button'],
    onItemAdd: clearSearch,
    options: names.map((name) => ({ value: name, text: name })),
    render: {
      option_create: (data, escape) => `<div class="create">${interpolate(gettext('Add %s…'), [`<strong>${escape(data.input)}</strong>`])}</div>`,
      no_results: noResults,
    },
  });
});

document.querySelectorAll('input[data-tk-ticket-search]').forEach((input) => {
  new TomSelect(input, {
    maxItems: 1,
    valueField: 'key',
    labelField: 'key',
    searchField: ['key', 'title'],
    loadThrottle: 250,
    shouldLoad: (query) => query.length > 0,
    load(query, callback) {
      fetch(`${input.dataset.tkTicketSearch}?q=${encodeURIComponent(query)}`)
        .then((response) => response.json())
        .then((data) => callback(data.results))
        .catch(() => callback());
    },
    render: {
      option: (item) => `<div class="d-flex gap-2"><span class="tk-key">${escapeHtml(item.key)}</span><span class="text-truncate">${escapeHtml(item.title)}</span></div>`,
      item: (item) => `<div><span class="tk-key">${escapeHtml(item.key)}</span></div>`,
      no_results: () => `<div class="no-results">${gettext('No ticket found')}</div>`,
    },
  });
});
