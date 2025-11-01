(function () {
  function parseDelay(value) {
    var delay = parseInt(value, 10);
    return isNaN(delay) ? 350 : delay;
  }

  function submitForm(form) {
    if (form.dataset.submitting === 'true') {
      return;
    }
    form.dataset.submitting = 'true';
    if (typeof form.requestSubmit === 'function') {
      form.requestSubmit();
    } else {
      form.submit();
    }
  }

  function initFilterForms() {
    var forms = document.querySelectorAll('[data-filter-form]');
    forms.forEach(function (form) {
      var instantAttr = form.getAttribute('data-filter-instant');
      var instant = instantAttr !== 'false';
      var delayAttr = form.getAttribute('data-filter-delay');
      var delay = parseDelay(delayAttr);
      var searchInput = form.querySelector('[data-filter-search]');
      var debounceTimer = null;

      form.addEventListener('submit', function () {
        form.dataset.submitting = 'true';
        if (debounceTimer) {
          clearTimeout(debounceTimer);
        }
      });

      if (instant && searchInput) {
        var lastValue = searchInput.value;
        searchInput.addEventListener('input', function () {
          var current = searchInput.value;
          if (current === lastValue) {
            return;
          }
          lastValue = current;
          if (debounceTimer) {
            clearTimeout(debounceTimer);
          }
          debounceTimer = window.setTimeout(function () {
            submitForm(form);
          }, delay);
        });
      }

      if (instant) {
        form.querySelectorAll('[data-filter-select]').forEach(function (select) {
          select.addEventListener('change', function () {
            submitForm(form);
          });
        });
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFilterForms);
  } else {
    initFilterForms();
  }
})();
