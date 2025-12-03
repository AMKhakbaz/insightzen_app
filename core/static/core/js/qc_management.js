(function () {
  const measureRoot = document.querySelector('.qc-management [data-measure-list]');
  const saveButton = document.querySelector('[data-save-measure]');
  const addRootButton = document.querySelector('[data-add-root]');
  const statusEl = document.querySelector('[data-measure-status]');
  const assignmentTable = document.querySelector('[data-filter-context="qc_management_assignment"]');
  const assignEmailInput = document.getElementById('qc-assign-email');
  const assignButton = document.querySelector('[data-assign-button]');
  const assignStatus = document.querySelector('[data-assign-status]');
  const defaultMeasureScript = document.getElementById('qc-default-measure');
  const defaultMeasure = defaultMeasureScript ? JSON.parse(defaultMeasureScript.textContent) : [];
  let hasSavedMeasure = false;
  let lastSavedStructure = [];

  function csrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function uuid() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `qc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function refreshEmptyState() {
    if (!measureRoot) return;
    const hasItems = measureRoot.querySelector(':scope > .qc-measure-item:not([data-empty])');
    const existingEmpty = measureRoot.querySelector('[data-empty]');
    if (!hasItems && !existingEmpty) {
      const empty = document.createElement('li');
      empty.className = 'qc-measure-item qc-measure-item--empty';
      empty.dataset.empty = 'true';
      empty.textContent = document.documentElement.lang === 'fa'
        ? 'هنوز آیتمی تعریف نشده است.'
        : 'No QC measure items defined yet.';
      measureRoot.appendChild(empty);
    }
    if (hasItems && existingEmpty) {
      existingEmpty.remove();
    }
  }

  function buildListFromDom(listEl) {
    const items = [];
    if (!listEl) return items;
    const children = listEl.querySelectorAll(':scope > .qc-measure-item:not([data-empty])');
    children.forEach((li) => {
      const labelInput = li.querySelector('[data-label-input]');
      const fieldInput = li.querySelector('[data-field-input]');
      const childList = li.querySelector(':scope > ul');
      const label = (labelInput?.value || '').trim();
      const field = (fieldInput?.value || label || '').trim();
      items.push({
        id: li.dataset.measureId || uuid(),
        label,
        field,
        children: buildListFromDom(childList),
      });
    });
    return items;
  }

  function ensureChildList(li) {
    let childList = li.querySelector(':scope > ul.qc-measure-list');
    if (!childList) {
      childList = document.createElement('ul');
      childList.className = 'qc-measure-list';
      li.appendChild(childList);
    }
    return childList;
  }

  function appendNodeFromStructure(node, listEl) {
    const li = createItem(node.label, node.field, node.id);
    listEl.appendChild(li);
    if (node.children && node.children.length) {
      const childList = ensureChildList(li);
      node.children.forEach((child) => appendNodeFromStructure(child, childList));
    }
    wireInteractions(li);
  }

  function rebuildListFromStructure(structure) {
    if (!measureRoot) return;
    measureRoot.innerHTML = '';
    structure.forEach((node) => appendNodeFromStructure(node, measureRoot));
    refreshEmptyState();
  }

  function focusLabelInput(li) {
    const labelInput = li?.querySelector('[data-label-input]');
    if (labelInput) {
      labelInput.focus();
      labelInput.select();
    }
  }

  function bindInputSync(li, labelInput, fieldInput) {
    if (!li || !labelInput || !fieldInput || li.dataset.inputBound === 'true') return;
    li.dataset.inputBound = 'true';
    const syncFieldDataset = () => {
      const nextLabel = (labelInput.value || '').trim();
      const nextField = (fieldInput.value || nextLabel).trim();
      li.dataset.measureField = nextField;
      if (!fieldInput.value && nextLabel) {
        fieldInput.value = nextLabel;
      }
    };

    labelInput.addEventListener('input', syncFieldDataset);
    fieldInput.addEventListener('input', syncFieldDataset);
  }

  function createItem(label, field, id) {
    const li = document.createElement('li');
    li.className = 'qc-measure-item';
    li.dataset.measureId = id || uuid();
    li.dataset.measureField = field || label;

    const body = document.createElement('div');
    body.className = 'qc-measure-item__body';
    body.draggable = true;
    body.dataset.draggable = 'true';

    const icon = document.createElement('div');
    icon.className = 'qc-measure-item__icon';
    body.appendChild(icon);

    const content = document.createElement('div');
    content.className = 'qc-measure-item__content';

    const labelInput = document.createElement('input');
    labelInput.type = 'text';
    labelInput.className = 'form-control form-control-sm qc-measure-item__input';
    labelInput.dataset.labelInput = 'true';
    labelInput.placeholder =
      document.documentElement.lang === 'fa' ? 'عنوان QC' : 'QC label';
    labelInput.value = label || '';

    const fieldInput = document.createElement('input');
    fieldInput.type = 'text';
    fieldInput.className =
      'form-control form-control-sm qc-measure-item__input qc-measure-item__input--sub';
    fieldInput.dataset.fieldInput = 'true';
    fieldInput.placeholder =
      document.documentElement.lang === 'fa' ? 'نام فیلد داده' : 'Data field';
    fieldInput.value = field || label || '';

    bindInputSync(li, labelInput, fieldInput);

    content.appendChild(labelInput);
    content.appendChild(fieldInput);
    body.appendChild(content);

    const actions = document.createElement('div');
    actions.className = 'qc-measure-item__actions';

    const addChildBtn = document.createElement('button');
    addChildBtn.type = 'button';
    addChildBtn.className = 'btn btn-text btn-sm';
    addChildBtn.dataset.addChild = 'true';
    addChildBtn.textContent = document.documentElement.lang === 'fa' ? 'افزودن زیرآیتم' : 'Add child';

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'btn btn-text btn-sm';
    removeBtn.dataset.removeItem = 'true';
    removeBtn.textContent = document.documentElement.lang === 'fa' ? 'حذف' : 'Remove';

    actions.appendChild(addChildBtn);
    actions.appendChild(removeBtn);
    body.appendChild(actions);
    li.appendChild(body);

    return li;
  }

  function handleAddRoot() {
    const item = createItem('', '');
    measureRoot.appendChild(item);
    refreshEmptyState();
    wireInteractions(item);
    focusLabelInput(item);
  }

  function handleAddChild(evt) {
    const li = evt.target.closest('.qc-measure-item');
    if (!li) return;
    const child = createItem('', '');
    ensureChildList(li).appendChild(child);
    refreshEmptyState();
    wireInteractions(child);
    focusLabelInput(child);
  }

  async function maybePromptDefaultReset() {
    if (!measureRoot || !hasSavedMeasure || !defaultMeasure.length) return;
    const hasItems = measureRoot.querySelector(':scope > .qc-measure-item:not([data-empty])');
    if (hasItems) return;
    const message =
      document.documentElement.lang === 'fa'
        ? 'همه آیتم‌ها حذف شدند. بازگردانی به مقدار پیش‌فرض؟'
        : 'All items were removed. Reset to the default QC measure?';
    const confirmed = window.confirm(message);
    if (!confirmed) return;
    rebuildListFromStructure(defaultMeasure);
    await persistStructure(defaultMeasure, {
      resetToDefault: true,
      pendingLabel: document.documentElement.lang === 'fa' ? 'در حال بازگردانی…' : 'Restoring defaults…',
      successLabel: document.documentElement.lang === 'fa' ? 'بازگردانی شد' : 'Defaults restored',
    });
  }

  async function handleRemove(evt) {
    const li = evt.target.closest('.qc-measure-item');
    if (!li) return;
    li.remove();
    refreshEmptyState();
    await maybePromptDefaultReset();
  }

  function handleDragStart(evt) {
    const li = evt.target.closest('.qc-measure-item');
    if (!li || !evt.dataTransfer) return;
    evt.dataTransfer.effectAllowed = 'move';
    evt.dataTransfer.setData('text/plain', li.dataset.measureId || '');
    li.classList.add('is-dragging');
  }

  function handleDragEnd(evt) {
    const li = evt.target.closest('.qc-measure-item');
    if (!li) return;
    li.classList.remove('is-dragging');
  }

  function handleDragOver(evt) {
    const targetBody = evt.target.closest('[data-draggable]');
    if (!targetBody) return;
    evt.preventDefault();
    evt.dataTransfer.dropEffect = 'move';
  }

  function handleDrop(evt) {
    const targetBody = evt.target.closest('[data-draggable]');
    if (!targetBody || !evt.dataTransfer) return;
    evt.preventDefault();
    const targetItem = targetBody.closest('.qc-measure-item');
    const draggedId = evt.dataTransfer.getData('text/plain');
    const draggedItem = measureRoot.querySelector(`[data-measure-id="${draggedId}"]`);
    if (!draggedItem || !targetItem || draggedItem === targetItem || targetItem.contains(draggedItem)) {
      return;
    }
    const childList = ensureChildList(targetItem);
    childList.appendChild(draggedItem);
    refreshEmptyState();
  }

  function wireInteractions(li) {
    const addChild = li.querySelector('[data-add-child]');
    const removeBtn = li.querySelector('[data-remove-item]');
    const body = li.querySelector('[data-draggable]');
    const labelInput = li.querySelector('[data-label-input]');
    const fieldInput = li.querySelector('[data-field-input]');
    bindInputSync(li, labelInput, fieldInput);
    if (addChild) addChild.addEventListener('click', handleAddChild);
    if (removeBtn) removeBtn.addEventListener('click', handleRemove);
    if (body) {
      body.addEventListener('dragstart', handleDragStart);
      body.addEventListener('dragend', handleDragEnd);
      body.addEventListener('dragover', handleDragOver);
      body.addEventListener('drop', handleDrop);
    }
  }

  function wireExistingItems() {
    const items = measureRoot ? measureRoot.querySelectorAll('.qc-measure-item') : [];
    items.forEach((li) => wireInteractions(li));
  }

  function syncSavedState(structure) {
    lastSavedStructure = structure || [];
    hasSavedMeasure = true;
    if (measureRoot) {
      measureRoot.dataset.measureSaved = 'true';
    }
  }

  function initialiseSavedState() {
    if (!measureRoot) return;
    lastSavedStructure = buildListFromDom(measureRoot);
    hasSavedMeasure = (measureRoot.dataset.measureSaved || '').toLowerCase() === 'true';
  }

  function setStatus(message, state) {
    if (!statusEl) return;
    statusEl.textContent = message || '';
    statusEl.dataset.state = state || '';
  }

  function setAssignStatus(message, state) {
    if (!assignStatus) return;
    assignStatus.textContent = message || '';
    assignStatus.dataset.state = state || '';
  }

  async function persistStructure(structure, options = {}) {
    if (!saveButton || !measureRoot) return;
    const endpoint = saveButton.dataset.endpoint;
    const entry = saveButton.dataset.entry;
    const { resetToDefault = false, pendingLabel, successLabel } = options;
    if (!endpoint || !entry) return;
    const payload = {
      measure: structure,
      reset_to_default: resetToDefault,
    };
    const pendingMessage =
      pendingLabel || (document.documentElement.lang === 'fa' ? 'در حال ذخیره…' : 'Saving…');
    const successMessage =
      successLabel || (document.documentElement.lang === 'fa' ? 'ذخیره شد' : 'Saved');
    setStatus(pendingMessage, 'saving');
    try {
      const resp = await fetch(`${endpoint}?entry=${encodeURIComponent(entry)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken(),
        },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.error || 'Request failed');
      }
      syncSavedState(resetToDefault ? defaultMeasure : structure);
      setStatus(successMessage, 'success');
      setTimeout(() => setStatus('', ''), 3500);
    } catch (err) {
      setStatus(document.documentElement.lang === 'fa' ? 'ذخیره انجام نشد' : 'Save failed', 'error');
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  function selectedAssignments() {
    if (!assignmentTable) return [];
    return Array.from(
      assignmentTable.querySelectorAll('tbody input[type="checkbox"]:checked'),
    )
      .map((box) => box.value)
      .filter((value) => value);
  }

  async function handleAssignClick() {
    if (!assignButton) return;
    const endpoint = assignButton.dataset.endpoint;
    const entry = assignButton.dataset.entry;
    const email = (assignEmailInput?.value || '').trim();
    const selected = selectedAssignments();

    if (!endpoint || !entry) {
      setAssignStatus(
        document.documentElement.lang === 'fa'
          ? 'آدرس تخصیص در دسترس نیست.'
          : 'Assignment endpoint is unavailable.',
        'error',
      );
      return;
    }

    if (!email) {
      setAssignStatus(
        document.documentElement.lang === 'fa'
          ? 'ایمیل را وارد کنید.'
          : 'Please enter an email address.',
        'error',
      );
      return;
    }

    if (!selected.length) {
      setAssignStatus(
        document.documentElement.lang === 'fa'
          ? 'هیچ ردیفی انتخاب نشده است.'
          : 'No rows selected.',
        'error',
      );
      return;
    }

    setAssignStatus(
      document.documentElement.lang === 'fa' ? 'در حال تخصیص…' : 'Assigning…',
      'pending',
    );

    try {
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken(),
        },
        body: JSON.stringify({
          entry,
          email,
          submissions: selected,
        }),
      });
      const data = await resp.json();
      if (!resp.ok || data.error) {
        throw new Error(data.error || 'Request failed');
      }
      setAssignStatus(
        document.documentElement.lang === 'fa'
          ? 'تخصیص با موفقیت انجام شد.'
          : 'Assignments sent successfully.',
        'success',
      );
      if (assignEmailInput) assignEmailInput.value = '';
      assignmentTable
        ?.querySelectorAll('tbody input[type="checkbox"]:checked')
        .forEach((box) => {
          // eslint-disable-next-line no-param-reassign
          box.checked = false;
        });
      setTimeout(() => setAssignStatus('', ''), 3500);
    } catch (err) {
      setAssignStatus(
        document.documentElement.lang === 'fa'
          ? 'تخصیص انجام نشد.'
          : 'Assignment failed.',
        'error',
      );
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  async function saveStructure() {
    if (!measureRoot) return;
    const structure = buildListFromDom(measureRoot);
    await persistStructure(structure);
  }

  if (addRootButton) {
    addRootButton.addEventListener('click', handleAddRoot);
  }
  if (saveButton) {
    saveButton.addEventListener('click', saveStructure);
  }
  if (assignButton) {
    assignButton.addEventListener('click', handleAssignClick);
  }

  if (measureRoot) {
    initialiseSavedState();
    refreshEmptyState();
    wireExistingItems();
  }
})();
