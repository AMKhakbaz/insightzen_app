(function () {
  const checklistForm = document.querySelector('[data-checklist-form]');
  const reviewTable = document.querySelector('[data-review-table]');
  const surveyButton = document.querySelector('[data-open-surveyzen]');
  const surveyStatus = document.querySelector('[data-surveyzen-status]');

  function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  function updateChecklistCell(rowId, measureId, checked) {
    if (!reviewTable) return;
    const cell = reviewTable.querySelector(
      `[data-row="${rowId}"][data-measure-cell="${measureId}"]`
    );
    if (!cell || !checklistForm) return;
    const trueLabel = checklistForm.dataset.trueLabel || 'True';
    const falseLabel = checklistForm.dataset.falseLabel || 'False';
    cell.textContent = checked ? trueLabel : falseLabel;
  }

  if (checklistForm) {
    checklistForm.addEventListener('change', (event) => {
      const target = event.target;
      if (target && target.matches('[data-checklist-toggle]')) {
        const rowId = target.getAttribute('data-row');
        const measureId = target.getAttribute('data-measure');
        if (rowId && measureId) {
          updateChecklistCell(rowId, measureId, target.checked);
        }
      }
    });
  }

  if (surveyButton) {
    surveyButton.addEventListener('click', async () => {
      const entryId = surveyButton.getAttribute('data-entry');
      const submissionId = surveyButton.getAttribute('data-submission');
      if (!entryId || !submissionId) {
        return;
      }

      const loadingText = surveyButton.getAttribute('data-loading-text') || '';
      const successText = surveyButton.getAttribute('data-success-text') || '';
      const errorText = surveyButton.getAttribute('data-error-text') || '';
      if (surveyStatus) {
        surveyStatus.textContent = loadingText;
      }

      surveyButton.disabled = true;
      surveyButton.classList.add('disabled');
      try {
        const response = await fetch(`/qc/edit/${entryId}/link/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
          },
          body: JSON.stringify({ submission_id: submissionId }),
        });
        const payload = await response.json();
        if (response.ok && payload.url) {
          window.open(payload.url, '_blank');
          if (surveyStatus) {
            surveyStatus.textContent = successText;
          }
        } else if (payload.error) {
          if (surveyStatus) {
            surveyStatus.textContent = payload.error;
          } else {
            alert(payload.error);
          }
        } else if (surveyStatus) {
          surveyStatus.textContent = errorText;
        }
      } catch (error) {
        console.error('Failed to open SurveyZen link', error);
        if (surveyStatus) {
          surveyStatus.textContent = errorText;
        }
      } finally {
        surveyButton.disabled = false;
        surveyButton.classList.remove('disabled');
      }
    });
  }
})();
