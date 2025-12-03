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

  const STORAGE_VERSION = 1;

  function getCsrfToken() {
    if (typeof window === 'undefined') {
      return null;
    }
    if (typeof window.getCookie === 'function') {
      return window.getCookie('csrftoken');
    }
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : null;
  }

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
      exportLabel: 'خروجی',
      exportCSV: 'دریافت CSV',
      exportExcel: 'دریافت Excel',
      exporting: 'در حال آماده‌سازی فایل…',
      exportReady: 'فایل آماده دانلود است.',
      exportError: 'دریافت خروجی ممکن نشد.',
      advanced: {
        button: 'فیلتر پیشرفته',
        title: 'فیلترهای پیشرفته',
        hint:
          'شرایط دقیق را بسازید و با عملگرهای AND/OR ترکیب کنید. برای جست‌وجوی ساده‌تر همچنان می‌توانید از جستجو و فیلترهای بالای جدول استفاده کنید. برای ذخیره مجموعه فیلترها نام یکتا انتخاب کنید و در صورت نیاز آن را بارگذاری یا حذف نمایید.',
        logicLabel: 'ردیف زمانی نمایش داده شود که',
        logicAll: 'همه شرایط برقرار باشند (AND)',
        logicAny: 'حداقل یکی از شرایط برقرار باشد (OR)',
        savedLabel: 'فیلترهای ذخیره‌شده',
        savedPlaceholder: 'فیلتر ذخیره‌شده را انتخاب کنید',
        noSaved: 'هنوز فیلتری برای این جدول ذخیره نشده است.',
        loadSaved: 'بارگذاری فیلتر',
        deleteSaved: 'حذف فیلتر',
        saveLabel: 'ذخیره فیلترهای جاری با نام',
        savePlaceholder: 'نام فیلتر',
        saveButton: 'ذخیره فیلتر',
        saveHint: 'از نام‌های یکتا استفاده کنید تا بعداً بتوانید فیلترها را تشخیص دهید.',
        saveRequiresFilters: 'برای ذخیرهٔ فیلتر باید حداقل یک شرط فعال داشته باشید.',
        saveSuccess: 'فیلتر ذخیره شد. برای اعمال آن، دکمهٔ اعمال را فشار دهید.',
        deleteSuccess: 'فیلتر حذف شد.',
        saveError: 'ذخیره فیلتر انجام نشد.',
        deleteError: 'حذف فیلتر انجام نشد.',
        addCondition: 'افزودن شرط',
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
      exportLabel: 'Export',
      exportCSV: 'Download CSV',
      exportExcel: 'Download Excel',
      exporting: 'Preparing export…',
      exportReady: 'Download ready.',
      exportError: 'Unable to export data.',
      advanced: {
        button: 'Advanced filters',
        title: 'Advanced filters',
        hint:
          'Create precise conditions and combine them with AND/OR. Keep using the quick filters and search above for simple lookups. Give your presets unique names so you can reload or remove them later.',
        logicLabel: 'Show rows when',
        logicAll: 'All conditions are true (AND)',
        logicAny: 'Any condition is true (OR)',
        savedLabel: 'Saved presets',
        savedPlaceholder: 'Select a saved preset',
        noSaved: 'No presets saved for this table yet.',
        loadSaved: 'Load preset',
        deleteSaved: 'Delete preset',
        saveLabel: 'Save current filters as',
        savePlaceholder: 'Preset name',
        saveButton: 'Save preset',
        saveHint: 'Use unique names so you can recognise presets later.',
        saveRequiresFilters: 'Define at least one condition before saving a preset.',
        saveSuccess: 'Preset saved. Press Apply to filter the table.',
        deleteSuccess: 'Preset removed.',
        saveError: 'Failed to save filter.',
        deleteError: 'Failed to delete filter.',
        addCondition: 'Add condition',
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
        loadedSaved: 'Saved preset loaded. Press Apply to filter the table.',
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
      this.tableId = table.getAttribute('id') || table.dataset.filterId || null;
      this.filterContext = table.dataset.filterContext || '';
      this.filterEndpoint = this.tableId
        ? `/api/table-filters/${encodeURIComponent(this.tableId)}/`
        : null;
      this.savedPresets = [];
      this.currentPresetName = null;
      this.savedFiltersKey = this.tableId ? `interactiveTablePresets:${this.tableId}` : null;
      this.originalBodyOverflow = null;
      this.statusEl = this.createStatusElement();
      this.exportEndpoint = table.dataset.exportEndpoint || null;
      this.exportFilename = table.dataset.exportFilename || this.filterContext || this.tableId || 'table-data';
      this.exportParams = this.collectExportParams();
      this.externalExportButtons = table.dataset.exportPlacement === 'header';
      this.exportStatusTarget = table.dataset.exportStatusTarget || null;
      this.exportButtons = [];
      this.exportGroup = null;
      this.exportStatus = null;
      if (this.exportStatusTarget) {
        this.exportStatus = document.getElementById(this.exportStatusTarget) || null;
      }

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

    collectExportParams() {
      const params = {};
      const dataset = this.table.dataset || {};
      Object.keys(dataset).forEach((key) => {
        if (!key.startsWith('exportParam')) {
          return;
        }
        const suffix = key.slice('exportParam'.length);
        if (!suffix) {
          return;
        }
        const normalised = suffix.charAt(0).toLowerCase() + suffix.slice(1);
        params[normalised] = dataset[key];
      });
      return params;
    }

    updateExportParams(newParams, options = {}) {
      if (!newParams || typeof newParams !== 'object') {
        return;
      }
      const base = options.replace ? {} : { ...this.exportParams };
      Object.keys(newParams).forEach((key) => {
        const value = newParams[key];
        if (value === undefined || value === null || value === '') {
          delete base[key];
        } else {
          base[key] = value;
        }
      });
      this.exportParams = base;
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
        this.createExportControls();
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
      this.createExportControls();
    }

    createExportControls() {
      if (!this.toolbarActions || !this.exportEndpoint || this.exportGroup || this.externalExportButtons) {
        return;
      }
      const group = document.createElement('div');
      group.className = 'table-toolbar__export';

      const label = document.createElement('span');
      label.className = 'table-toolbar__export-label';
      label.textContent = this.messages.exportLabel || 'Export';
      group.appendChild(label);

      const excelButton = document.createElement('button');
      excelButton.type = 'button';
      excelButton.className = 'btn btn-outline table-toolbar__export-btn';
      excelButton.textContent = this.messages.exportExcel || 'Excel';
      excelButton.addEventListener('click', () => this.handleExport('xlsx'));
      group.appendChild(excelButton);

      const csvButton = document.createElement('button');
      csvButton.type = 'button';
      csvButton.className = 'btn btn-outline table-toolbar__export-btn';
      csvButton.textContent = this.messages.exportCSV || 'CSV';
      csvButton.addEventListener('click', () => this.handleExport('csv'));
      group.appendChild(csvButton);

      const status = document.createElement('span');
      status.className = 'table-toolbar__export-status';
      status.setAttribute('role', 'status');
      status.setAttribute('aria-live', 'polite');
      group.appendChild(status);

      this.toolbarActions.appendChild(group);
      this.exportGroup = group;
      this.exportButtons = [excelButton, csvButton];
      this.exportStatus = status;
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

    buildExportPayload(format) {
      const columnFilters = this.getFilters().map((filter) => ({
        column: filter.column,
        type: filter.type,
        value: filter.value,
        valueLower: filter.valueLower,
      }));
      const payload = {
        context: this.filterContext,
        format,
        params: { ...this.exportParams },
        filters: {
          global: this.globalSearchInput ? this.globalSearchInput.value : this.globalFilter || '',
          columnFilters,
          sort:
            this.sortColumn == null
              ? null
              : { column: this.sortColumn, direction: this.sortDirection },
        },
      };
      if (this.advancedFilters.length) {
        payload.filters.advanced = { logic: this.advancedLogic, filters: cloneFilters(this.advancedFilters) };
      }
      return payload;
    }

    setExportBusy(isBusy) {
      if (!this.exportButtons.length) {
        return;
      }
      this.exportButtons.forEach((button) => {
        button.disabled = Boolean(isBusy);
        button.classList.toggle('is-loading', Boolean(isBusy));
      });
      if (isBusy) {
        this.setExportStatus(this.messages.exporting || 'Preparing export…', 'info');
      }
    }

    setExportStatus(message, tone = 'info') {
      if (!this.exportStatus) {
        return;
      }
      this.exportStatus.textContent = message || '';
      this.exportStatus.classList.remove('is-success', 'is-error', 'is-info');
      if (!message) {
        return;
      }
      const className = tone === 'success' ? 'is-success' : tone === 'error' ? 'is-error' : 'is-info';
      this.exportStatus.classList.add(className);
    }

    extractFilename(response) {
      const disposition = response.headers ? response.headers.get('Content-Disposition') : null;
      if (!disposition) {
        return null;
      }
      const match = disposition.match(/filename="?([^";]+)"?/i);
      return match ? match[1] : null;
    }

    triggerDownload(blob, filename) {
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    }

    async handleExport(format) {
      if (!this.exportEndpoint) {
        return;
      }
      const payload = this.buildExportPayload(format);
      const headers = {
        'Content-Type': 'application/json',
        Accept: 'application/octet-stream, application/json',
      };
      const csrf = getCsrfToken();
      if (csrf) {
        headers['X-CSRFToken'] = csrf;
      }
      this.setExportBusy(true);
      try {
        const response = await fetch(this.exportEndpoint, {
          method: 'POST',
          headers,
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          let errorMessage = this.messages.exportError || 'Unable to export data.';
          const contentType = response.headers.get('Content-Type') || '';
          if (contentType.includes('application/json')) {
            try {
              const data = await response.json();
              if (data && data.error) {
                errorMessage = data.error;
              }
            } catch (error) {
              // ignore JSON parsing errors
            }
          }
          throw new Error(errorMessage);
        }
        const blob = await response.blob();
        const filename =
          this.extractFilename(response) ||
          `${this.exportFilename}.${format === 'xlsx' ? 'xlsx' : 'csv'}`;
        this.triggerDownload(blob, filename);
        this.setExportStatus(this.messages.exportReady || 'Download ready.', 'success');
      } catch (error) {
        const fallback = this.messages.exportError || 'Unable to export data.';
        const message = error && error.message ? error.message : fallback;
        this.setExportStatus(message, 'error');
      } finally {
        this.setExportBusy(false);
      }
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
      this.advancedStatus = instance.querySelector('[data-advanced-status]');
      this.advancedPresetsContainer = instance.querySelector('[data-advanced-presets]');
      this.advancedPresetSelect = instance.querySelector('[data-advanced-preset-select]');
      this.advancedLoadButton = instance.querySelector('[data-advanced-load]');
      this.advancedDeleteButton = instance.querySelector('[data-advanced-delete]');
      this.advancedSaveSection = instance.querySelector('[data-advanced-save]');
      this.advancedSaveInput = instance.querySelector('[data-advanced-save-name]');
      this.advancedSaveButton = instance.querySelector('[data-advanced-save-button]');
      this.advancedSaveHint = instance.querySelector('.table-advanced-filter__save-hint');

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
      if (this.advancedPresetSelect) {
        this.advancedPresetSelect.addEventListener('change', () => this.updatePresetButtonState());
      }
      if (this.advancedLoadButton) {
        this.advancedLoadButton.addEventListener('click', () => this.handleAdvancedLoadSaved());
      }
      if (this.advancedDeleteButton) {
        this.advancedDeleteButton.addEventListener('click', () => this.handleAdvancedDeleteSaved());
      }
      if (this.advancedSaveButton) {
        this.advancedSaveButton.addEventListener('click', () => this.handleAdvancedSave());
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
        savedLabel: this.messages.advanced.savedLabel,
        saveLabel: this.messages.advanced.saveLabel,
        saveHint: this.messages.advanced.saveHint,
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
      if (this.advancedDeleteButton) {
        this.advancedDeleteButton.textContent = this.messages.advanced.deleteSaved;
      }
      if (this.advancedSaveButton) {
        this.advancedSaveButton.textContent = this.messages.advanced.saveButton;
      }
      if (this.advancedSaveInput) {
        this.advancedSaveInput.placeholder = this.messages.advanced.savePlaceholder;
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
      this.setAdvancedStatus('', 'none');
      if (this.advancedSaveInput) {
        this.advancedSaveInput.value = this.currentPresetName || '';
      }
      if (this.advancedPresetSelect) {
        this.advancedPresetSelect.value = this.currentPresetName || '';
      }
      this.updatePresetButtonState();
      this.refreshAdvancedPresets({ silent: true });
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
      this.persistAdvancedFilters({ logic, filters });
      this.updateAdvancedFilterButtonState();
    }

    handleAdvancedReset() {
      this.advancedFilters = [];
      this.advancedLogic = 'and';
      if (this.advancedLogicSelect) {
        this.advancedLogicSelect.value = 'and';
      }
      if (this.advancedPresetSelect) {
        this.advancedPresetSelect.value = '';
      }
      if (this.advancedSaveInput) {
        this.advancedSaveInput.value = '';
      }
      this.currentPresetName = null;
      this.renderAdvancedConditions();
      this.setAdvancedStatus('', 'none');
      this.persistAdvancedFilters({ logic: this.advancedLogic, filters: this.advancedFilters });
      this.applyFilters();
      this.updateAdvancedFilterButtonState();
      this.updatePresetButtonState();
    }

    handleAdvancedLoadSaved() {
      if (!this.savedPresets.length || !this.advancedPresetSelect) {
        this.setAdvancedStatus(this.messages.advanced.noSaved, 'info');
        return;
      }
      const name = this.advancedPresetSelect.value;
      if (!name) {
        this.setAdvancedStatus(this.messages.advanced.savedPlaceholder, 'info');
        return;
      }
      const preset = this.savedPresets.find((item) => item.name === name);
      if (!preset) {
        this.setAdvancedStatus(this.messages.advanced.noSaved, 'info');
        return;
      }
      const payload = preset.payload || {};
      const filters = Array.isArray(payload.filters) ? payload.filters : [];
      this.advancedFilters = cloneFilters(filters);
      this.advancedLogic = payload.logic === 'or' ? 'or' : 'and';
      this.renderAdvancedConditions();
      this.populateLogicOptions();
      this.setAdvancedStatus(this.messages.advanced.loadedSaved, 'success');
      this.currentPresetName = name;
      if (this.advancedSaveInput) {
        this.advancedSaveInput.value = name;
      }
      this.persistAdvancedFilters({ logic: this.advancedLogic, filters: this.advancedFilters });
      this.updateAdvancedFilterButtonState();
    }

    async handleAdvancedSave() {
      if (!this.filterEndpoint) {
        this.setAdvancedStatus(this.messages.advanced.noSaved, 'info');
        return;
      }
      const name = (this.advancedSaveInput ? this.advancedSaveInput.value : '').trim();
      if (!name) {
        this.setAdvancedStatus(this.messages.advanced.savePlaceholder, 'info');
        return;
      }
      const { filters, logic, hasError } = this.collectConditionsFromUI();
      if (hasError) {
        this.setAdvancedStatus(this.messages.advanced.validationMissingValue, 'error');
        return;
      }
      if (!filters.length) {
        this.setAdvancedStatus(this.messages.advanced.saveRequiresFilters, 'error');
        return;
      }
      const body = {
        name,
        payload: {
          version: STORAGE_VERSION,
          logic,
          filters: cloneFilters(filters),
          columns: this.getAdvancedFilterableColumns().map((column) => ({
            index: column.column,
            name: column.label,
            type: column.type || 'text',
          })),
        },
      };
      if (this.filterContext) {
        body.payload.context = this.filterContext;
      }
      const headers = { 'Content-Type': 'application/json', Accept: 'application/json' };
      const csrf = getCsrfToken();
      if (csrf) {
        headers['X-CSRFToken'] = csrf;
      }
      try {
        const response = await fetch(this.filterEndpoint, {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
        });
        const data = await response.json();
        if (!response.ok) {
          this.setAdvancedStatus(data.error || this.messages.advanced.saveError, 'error');
          return;
        }
        if (Array.isArray(data.presets)) {
          this.savedPresets = data.presets
            .map((preset) => ({ name: preset.name, payload: preset.payload || {} }))
            .filter((preset) => preset.name);
        }
        this.currentPresetName = name;
        this.updateSavedUI();
        if (this.advancedPresetSelect) {
          this.advancedPresetSelect.value = name;
        }
        this.setAdvancedStatus(data.message || this.messages.advanced.saveSuccess, 'success');
        this.persistAdvancedFilters({ logic: this.advancedLogic, filters: this.advancedFilters });
      } catch (error) {
        this.setAdvancedStatus(this.messages.advanced.saveError, 'error');
      }
    }

    async handleAdvancedDeleteSaved() {
      if (!this.filterEndpoint || !this.advancedPresetSelect) {
        this.setAdvancedStatus(this.messages.advanced.noSaved, 'info');
        return;
      }
      const name = this.advancedPresetSelect.value;
      if (!name) {
        this.setAdvancedStatus(this.messages.advanced.savedPlaceholder, 'info');
        return;
      }
      const headers = { 'Content-Type': 'application/json', Accept: 'application/json' };
      const csrf = getCsrfToken();
      if (csrf) {
        headers['X-CSRFToken'] = csrf;
      }
      try {
        const response = await fetch(this.filterEndpoint, {
          method: 'DELETE',
          headers,
          body: JSON.stringify({ name }),
        });
        const data = await response.json();
        if (!response.ok) {
          this.setAdvancedStatus(data.error || this.messages.advanced.deleteError, 'error');
          return;
        }
        if (Array.isArray(data.presets)) {
          this.savedPresets = data.presets
            .map((preset) => ({ name: preset.name, payload: preset.payload || {} }))
            .filter((preset) => preset.name);
        } else {
          this.savedPresets = this.savedPresets.filter((preset) => preset.name !== name);
        }
        if (this.currentPresetName === name) {
          this.currentPresetName = null;
          if (this.advancedSaveInput) {
            this.advancedSaveInput.value = '';
          }
        }
        if (this.advancedPresetSelect) {
          this.advancedPresetSelect.value = '';
        }
        this.updateSavedUI();
        this.updatePresetButtonState();
        this.setAdvancedStatus(data.message || this.messages.advanced.deleteSuccess, 'success');
        this.persistAdvancedFilters({ logic: this.advancedLogic, filters: this.advancedFilters });
      } catch (error) {
        this.setAdvancedStatus(this.messages.advanced.deleteError, 'error');
      }
    }

    async refreshAdvancedPresets({ silent = false } = {}) {
      if (!this.filterEndpoint) {
        this.updateSavedUI();
        if (!silent) {
          this.setAdvancedStatus(this.messages.advanced.noSaved, 'info');
        }
        return;
      }
      try {
        const response = await fetch(this.filterEndpoint, { headers: { Accept: 'application/json' } });
        if (!response.ok) {
          throw new Error('Failed to fetch presets');
        }
        const data = await response.json();
        if (Array.isArray(data.presets)) {
          this.savedPresets = data.presets
            .map((preset) => ({ name: preset.name, payload: preset.payload || {} }))
            .filter((preset) => preset.name);
        } else {
          this.savedPresets = [];
        }
        this.updateSavedUI();
        if (!this.savedPresets.length && !silent) {
          this.setAdvancedStatus(this.messages.advanced.noSaved, 'info');
        }
      } catch (error) {
        if (!silent) {
          this.setAdvancedStatus(this.messages.advanced.noSaved, 'info');
        }
      }
    }

    updatePresetButtonState() {
      const hasSelection = Boolean(this.advancedPresetSelect && this.advancedPresetSelect.value);
      if (this.advancedLoadButton) {
        this.advancedLoadButton.disabled = !hasSelection;
      }
      if (this.advancedDeleteButton) {
        this.advancedDeleteButton.disabled = !hasSelection;
      }
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

    persistAdvancedFilters({ logic, filters } = {}) {
      if (!this.savedFiltersKey || typeof window === 'undefined' || !window.localStorage) {
        return;
      }
      try {
        const payload = {
          version: STORAGE_VERSION,
          lastApplied: {
            logic: logic === 'or' ? 'or' : 'and',
            filters: cloneFilters(Array.isArray(filters) ? filters : this.advancedFilters),
          },
          currentPreset: this.currentPresetName || null,
        };
        window.localStorage.setItem(this.savedFiltersKey, JSON.stringify(payload));
        if (payload.lastApplied.filters.length) {
          this.savedAdvancedFilters = {
            logic: payload.lastApplied.logic,
            filters: cloneFilters(payload.lastApplied.filters),
          };
        } else {
          this.savedAdvancedFilters = null;
        }
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
          this.currentPresetName = null;
          this.updateSavedUI();
          return;
        }
        const parsed = JSON.parse(stored);
        const lastApplied = parsed && parsed.lastApplied;
        if (!lastApplied || !Array.isArray(lastApplied.filters)) {
          window.localStorage.removeItem(this.savedFiltersKey);
          this.savedAdvancedFilters = null;
          this.currentPresetName = null;
          this.updateSavedUI();
          return;
        }
        const validFilters = lastApplied.filters
          .map((item) => ({
            column: Number(item.column),
            operator: item.operator,
            values: Array.isArray(item.values)
              ? item.values.map((value) => String(value))
              : [],
            type: item.type || (this.columnMeta.get(Number(item.column))?.type || 'text'),
          }))
          .filter((item) => this.columnMeta.has(item.column));
        const logicValue = lastApplied.logic === 'or' ? 'or' : 'and';
        this.currentPresetName = parsed.currentPreset || null;
        if (validFilters.length) {
          this.savedAdvancedFilters = { logic: logicValue, filters: cloneFilters(validFilters) };
          this.advancedFilters = cloneFilters(validFilters);
          this.advancedLogic = logicValue;
          if (apply) {
            this.applyFilters();
          }
        } else {
          this.savedAdvancedFilters = null;
          this.advancedFilters = [];
          this.advancedLogic = 'and';
        }
        this.updateSavedUI();
        this.updateAdvancedFilterButtonState();
      } catch (error) {
        window.localStorage.removeItem(this.savedFiltersKey);
        this.savedAdvancedFilters = null;
        this.currentPresetName = null;
        this.updateSavedUI();
      }
    }

    updateSavedUI() {
      if (!this.advancedPresetSelect) {
        return;
      }
      const selectedName =
        this.currentPresetName && this.savedPresets.some((preset) => preset.name === this.currentPresetName)
          ? this.currentPresetName
          : '';
      this.advancedPresetSelect.innerHTML = '';
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = this.messages.advanced.savedPlaceholder;
      this.advancedPresetSelect.appendChild(placeholder);
      this.savedPresets.forEach((preset) => {
        const option = document.createElement('option');
        option.value = preset.name;
        option.textContent = preset.name;
        this.advancedPresetSelect.appendChild(option);
      });
      this.advancedPresetSelect.value = selectedName;
      this.currentPresetName = selectedName || null;
      if (this.advancedPresetsContainer) {
        this.advancedPresetsContainer.hidden = this.savedPresets.length === 0;
      }
      this.updatePresetButtonState();
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

  function bindExternalExportButtons() {
    const buttons = document.querySelectorAll('[data-table-export-target]');
    buttons.forEach((button) => {
      if (button.dataset.exportBound === 'true') {
        return;
      }
      const targetId = button.dataset.tableExportTarget;
      const format = (button.dataset.exportFormat || 'xlsx').toLowerCase();
      button.addEventListener('click', () => {
        const instance = window.InteractiveTableRegistry.get(targetId);
        if (!instance) {
          return;
        }
        if (!instance.exportButtons.includes(button)) {
          instance.exportButtons.push(button);
        }
        instance.handleExport(format);
      });
      button.dataset.exportBound = 'true';
    });

    const statuses = document.querySelectorAll('[data-table-export-status]');
    statuses.forEach((statusEl) => {
      const targetId = statusEl.dataset.tableExportStatus;
      const instance = window.InteractiveTableRegistry.get(targetId);
      if (instance) {
        instance.exportStatus = statusEl;
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

  document.addEventListener('DOMContentLoaded', () => {
    initTables();
    bindExternalExportButtons();
  });
})();
