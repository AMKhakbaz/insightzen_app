(function () {
  const locale = document.documentElement.lang || undefined;
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

    return normaliseText(cellValue).toLowerCase().includes(filter.toLowerCase());
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
      this.captureRows();
      this.cacheControls();
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
      });
    }

    bindEvents() {
      this.sortButtons.forEach((button) => {
        button.addEventListener('click', () => this.handleSort(button));
      });
      this.filterInputs.forEach((input) => {
        const handler = () => {
          clearTimeout(this.filterTimer);
          this.table.classList.add('is-searching');
          this.setStatus('searching');
          this.filterTimer = setTimeout(() => {
            this.applyFilters();
            this.table.classList.remove('is-searching');
          }, 160);
        };
        input.addEventListener('input', handler);
        input.addEventListener('change', handler);
      });
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
        });
      });
      return filters;
    }

    matchesFilters(row, filters) {
      if (!filters.length) {
        return true;
      }
      return filters.every((filter) => {
        const cell = row.cells[filter.column];
        const cellValue = getCellContent(cell);
        if (filter.type === 'number') {
          return parseNumericFilter(filter.value, cellValue);
        }
        return normaliseText(cellValue).toLowerCase().includes(filter.value.toLowerCase());
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
        const textA = normaliseText(cellA).toLowerCase();
        const textB = normaliseText(cellB).toLowerCase();
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
      const filtered = this.originalRows.filter(({ row }) => this.matchesFilters(row, filters));
      const sorted = this.sortRows(filtered);
      this.renderRows(sorted);
      this.updateSortIndicators();
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
