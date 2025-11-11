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
      showSearch: 'نمایش جستجو',
      hideSearch: 'پنهان کردن جستجو',
      searchToggleLabel: 'تغییر وضعیت جستجوی جدول',
      advanced: {
        button: 'فیلتر پیشرفته',
        title: 'فیلترهای پیشرفته',
        hint:
          'شرایط دقیق را بسازید و با عملگرهای AND/OR ترکیب کنید. برای جست‌وجوی ساده‌تر همچنان می‌توانید از جستجو و فیلترهای بالای جدول استفاده کنید. برای ذخیره یا پاک کردن حالت‌ها از گزینه‌های زیر کمک بگیرید.',
        logicLabel: 'ردیف زمانی نمایش داده شود که',
        logicAll: 'همه شرایط برقرار باشند (AND)',
        logicAny: 'حداقل یکی از شرایط برقرار باشد (OR)',
        savedInfo: 'یک فیلتر ذخیره‌شده برای این جدول در دسترس است.',
        noSaved: 'هنوز فیلتری ذخیره نشده است.',
        loadSaved: 'بارگذاری فیلتر ذخیره‌شده',
        clearSaved: 'پاک کردن فیلتر ذخیره‌شده',
        addCondition: 'افزودن شرط',
        remember: 'این فیلترها را برای این جدول ذخیره کن',
        apply: 'اعمال فیلترها',
        cancel: 'بستن',
        reset: 'حذف فیلترهای جاری',
        columnLabel: 'ستون',
        operatorLabel: 'عملگر',
        valueLabel: 'مقدار',
        valuePlaceholder: 'مقدار را وارد کنید',
        valuePlaceholderSecond: 'مقدار دوم',
        removeCondition: 'حذف شرط',
        empty: 'هنوز شرطی تعریف نشده است.',
        validationMissingValue: 'برای اعمال فیلتر، مقادیر لازم را تکمیل کنید.',
        loadedSaved: 'فیلتر ذخیره‌شده بارگذاری شد. برای اعمال روی جدول، دکمهٔ اعمال را فشار دهید.',
        clearedSaved: 'فیلتر ذخیره‌شده حذف شد.',
        operators: {
          eq: 'برابر باشد با',
          neq: 'برابر نباشد با',
          contains: 'شامل باشد',
          notContains: 'شامل نباشد',
          startsWith: 'با این مقدار شروع شود',
          endsWith: 'با این مقدار پایان یابد',
          gt: 'بزرگ‌تر باشد از',
          gte: 'بزرگ‌تر یا مساوی باشد با',
          lt: 'کوچک‌تر باشد از',
          lte: 'کوچک‌تر یا مساوی باشد با',
          between: 'بین دو مقدار باشد',
          empty: 'خالی باشد',
          notEmpty: 'خالی نباشد',
        },
      },
    },
    en: {
      searchPlaceholder: 'Search table…',
      searchLabel: 'Search this table',
      showFilters: 'Show filters',
      hideFilters: 'Hide filters',
      toggleLabel: 'Toggle table filters',
      showSearch: 'Show search',
      hideSearch: 'Hide search',
      searchToggleLabel: 'Toggle table search',
      advanced: {
        button: 'Advanced filters',
        title: 'Advanced filters',
        hint:
          'Create precise conditions and combine them with AND/OR. Keep using the quick filters and search above for simple lookups. Use the controls below to save, reload, or clear complex filter sets.',
        logicLabel: 'Show rows when',
        logicAll: 'All conditions are true (AND)',
        logicAny: 'Any condition is true (OR)',
        savedInfo: 'A saved filter set is available for this table.',
        noSaved: 'No saved filters yet.',
        loadSaved: 'Load saved filters',
        clearSaved: 'Clear saved filters',
        addCondition: 'Add condition',
        remember: 'Remember these filters for this table',
        apply: 'Apply filters',
        cancel: 'Close',
        reset: 'Clear current filters',
        columnLabel: 'Column',
        operatorLabel: 'Operator',
        valueLabel: 'Value',
        valuePlaceholder: 'Enter value',
        valuePlaceholderSecond: 'Second value',
        removeCondition: 'Remove condition',
        empty: 'No advanced conditions yet.',
        validationMissingValue: 'Fill in the required values before applying.',
        loadedSaved: 'Saved filters loaded. Press Apply to filter the table.',
        clearedSaved: 'Saved filters cleared.',
        operators: {
          eq: 'Equals',
          neq: 'Does not equal',
          contains: 'Contains',
          notContains: 'Does not contain',
          startsWith: 'Starts with',
          endsWith: 'Ends with',
          gt: 'Greater than',
          gte: 'Greater than or equal to',
          lt: 'Less than',
          lte: 'Less than or equal to',
          between: 'Between',
          empty: 'Is empty',
          notEmpty: 'Is not empty',
        },
      },
    },
  };

  function resolveMessages() {
    const short = documentLang.split('-')[0];
    if (toolbarMessages[short]) {
      return toolbarMessages[short];
    }
    return toolbarMessages.en;
  }

  const advancedOperators = {
    text: ['contains', 'notContains', 'eq', 'neq', 'startsWith', 'endsWith', 'empty', 'notEmpty'],
    number: ['eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'between', 'empty', 'notEmpty'],
  };

  function cloneFilters(filters) {
    return filters.map((filter) => ({
      column: Number(filter.column),
      operator: filter.operator,
      values: Array.isArray(filter.values) ? [...filter.values] : [],
      type: filter.type || 'text',
    }));
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
      this.messages = resolveMessages();
      this.globalFilter = '';
      this.defaultFiltersVisible = table.dataset.filtersVisible === 'true';
      this.filtersVisible = this.defaultFiltersVisible;
      this.searchVisible = table.dataset.searchHidden === 'true' ? false : true;
      this.searchGroup = null;
      this.searchToggleButton = null;
      this.advancedFilters = [];
      this.advancedLogic = 'and';
      this.savedAdvancedFilters = null;
      this.savedFiltersKey = table.id ? `interactiveTableAdvanced:${table.id}` : null;
      this.originalBodyOverflow = null;
      this.statusEl = this.createStatusElement();

      this.captureRows();
      this.cacheControls();
      this.createToolbar();
      this.createAdvancedFilterUI();
      this.bindEvents();
      this.loadSavedAdvancedFilters({ apply: false });
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
        const meta = this.columnMeta.get(column) || {};
        meta.type = type;
        meta.filterable = true;
        this.columnMeta.set(column, meta);
      });

      this.filterInputs.forEach((input) => {
        const column = Number(input.dataset.filterColumn);
        const type = input.dataset.filterType || 'text';
        const meta = this.columnMeta.get(column) || {};
        meta.type = type;
        meta.filterable = true;
        this.columnMeta.set(column, meta);
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
        let initialVisible = this.defaultFiltersVisible;
        if (this.filterRow.hasAttribute('hidden')) {
          initialVisible = false;
        }
        const hasPresetFilters = this.filterInputs.some((input) => normaliseText(input.value));
        if (hasPresetFilters) {
          initialVisible = true;
        }
        if (!initialVisible) {
          this.filterRow.hidden = true;
          this.table.classList.add('table-filters-hidden');
        } else {
          this.filterRow.hidden = false;
          this.table.classList.remove('table-filters-hidden');
        }
        this.filtersVisible = initialVisible;
      } else {
        this.filtersVisible = false;
      }

      const headers = Array.from(this.table.querySelectorAll('thead th'));
      headers.forEach((th, index) => {
        const meta = this.columnMeta.get(index) || {};
        if (!meta.type) {
          meta.type = th.dataset.columnType || 'text';
        }
        if (th.dataset.allowAdvanced === 'true') {
          meta.filterable = true;
        }
        const labelText = th.dataset.columnLabel || normaliseText(th.textContent || '').replace(/\s+/g, ' ').trim();
        meta.label = labelText || `Column ${index + 1}`;
        this.columnMeta.set(index, meta);
      });
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
      if (this.searchToggleButton) {
        this.searchToggleButton.addEventListener('click', () => {
          this.toggleGlobalSearchVisibility();
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

      if (filters.length) {
        const matchesBasic = filters.every((filter) => {
          const cell = row.cells[filter.column];
          const cellValue = getCellContent(cell);
          if (filter.type === 'number') {
            return parseNumericFilter(filter.value, cellValue);
          }
          return normaliseForSearch(cellValue).includes(filter.valueLower);
        });
        if (!matchesBasic) {
          return false;
        }
      }

      if (this.advancedFilters.length) {
        return this.evaluateAdvancedFilters(row);
      }

      return true;
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
      const filtered = this.originalRows.filter(({ row }) => this.matchesRow(row, filters, globalTerm));
      const sorted = this.sortRows(filtered);
      this.renderRows(sorted);
      this.updateSortIndicators();
      const hasAdvanced = this.advancedFilters.length > 0;
      const hasBasic = Boolean(filters.length) || Boolean(globalTerm);
      this.table.classList.toggle('has-active-filters', hasBasic || hasAdvanced);
      if (this.filterToggleButton) {
        this.filterToggleButton.classList.toggle('has-active-filters', Boolean(filters.length));
      }
      this.updateAdvancedFilterButtonState();
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
        this.searchGroup = existing.querySelector('.table-toolbar__search');
        this.searchToggleButton = existing.querySelector('[data-table-search-toggle]');
        this.filterToggleButton = existing.querySelector('[data-table-filter-toggle]');
        this.toolbarActions = existing.querySelector('.table-toolbar__actions');
        if (!this.toolbarActions) {
          this.toolbarActions = document.createElement('div');
          this.toolbarActions.className = 'table-toolbar__actions';
          existing.appendChild(this.toolbarActions);
        }
        if (this.searchGroup) {
          this.searchVisible = !this.searchGroup.hidden;
          this.searchGroup.hidden = !this.searchVisible;
        }
        if (this.searchToggleButton) {
          this.updateSearchToggleState();
        }
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

      this.searchGroup = searchGroup;
      if (!this.searchVisible) {
        this.searchGroup.hidden = true;
      }

      const actions = document.createElement('div');
      actions.className = 'table-toolbar__actions';
      toolbar.appendChild(actions);

      const searchToggle = document.createElement('button');
      searchToggle.type = 'button';
      searchToggle.className = 'btn btn-outline table-toolbar__toggle';
      searchToggle.setAttribute('data-table-search-toggle', 'true');
      searchToggle.setAttribute('aria-label', this.messages.searchToggleLabel || this.messages.searchLabel);
      actions.appendChild(searchToggle);
      this.searchToggleButton = searchToggle;
      this.updateSearchToggleState();

      if (this.filterRow) {
        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'btn btn-outline table-toolbar__toggle';
        toggle.setAttribute('data-table-filter-toggle', 'true');
        toggle.setAttribute('aria-label', this.messages.toggleLabel);
        actions.appendChild(toggle);
        this.filterToggleButton = toggle;
        this.updateFilterToggleState();
      }

      if (this.container.parentElement) {
        this.container.parentElement.insertBefore(toolbar, this.container);
      } else {
        this.container.insertAdjacentElement('beforebegin', toolbar);
      }
      this.toolbar = toolbar;
      this.toolbarActions = actions;
      this.globalSearchInput = searchInput;
    }

    toggleGlobalSearchVisibility(force) {
      if (!this.searchGroup) {
        return;
      }
      if (typeof force === 'boolean') {
        this.searchVisible = force;
      } else {
        this.searchVisible = !this.searchVisible;
      }
      this.searchGroup.hidden = !this.searchVisible;
      if (!this.searchVisible) {
        if (this.globalSearchInput) {
          this.globalSearchInput.value = '';
        }
        this.setGlobalFilter('', { silent: true });
        this.applyFilters({ resetSort: false });
      } else if (this.globalSearchInput) {
        const current = this.globalSearchInput.value;
        this.setGlobalFilter(current, { silent: true });
        this.applyFilters({ resetSort: false });
      }
      this.updateSearchToggleState();
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
      this.filterToggleButton.classList.toggle('is-active', this.filtersVisible);
      this.filterToggleButton.classList.toggle('is-inactive', !this.filtersVisible);
    }

    updateSearchToggleState() {
      if (!this.searchToggleButton) {
        return;
      }
      const label = this.searchVisible ? this.messages.hideSearch : this.messages.showSearch;
      this.searchToggleButton.textContent = label;
      this.searchToggleButton.setAttribute('aria-pressed', this.searchVisible ? 'true' : 'false');
      this.searchToggleButton.classList.toggle('is-active', this.searchVisible);
      this.searchToggleButton.classList.toggle('is-inactive', !this.searchVisible);
    }

    getAdvancedFilterableColumns() {
      const entries = [];
      this.columnMeta.forEach((meta, column) => {
        if (!meta || !meta.filterable) {
          return;
        }
        entries.push({
          column,
          label: meta.label || `Column ${column + 1}`,
          type: meta.type || 'text',
        });
      });
      return entries.sort((a, b) => a.column - b.column);
    }

    createAdvancedFilterUI() {
      const columns = this.getAdvancedFilterableColumns();
      if (!this.toolbar || !columns.length) {
        this.supportsAdvancedFilters = false;
        return;
      }
      this.supportsAdvancedFilters = true;
      if (!this.toolbarActions) {
        this.toolbarActions = document.createElement('div');
        this.toolbarActions.className = 'table-toolbar__actions';
        this.toolbar.appendChild(this.toolbarActions);
      }

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-outline table-toolbar__advanced-btn';
      button.textContent = this.messages.advanced.button;
      button.setAttribute('aria-haspopup', 'dialog');
      button.setAttribute('aria-expanded', 'false');
      this.toolbarActions.appendChild(button);
      this.advancedFilterButton = button;

      const template = document.getElementById('table-advanced-filter-template');
      if (!template) {
        return;
      }
      const instance = template.content.firstElementChild.cloneNode(true);
      instance.hidden = true;
      document.body.appendChild(instance);

      this.advancedPanel = instance;
      this.advancedConditionContainer = instance.querySelector('[data-advanced-conditions]');
      this.advancedLogicSelect = instance.querySelector('[data-advanced-logic]');
      this.advancedAddButton = instance.querySelector('[data-advanced-add]');
      this.advancedApplyButton = instance.querySelector('[data-advanced-apply]');
      this.advancedCancelButton = instance.querySelector('[data-advanced-cancel]');
      this.advancedResetButton = instance.querySelector('[data-advanced-reset]');
      this.advancedRememberCheckbox = instance.querySelector('[data-advanced-remember]');
      this.advancedStatus = instance.querySelector('[data-advanced-status]');
      this.advancedSavedSection = instance.querySelector('[data-advanced-saved]');
      this.advancedSavedText = instance.querySelector('.table-advanced-filter__saved-text');
      this.advancedLoadButton = instance.querySelector('[data-advanced-load]');
      this.advancedClearSavedButton = instance.querySelector('[data-advanced-clear-saved]');

      this.populateAdvancedText();
      this.populateLogicOptions();

      button.addEventListener('click', () => this.openAdvancedFilter());
      this.advancedAddButton.addEventListener('click', () => this.addAdvancedCondition());
      this.advancedApplyButton.addEventListener('click', () => this.handleAdvancedApply());
      this.advancedCancelButton.addEventListener('click', () => this.closeAdvancedFilter());
      this.advancedResetButton.addEventListener('click', () => this.handleAdvancedReset());
      instance.addEventListener('click', (event) => {
        if (event.target.dataset.advancedDismiss === 'true') {
          this.closeAdvancedFilter();
        }
      });
      this.handleAdvancedKeydown = this.handleAdvancedKeydown.bind(this);
      if (this.advancedLoadButton) {
        this.advancedLoadButton.addEventListener('click', () => this.handleAdvancedLoadSaved());
      }
      if (this.advancedClearSavedButton) {
        this.advancedClearSavedButton.addEventListener('click', () => this.handleAdvancedClearSaved());
      }
      this.updateSavedUI();
    }

    populateAdvancedText() {
      if (!this.advancedPanel) {
        return;
      }
      const mapping = {
        title: this.messages.advanced.title,
        hint: this.messages.advanced.hint,
        logicLabel: this.messages.advanced.logicLabel,
        savedInfo: this.messages.advanced.savedInfo,
        remember: this.messages.advanced.remember,
      };
      Object.entries(mapping).forEach(([key, value]) => {
        const el = this.advancedPanel.querySelector(`[data-i18n="${key}"]`);
        if (el) {
          el.textContent = value;
        }
      });
      if (this.advancedAddButton) {
        this.advancedAddButton.textContent = this.messages.advanced.addCondition;
      }
      if (this.advancedApplyButton) {
        this.advancedApplyButton.textContent = this.messages.advanced.apply;
      }
      if (this.advancedCancelButton) {
        this.advancedCancelButton.textContent = this.messages.advanced.cancel;
      }
      if (this.advancedResetButton) {
        this.advancedResetButton.textContent = this.messages.advanced.reset;
      }
      if (this.advancedLoadButton) {
        this.advancedLoadButton.textContent = this.messages.advanced.loadSaved;
      }
      if (this.advancedClearSavedButton) {
        this.advancedClearSavedButton.textContent = this.messages.advanced.clearSaved;
      }
    }

    populateLogicOptions() {
      if (!this.advancedLogicSelect) {
        return;
      }
      this.advancedLogicSelect.innerHTML = '';
      const options = [
        { value: 'and', label: this.messages.advanced.logicAll },
        { value: 'or', label: this.messages.advanced.logicAny },
      ];
      options.forEach((option) => {
        const opt = document.createElement('option');
        opt.value = option.value;
        opt.textContent = option.label;
        this.advancedLogicSelect.appendChild(opt);
      });
      this.advancedLogicSelect.value = this.advancedLogic;
    }

    openAdvancedFilter() {
      if (!this.advancedPanel) {
        return;
      }
      this.renderAdvancedConditions();
      this.populateLogicOptions();
      if (this.advancedRememberCheckbox) {
        this.advancedRememberCheckbox.checked = Boolean(this.savedAdvancedFilters);
      }
      this.setAdvancedStatus('', 'none');
      this.advancedPanel.hidden = false;
      this.advancedPanel.dataset.open = 'true';
      this.advancedFilterButton.setAttribute('aria-expanded', 'true');
      this.previousActiveElement = document.activeElement;
      this.advancedPanel.addEventListener('keydown', this.handleAdvancedKeydown);
      this.originalBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      const firstInput = this.advancedPanel.querySelector('select, input, button');
      if (firstInput) {
        firstInput.focus();
      }
    }

    closeAdvancedFilter() {
      if (!this.advancedPanel || this.advancedPanel.hidden) {
        return;
      }
      this.advancedPanel.hidden = true;
      delete this.advancedPanel.dataset.open;
      this.advancedFilterButton.setAttribute('aria-expanded', 'false');
      this.advancedPanel.removeEventListener('keydown', this.handleAdvancedKeydown);
      document.body.style.overflow = this.originalBodyOverflow || '';
      this.originalBodyOverflow = null;
      if (this.previousActiveElement && typeof this.previousActiveElement.focus === 'function') {
        this.previousActiveElement.focus();
      }
    }

    handleAdvancedKeydown(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        this.closeAdvancedFilter();
      }
    }

    renderAdvancedConditions() {
      if (!this.advancedConditionContainer) {
        return;
      }
      this.advancedConditionContainer.innerHTML = '';
      if (!this.advancedFilters.length) {
        const empty = document.createElement('p');
        empty.className = 'table-advanced-filter__empty';
        empty.textContent = this.messages.advanced.empty;
        this.advancedConditionContainer.appendChild(empty);
        return;
      }
      this.advancedFilters.forEach((condition) => {
        this.advancedConditionContainer.appendChild(this.createConditionRow(condition));
      });
    }

    addAdvancedCondition(condition) {
      if (!this.advancedConditionContainer) {
        return;
      }
      const columns = this.getAdvancedFilterableColumns();
      if (!columns.length) {
        return;
      }
      if (!this.advancedFilters.length && !condition) {
        this.advancedConditionContainer.innerHTML = '';
      }
      const baseColumn = condition ? condition.column : columns[0].column;
      const meta = this.columnMeta.get(baseColumn) || { type: 'text' };
      const operatorList = advancedOperators[meta.type] || advancedOperators.text;
      const baseOperator = condition && condition.operator ? condition.operator : operatorList[0];
      const values = condition && condition.values ? condition.values : [];
      const row = this.createConditionRow({
        column: baseColumn,
        operator: baseOperator,
        values,
        type: meta.type || 'text',
      });
      this.advancedConditionContainer.appendChild(row);
      const focusTarget = row.querySelector('select, input');
      if (focusTarget) {
        focusTarget.focus();
      }
    }

    createConditionRow(condition) {
      const columns = this.getAdvancedFilterableColumns();
      const row = document.createElement('div');
      row.className = 'table-advanced-filter__condition';
      if (!columns.length) {
        return row;
      }
      const targetColumn = columns.find((col) => col.column === condition.column) || columns[0];
      const columnSelect = document.createElement('select');
      columnSelect.setAttribute('aria-label', this.messages.advanced.columnLabel);
      columnSelect.dataset.advancedColumn = 'true';
      columns.forEach((col) => {
        const option = document.createElement('option');
        option.value = String(col.column);
        option.textContent = col.label;
        columnSelect.appendChild(option);
      });
      columnSelect.value = String(targetColumn.column);

      const operatorSelect = document.createElement('select');
      operatorSelect.setAttribute('aria-label', this.messages.advanced.operatorLabel);
      operatorSelect.dataset.advancedOperator = 'true';

      const valuesWrap = document.createElement('div');
      valuesWrap.className = 'table-advanced-filter__values';

      const removeButton = document.createElement('button');
      removeButton.type = 'button';
      removeButton.className = 'table-advanced-filter__condition-remove';
      removeButton.setAttribute('aria-label', this.messages.advanced.removeCondition);
      removeButton.innerHTML = '&times;';

      row.appendChild(columnSelect);
      row.appendChild(operatorSelect);
      row.appendChild(valuesWrap);
      row.appendChild(removeButton);

      const applyColumn = (columnIndex, preferredOperator, presetValues) => {
        const meta = this.columnMeta.get(columnIndex) || { type: 'text' };
        row.dataset.column = String(columnIndex);
        row.dataset.type = meta.type || 'text';
        this.populateOperatorOptions(row, operatorSelect, meta.type || 'text', preferredOperator);
        this.populateValueInputs(row, valuesWrap, operatorSelect.value, presetValues || [], meta.type || 'text');
        this.clearConditionErrors(row);
      };

      columnSelect.addEventListener('change', () => {
        const selected = Number(columnSelect.value);
        const meta = this.columnMeta.get(selected) || { type: 'text' };
        row.dataset.column = String(selected);
        row.dataset.type = meta.type || 'text';
        this.populateOperatorOptions(row, operatorSelect, meta.type || 'text');
        this.populateValueInputs(row, valuesWrap, operatorSelect.value, [], meta.type || 'text');
        this.clearConditionErrors(row);
      });

      operatorSelect.addEventListener('change', () => {
        const type = row.dataset.type || 'text';
        this.populateValueInputs(row, valuesWrap, operatorSelect.value, [], type);
        this.clearConditionErrors(row);
      });

      removeButton.addEventListener('click', () => {
        row.remove();
        if (!this.advancedConditionContainer.querySelector('.table-advanced-filter__condition')) {
          this.advancedFilters = [];
          this.renderAdvancedConditions();
        }
      });

      const presetOperator = condition.operator;
      const presetValues = condition.values || [];
      applyColumn(targetColumn.column, presetOperator, presetValues);
      operatorSelect.value = row.dataset.operator || operatorSelect.value;
      this.populateValueInputs(row, valuesWrap, operatorSelect.value, presetValues, row.dataset.type || 'text');
      return row;
    }

    populateOperatorOptions(row, select, type, preferred) {
      const available = advancedOperators[type] || advancedOperators.text;
      select.innerHTML = '';
      available.forEach((operator) => {
        const option = document.createElement('option');
        option.value = operator;
        option.textContent = this.messages.advanced.operators[operator] || operator;
        select.appendChild(option);
      });
      if (preferred && available.includes(preferred)) {
        select.value = preferred;
      }
      row.dataset.operator = select.value;
    }

    populateValueInputs(row, container, operator, values, type) {
      container.innerHTML = '';
      row.dataset.operator = operator;
      const requiresValue = !['empty', 'notEmpty'].includes(operator);
      if (!requiresValue) {
        return;
      }

      const createInput = (placeholderText, existingValue) => {
        const input = document.createElement('input');
        input.type = 'text';
        input.dir = 'auto';
        input.dataset.advancedValue = 'true';
        input.placeholder = placeholderText;
        input.value = existingValue || '';
        if (type === 'number') {
          input.inputMode = 'decimal';
        }
        input.addEventListener('input', () => this.clearConditionErrors(row));
        return input;
      };

      if (operator === 'between') {
        const first = createInput(this.messages.advanced.valuePlaceholder, values[0] || '');
        const second = createInput(this.messages.advanced.valuePlaceholderSecond, values[1] || '');
        container.appendChild(first);
        container.appendChild(second);
      } else {
        const input = createInput(this.messages.advanced.valuePlaceholder, values[0] || '');
        container.appendChild(input);
      }
    }

    clearConditionErrors(row) {
      const inputs = row.querySelectorAll('input, select');
      inputs.forEach((input) => input.classList.remove('is-invalid'));
      if (this.advancedStatus) {
        this.advancedStatus.textContent = '';
        this.advancedStatus.classList.remove('is-info', 'is-success');
      }
    }

    setAdvancedStatus(message, variant = 'none') {
      if (!this.advancedStatus) {
        return;
      }
      this.advancedStatus.textContent = message || '';
      this.advancedStatus.classList.remove('is-info', 'is-success');
      if (!message) {
        return;
      }
      if (variant === 'info') {
        this.advancedStatus.classList.add('is-info');
      } else if (variant === 'success') {
        this.advancedStatus.classList.add('is-success');
      }
    }

    collectConditionsFromUI() {
      if (!this.advancedConditionContainer) {
        return { filters: [], logic: 'and', hasError: false };
      }
      const rows = Array.from(
        this.advancedConditionContainer.querySelectorAll('.table-advanced-filter__condition')
      );
      const filters = [];
      let hasError = false;
      rows.forEach((row) => {
        const column = Number(row.dataset.column);
        const type = row.dataset.type || 'text';
        const operator = row.dataset.operator || (row.querySelector('[data-advanced-operator]')?.value || '');
        const valueInputs = Array.from(row.querySelectorAll('[data-advanced-value]'));
        const values = valueInputs.map((input) => normaliseText(input.value));
        valueInputs.forEach((input) => input.classList.remove('is-invalid'));
        if (['empty', 'notEmpty'].includes(operator)) {
          filters.push({ column, type, operator, values: [] });
          return;
        }
        if (operator === 'between') {
          if (!values[0] || !values[1]) {
            hasError = true;
            valueInputs.forEach((input) => input.classList.add('is-invalid'));
            return;
          }
          filters.push({ column, type, operator, values: [values[0], values[1]] });
          return;
        }
        if (!values[0]) {
          hasError = true;
          if (valueInputs[0]) {
            valueInputs[0].classList.add('is-invalid');
          }
          return;
        }
        filters.push({ column, type, operator, values: [values[0]] });
      });
      const logicValue = this.advancedLogicSelect ? this.advancedLogicSelect.value : 'and';
      return { filters, logic: logicValue === 'or' ? 'or' : 'and', hasError };
    }

    handleAdvancedApply() {
      const { filters, logic, hasError } = this.collectConditionsFromUI();
      if (hasError) {
        this.setAdvancedStatus(this.messages.advanced.validationMissingValue, 'error');
        return;
      }
      this.advancedFilters = filters;
      this.advancedLogic = logic;
      this.closeAdvancedFilter();
      this.applyFilters();
      const remember = this.advancedRememberCheckbox && this.advancedRememberCheckbox.checked;
      this.persistAdvancedFilters({ remember, clearWhenEmpty: true });
      this.updateAdvancedFilterButtonState();
    }

    handleAdvancedReset() {
      this.advancedFilters = [];
      this.advancedLogic = 'and';
      if (this.advancedLogicSelect) {
        this.advancedLogicSelect.value = 'and';
      }
      this.renderAdvancedConditions();
      this.setAdvancedStatus('', 'none');
      const remember = this.advancedRememberCheckbox && this.advancedRememberCheckbox.checked;
      this.persistAdvancedFilters({ remember, clearWhenEmpty: true });
      this.applyFilters();
      this.updateAdvancedFilterButtonState();
    }

    handleAdvancedLoadSaved() {
      if (!this.savedAdvancedFilters || !this.savedAdvancedFilters.filters.length) {
        this.setAdvancedStatus(this.messages.advanced.noSaved, 'info');
        return;
      }
      this.advancedFilters = cloneFilters(this.savedAdvancedFilters.filters);
      this.advancedLogic = this.savedAdvancedFilters.logic;
      this.renderAdvancedConditions();
      this.populateLogicOptions();
      this.setAdvancedStatus(this.messages.advanced.loadedSaved, 'success');
    }

    handleAdvancedClearSaved() {
      this.persistAdvancedFilters({ clear: true });
      this.setAdvancedStatus(this.messages.advanced.clearedSaved, 'info');
    }

    updateAdvancedFilterButtonState() {
      if (!this.advancedFilterButton) {
        return;
      }
      const active = this.advancedFilters.length > 0;
      this.advancedFilterButton.classList.toggle('has-active-filters', active);
      this.advancedFilterButton.setAttribute('aria-pressed', active ? 'true' : 'false');
    }

    evaluateAdvancedFilters(row) {
      if (!this.advancedFilters.length) {
        return true;
      }
      const results = this.advancedFilters.map((condition) =>
        this.evaluateAdvancedCondition(row, condition)
      );
      if (this.advancedLogic === 'or') {
        return results.some(Boolean);
      }
      return results.every(Boolean);
    }

    evaluateAdvancedCondition(row, condition) {
      const cell = row.cells[condition.column];
      const value = getCellContent(cell);
      if (condition.operator === 'empty') {
        return normaliseText(value) === '';
      }
      if (condition.operator === 'notEmpty') {
        return normaliseText(value) !== '';
      }
      if ((condition.type || 'text') === 'number') {
        return this.evaluateNumberCondition(value, condition);
      }
      return this.evaluateTextCondition(value, condition);
    }

    evaluateTextCondition(value, condition) {
      const target = normaliseForSearch(value);
      const query = normaliseForSearch(condition.values[0] || '');
      switch (condition.operator) {
        case 'eq':
          return target === query;
        case 'neq':
          return target !== query;
        case 'contains':
          return target.includes(query);
        case 'notContains':
          return !target.includes(query);
        case 'startsWith':
          return target.startsWith(query);
        case 'endsWith':
          return target.endsWith(query);
        default:
          return true;
      }
    }

    evaluateNumberCondition(value, condition) {
      const numericValue = extractNumeric(value);
      if (Number.isNaN(numericValue)) {
        return false;
      }
      const toNumber = (input) => extractNumeric(input);
      switch (condition.operator) {
        case 'eq':
          return numericValue === toNumber(condition.values[0]);
        case 'neq':
          return numericValue !== toNumber(condition.values[0]);
        case 'gt':
          return numericValue > toNumber(condition.values[0]);
        case 'gte':
          return numericValue >= toNumber(condition.values[0]);
        case 'lt':
          return numericValue < toNumber(condition.values[0]);
        case 'lte':
          return numericValue <= toNumber(condition.values[0]);
        case 'between': {
          const min = toNumber(condition.values[0]);
          const max = toNumber(condition.values[1]);
          if (Number.isNaN(min) || Number.isNaN(max)) {
            return false;
          }
          const lower = Math.min(min, max);
          const upper = Math.max(min, max);
          return numericValue >= lower && numericValue <= upper;
        }
        default:
          return true;
      }
    }

    persistAdvancedFilters({ remember = false, clearWhenEmpty = false, clear = false } = {}) {
      if (!this.savedFiltersKey || typeof window === 'undefined' || !window.localStorage) {
        return;
      }
      try {
        if (clear) {
          window.localStorage.removeItem(this.savedFiltersKey);
          this.savedAdvancedFilters = null;
          this.updateSavedUI();
          return;
        }
        if (remember && this.advancedFilters.length) {
          const payload = {
            logic: this.advancedLogic,
            filters: cloneFilters(this.advancedFilters),
          };
          window.localStorage.setItem(this.savedFiltersKey, JSON.stringify(payload));
          this.savedAdvancedFilters = { logic: payload.logic, filters: cloneFilters(this.advancedFilters) };
          this.updateSavedUI();
          return;
        }
        if (remember && !this.advancedFilters.length && clearWhenEmpty) {
          window.localStorage.removeItem(this.savedFiltersKey);
          this.savedAdvancedFilters = null;
          this.updateSavedUI();
          return;
        }
        this.updateSavedUI();
      } catch (error) {
        // Ignore storage errors
      }
    }

    loadSavedAdvancedFilters({ apply = false } = {}) {
      if (!this.savedFiltersKey || typeof window === 'undefined' || !window.localStorage) {
        return;
      }
      try {
        const stored = window.localStorage.getItem(this.savedFiltersKey);
        if (!stored) {
          this.savedAdvancedFilters = null;
          this.updateSavedUI();
          return;
        }
        const parsed = JSON.parse(stored);
        if (!parsed || !Array.isArray(parsed.filters)) {
          window.localStorage.removeItem(this.savedFiltersKey);
          this.savedAdvancedFilters = null;
          this.updateSavedUI();
          return;
        }
        const validFilters = parsed.filters
          .map((item) => ({
            column: Number(item.column),
            operator: item.operator,
            values: Array.isArray(item.values) ? item.values : [],
            type: item.type || (this.columnMeta.get(Number(item.column))?.type || 'text'),
          }))
          .filter((item) => this.columnMeta.has(item.column));
        if (!validFilters.length) {
          this.savedAdvancedFilters = null;
          this.updateSavedUI();
          return;
        }
        this.savedAdvancedFilters = {
          logic: parsed.logic === 'or' ? 'or' : 'and',
          filters: cloneFilters(validFilters),
        };
        this.advancedFilters = cloneFilters(validFilters);
        this.advancedLogic = this.savedAdvancedFilters.logic;
        this.updateSavedUI();
        this.updateAdvancedFilterButtonState();
        if (apply) {
          this.applyFilters();
        }
      } catch (error) {
        // Ignore storage errors
      }
    }

    updateSavedUI() {
      if (!this.advancedSavedSection) {
        return;
      }
      const hasSaved = Boolean(
        this.savedAdvancedFilters && this.savedAdvancedFilters.filters && this.savedAdvancedFilters.filters.length
      );
      this.advancedSavedSection.hidden = false;
      if (this.advancedSavedText) {
        this.advancedSavedText.textContent = hasSaved
          ? this.messages.advanced.savedInfo
          : this.messages.advanced.noSaved;
      }
      if (this.advancedLoadButton) {
        this.advancedLoadButton.disabled = !hasSaved;
      }
      if (this.advancedClearSavedButton) {
        this.advancedClearSavedButton.disabled = !hasSaved;
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
