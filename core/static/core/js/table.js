(function () {
  const documentLang = (document.documentElement.lang || 'en').toLowerCase();
  const locale = documentLang || undefined;
  const digitMap = {
    '۰': '0',
    '۱': '1',
    '۲': '2',
    '۳': '3',
    '۴': '4',
    '۵': '5',
    '۶': '6',
    '۷': '7',
    '۸': '8',
    '۹': '9',
    '٠': '0',
    '١': '1',
    '٢': '2',
    '٣': '3',
    '٤': '4',
    '٥': '5',
    '٦': '6',
    '٧': '7',
    '٨': '8',
    '٩': '9',
  };

  function normaliseText(value) {
    if (value == null) {
      return '';
    }
    const stringValue = String(value).trim();
    return stringValue.replace(/[۰-۹٠-٩]/g, (char) => digitMap[char] || char);
  }

  function normaliseForSearch(value) {
    return normaliseText(value).toLocaleLowerCase(locale || undefined);
  }

  function extractNumeric(value) {
    if (typeof value === 'number') {
      return value;
    }
    const normalised = normaliseText(value)
      .replace(/[٬,\s]/g, '')
      .replace(/[٫]/g, '.')
      .replace(/٪/g, '');
    const cleaned = normalised.replace(/[^0-9+\-.]/g, '');
    if (!cleaned) {
      return NaN;
    }
    return Number(cleaned);
  }

  function getCellContent(cell) {
    if (!cell) {
      return '';
    }
    if (cell.dataset.sortValue) {
      return cell.dataset.sortValue;
    }
    const input = cell.querySelector('input, select, textarea');
    if (input) {
      if (input.type === 'checkbox' || input.type === 'radio') {
        return input.checked ? '1' : '0';
      }
      return input.value;
    }
    return normaliseText(cell.textContent);
  }

  function parseNumericFilter(filterValue, cellValue) {
    const filter = normaliseText(filterValue);
    if (!filter) {
      return true;
    }
    const cellNumber = extractNumeric(cellValue);
    if (Number.isNaN(cellNumber)) {
      return false;
    }

    const rangeMatch = filter.match(/^\s*(-?\d+(?:[.,]\d+)?)\s*[-–]\s*(-?\d+(?:[.,]\d+)?)\s*$/);
    if (rangeMatch) {
      const min = Number(rangeMatch[1].replace(',', '.'));
      const max = Number(rangeMatch[2].replace(',', '.'));
      if (Number.isNaN(min) || Number.isNaN(max)) {
        return false;
      }
      return cellNumber >= Math.min(min, max) && cellNumber <= Math.max(min, max);
    }

    const comparatorMatch = filter.match(/^\s*(<=|>=|<|>|=)\s*(-?\d+(?:[.,]\d+)?)\s*$/);
    if (comparatorMatch) {
      const comparator = comparatorMatch[1];
      const compareValue = Number(comparatorMatch[2].replace(',', '.'));
      if (Number.isNaN(compareValue)) {
        return false;
      }
      switch (comparator) {
        case '<':
          return cellNumber < compareValue;
        case '<=':
          return cellNumber <= compareValue;
        case '>':
          return cellNumber > compareValue;
        case '>=':
          return cellNumber >= compareValue;
        default:
          return cellNumber === compareValue;
      }
    }

    const numericValue = Number(filter.replace(',', '.'));
    if (!Number.isNaN(numericValue)) {
      return cellNumber === numericValue;
    }

    return normaliseForSearch(cellValue).includes(normaliseForSearch(filter));
  }

  const toolbarMessages = {
    fa: {
      searchPlaceholder: 'جستجو در جدول…',
      searchLabel: 'جستجو در جدول',
      showFilters: 'نمایش فیلترها',
      hideFilters: 'پنهان کردن فیلترها',
      toggleLabel: 'تغییر وضعیت فیلترهای جدول',
    },
    en: {
      searchPlaceholder: 'Search table…',
      searchLabel: 'Search this table',
      showFilters: 'Show filters',
      hideFilters: 'Hide filters',
      toggleLabel: 'Toggle table filters',
    },
  };

  function resolveMessages() {
    const short = documentLang.split('-')[0];
    if (toolbarMessages[short]) {
      return toolbarMessages[short];
    }
    return toolbarMessages.en;
  }

  class InteractiveTable {
    constructor(table) {
      this.table = table;
      this.tbody = table.querySelector('tbody');
      this.container = table.closest('.table-responsive') || table.parentElement || table;
      this.sortColumn = null;
      this.sortDirection = 'asc';
      this.filterTimer = null;
      this.emptyText = table.dataset.emptyText || 'No results to display.';
      this.searchText = table.dataset.searchText || 'Filtering…';
      this.statusEl = this.createStatusElement();
      this.messages = resolveMessages();
      this.globalFilter = '';
      this.filtersVisible = true;
      this.captureRows();
      this.cacheControls();
      this.createToolbar();
      this.bindEvents();
      this.applyFilters({ resetSort: false });
      table.dispatchEvent(
        new CustomEvent('interactive-table:init', {
          bubbles: true,
          detail: { instance: this },
        })
      );
    }

    createStatusElement() {
      if (!this.container) {
        return null;
      }
      const status = document.createElement('div');
      status.className = 'table-status';
      status.setAttribute('role', 'status');
      status.setAttribute('aria-live', 'polite');
      status.hidden = true;
      this.container.appendChild(status);
      return status;
    }

    cacheControls() {
      this.sortButtons = Array.from(this.table.querySelectorAll('[data-sort-column]'));
      this.filterInputs = Array.from(this.table.querySelectorAll('[data-filter-column]'));
      this.filterRow = null;
      this.columnMeta = new Map();
      this.sortButtons.forEach((btn) => {
        const column = Number(btn.dataset.sortColumn);
        const type = btn.dataset.sortType || 'text';
        this.columnMeta.set(column, { type });
      });
      this.filterInputs.forEach((input) => {
        const column = Number(input.dataset.filterColumn);
        const type = input.dataset.filterType || 'text';
        if (!this.columnMeta.has(column)) {
          this.columnMeta.set(column, { type });
        } else {
          this.columnMeta.get(column).type = type;
        }
        if (!this.filterRow) {
          const row = input.closest('tr');
          if (row) {
            this.filterRow = row;
            row.dataset.tableFilterRow = 'true';
          }
        }
      });
      if (this.filterRow) {
        this.table.classList.add('has-filter-row');
        if (this.filterRow.hasAttribute('hidden')) {
          this.filtersVisible = false;
          this.table.classList.add('table-filters-hidden');
        }
      }
    }

    bindEvents() {
      this.sortButtons.forEach((button) => {
        button.addEventListener('click', () => this.handleSort(button));
      });
      this.filterInputs.forEach((input) => {
        const handler = () => {
          this.triggerFilterUpdate();
        };
        input.addEventListener('input', handler);
        input.addEventListener('change', handler);
      });
      if (this.globalSearchInput) {
        this.globalSearchInput.addEventListener('input', () => {
          this.setGlobalFilter(this.globalSearchInput.value);
        });
      }
      if (this.filterToggleButton) {
        this.filterToggleButton.addEventListener('click', () => {
          this.toggleAdvancedFilters();
        });
      }
    }

    handleSort(button) {
      const column = Number(button.dataset.sortColumn);
      if (this.sortColumn === column) {
        this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
      } else {
        this.sortColumn = column;
        this.sortDirection = 'asc';
      }
      this.applyFilters({ resetSort: false });
    }

    captureRows() {
      const rows = Array.from(this.tbody ? this.tbody.children : []);
      this.originalRows = rows
        .filter((row) => !row.hasAttribute('data-empty-row'))
        .map((row, index) => ({ row, index }));
    }

    refresh() {
      this.captureRows();
      this.applyFilters({ resetSort: false });
    }

    getFilters() {
      const filters = [];
      this.filterInputs.forEach((input) => {
        const value = normaliseText(input.value);
        if (!value) {
          return;
        }
        filters.push({
          column: Number(input.dataset.filterColumn),
          type: input.dataset.filterType || 'text',
          value,
          valueLower: normaliseForSearch(value),
        });
      });
      return filters;
    }

    matchesRow(row, filters, globalTerm) {
      if (globalTerm) {
        const cells = Array.from(row.cells || []);
        const hasMatch = cells.some((cell) => {
          const cellValue = getCellContent(cell);
          if (!cellValue) {
            return false;
          }
          return normaliseForSearch(cellValue).includes(globalTerm);
        });
        if (!hasMatch) {
          return false;
        }
      }
      if (!filters.length) {
        return true;
      }
      return filters.every((filter) => {
        const cell = row.cells[filter.column];
        const cellValue = getCellContent(cell);
        if (filter.type === 'number') {
          return parseNumericFilter(filter.value, cellValue);
        }
        return normaliseForSearch(cellValue).includes(filter.valueLower);
      });
    }

    sortRows(rows) {
      if (this.sortColumn == null) {
        return rows.slice();
      }
      const direction = this.sortDirection === 'asc' ? 1 : -1;
      const meta = this.columnMeta.get(this.sortColumn) || { type: 'text' };
      const type = meta.type;
      return rows.slice().sort((a, b) => {
        const cellA = getCellContent(a.row.cells[this.sortColumn]);
        const cellB = getCellContent(b.row.cells[this.sortColumn]);
        if (type === 'number') {
          const numA = extractNumeric(cellA);
          const numB = extractNumeric(cellB);
          if (Number.isNaN(numA) && Number.isNaN(numB)) {
            return a.index - b.index;
          }
          if (Number.isNaN(numA)) {
            return 1 * direction;
          }
          if (Number.isNaN(numB)) {
            return -1 * direction;
          }
          if (numA === numB) {
            return (a.index - b.index) * direction;
          }
          return numA > numB ? direction : -direction;
        }
        const textA = normaliseForSearch(cellA);
        const textB = normaliseForSearch(cellB);
        if (textA === textB) {
          return (a.index - b.index) * direction;
        }
        const comparison = textA.localeCompare(textB, locale, { sensitivity: 'accent' });
        return comparison * direction;
      });
    }

    applyFilters(options = {}) {
      if (!this.tbody) {
        return;
      }
      const filters = this.getFilters();
      const globalTerm = this.globalFilter;
      const filtered = this.originalRows.filter(({ row }) =>
        this.matchesRow(row, filters, globalTerm)
      );
      const sorted = this.sortRows(filtered);
      this.renderRows(sorted);
      this.updateSortIndicators();
      this.table.classList.toggle('has-active-filters', Boolean(filters.length) || Boolean(globalTerm));
      if (this.filterToggleButton) {
        this.filterToggleButton.classList.toggle('has-active-filters', Boolean(filters.length));
      }
      if (sorted.length === 0) {
        this.setStatus('empty');
      } else {
        this.setStatus('hidden');
      }
    }

    renderRows(rows) {
      if (!this.tbody) {
        return;
      }
      if (rows.length === 0) {
        this.tbody.innerHTML = '';
        return;
      }
      const nodes = rows.map((item) => item.row);
      this.tbody.replaceChildren(...nodes);
    }

    updateSortIndicators() {
      const ths = Array.from(this.table.querySelectorAll('thead th'));
      ths.forEach((th) => th.removeAttribute('aria-sort'));
      this.sortButtons.forEach((btn) => {
        btn.classList.remove('is-sorted-asc', 'is-sorted-desc');
      });
      if (this.sortColumn == null) {
        return;
      }
      const activeButton = this.sortButtons.find(
        (btn) => Number(btn.dataset.sortColumn) === this.sortColumn
      );
      if (activeButton) {
        activeButton.classList.add(
          this.sortDirection === 'asc' ? 'is-sorted-asc' : 'is-sorted-desc'
        );
        const th = activeButton.closest('th');
        if (th) {
          th.setAttribute('aria-sort', this.sortDirection === 'asc' ? 'ascending' : 'descending');
        }
      }
    }

    setStatus(state) {
      if (!this.statusEl) {
        return;
      }
      if (state === 'hidden') {
        this.statusEl.hidden = true;
        this.statusEl.textContent = '';
        this.statusEl.classList.remove('is-searching', 'is-empty');
        return;
      }
      if (state === 'searching') {
        this.statusEl.textContent = this.searchText;
        this.statusEl.hidden = false;
        this.statusEl.classList.add('is-searching');
        this.statusEl.classList.remove('is-empty');
        return;
      }
      if (state === 'empty') {
        this.statusEl.textContent = this.emptyText;
        this.statusEl.hidden = false;
        this.statusEl.classList.add('is-empty');
        this.statusEl.classList.remove('is-searching');
      }
    }

    triggerFilterUpdate() {
      clearTimeout(this.filterTimer);
      this.table.classList.add('is-searching');
      this.setStatus('searching');
      this.filterTimer = setTimeout(() => {
        this.applyFilters();
        this.table.classList.remove('is-searching');
      }, 160);
    }

    setGlobalFilter(value, { silent } = {}) {
      const incoming = value == null ? '' : String(value);
      const normalised = normaliseForSearch(incoming);
      if (this.globalSearchInput && this.globalSearchInput.value !== incoming) {
        this.globalSearchInput.value = incoming;
      }
      if (normalised === this.globalFilter) {
        if (!silent) {
          this.triggerFilterUpdate();
        }
        return;
      }
      this.globalFilter = normalised;
      if (!silent) {
        this.triggerFilterUpdate();
      }
    }

    createToolbar() {
      if (!this.container) {
        return;
      }
      const existing = this.container.previousElementSibling;
      if (existing && existing.classList.contains('table-toolbar')) {
        this.toolbar = existing;
        this.globalSearchInput = existing.querySelector('[data-table-global-search]');
        this.filterToggleButton = existing.querySelector('[data-table-filter-toggle]');
        if (this.filterToggleButton) {
          this.updateFilterToggleState();
        }
        return;
      }
      const toolbar = document.createElement('div');
      toolbar.className = 'table-toolbar';

      const searchGroup = document.createElement('div');
      searchGroup.className = 'table-toolbar__search';

      const searchInput = document.createElement('input');
      searchInput.type = 'search';
      searchInput.setAttribute('data-table-global-search', 'true');
      searchInput.setAttribute('aria-label', this.messages.searchLabel);
      searchInput.placeholder = this.messages.searchPlaceholder;
      searchInput.autocomplete = 'off';
      searchInput.spellcheck = false;
      searchInput.dir = 'auto';
      searchInput.className = 'table-toolbar__search-input';

      searchGroup.appendChild(searchInput);
      toolbar.appendChild(searchGroup);

      if (this.filterRow) {
        const actions = document.createElement('div');
        actions.className = 'table-toolbar__actions';
        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'btn btn-outline table-toolbar__toggle';
        toggle.setAttribute('data-table-filter-toggle', 'true');
        toggle.setAttribute('aria-label', this.messages.toggleLabel);
        toggle.setAttribute('aria-expanded', 'true');
        actions.appendChild(toggle);
        toolbar.appendChild(actions);
        this.filterToggleButton = toggle;
        this.updateFilterToggleState();
      }

      if (this.container.parentElement) {
        this.container.parentElement.insertBefore(toolbar, this.container);
      } else {
        this.container.insertAdjacentElement('beforebegin', toolbar);
      }
      this.toolbar = toolbar;
      this.globalSearchInput = searchInput;
    }

    toggleAdvancedFilters(force) {
      if (!this.filterRow) {
        return;
      }
      if (typeof force === 'boolean') {
        this.filtersVisible = force;
      } else {
        this.filtersVisible = !this.filtersVisible;
      }
      this.filterRow.hidden = !this.filtersVisible;
      this.table.classList.toggle('table-filters-hidden', !this.filtersVisible);
      this.updateFilterToggleState();
    }

    updateFilterToggleState() {
      if (!this.filterToggleButton) {
        return;
      }
      const label = this.filtersVisible ? this.messages.hideFilters : this.messages.showFilters;
      this.filterToggleButton.textContent = label;
      this.filterToggleButton.setAttribute('aria-expanded', this.filtersVisible ? 'true' : 'false');
      this.filterToggleButton.classList.toggle('is-muted', !this.filtersVisible);
    }
  }

  function initTables() {
    const tables = document.querySelectorAll('[data-table="interactive"]');
    tables.forEach((table) => {
      if (table.__interactiveTableInstance) {
        return;
      }
      const instance = new InteractiveTable(table);
      table.__interactiveTableInstance = instance;
      const id = table.getAttribute('id');
      if (id) {
        window.InteractiveTableRegistry.register(id, instance);
      }
    });
  }

  window.InteractiveTableRegistry = window.InteractiveTableRegistry || {
    tables: new Map(),
    register(id, instance) {
      this.tables.set(id, instance);
    },
    get(id) {
      return this.tables.get(id) || null;
    },
  };

  document.addEventListener('DOMContentLoaded', initTables);
})();
