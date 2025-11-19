(function () {
  document.addEventListener('DOMContentLoaded', function () {
    const toggle = document.querySelector('[data-calendar-toggle]');
    const panel = document.querySelector('[data-calendar-panel]');
    if (!toggle || !panel || !window.FullCalendar) {
      return;
    }

    const calendarEl = panel.querySelector('[data-calendar-container]');
    const form = panel.querySelector('[data-calendar-form]');
    const statusEl = panel.querySelector('[data-calendar-status]');
    const deleteBtn = panel.querySelector('[data-calendar-delete]');
    const resetBtn = panel.querySelector('[data-calendar-reset]');
    const participantsSelect = panel.querySelector('[data-calendar-participants]');
    const reminderSelect = panel.querySelector('[data-calendar-reminder]');
    const closeEls = panel.querySelectorAll('[data-calendar-dismiss]');

    const lang = document.documentElement.lang === 'fa' ? 'fa' : 'en';
    const text = {
      en: {
        saved: 'Event saved.',
        deleted: 'Event deleted.',
        loadingPeople: 'Loading teammates…',
        ready: 'Select a slot to start.',
        error: 'Something went wrong.',
        inviteLabel: 'Invite people',
        saving: 'Saving…',
        deleting: 'Deleting…',
      },
      fa: {
        saved: 'رویداد ذخیره شد.',
        deleted: 'رویداد حذف شد.',
        loadingPeople: 'در حال بارگذاری اعضا…',
        ready: 'برای شروع یک بازه را انتخاب کنید.',
        error: 'خطایی رخ داد.',
        inviteLabel: 'دعوت همکاران',
        saving: 'در حال ذخیره…',
        deleting: 'در حال حذف…',
      },
    };

    let calendar;
    let currentEventId = null;
    let participantsLoaded = false;

    function refreshCalendarSize() {
      if (calendar) {
        calendar.updateSize();
      }
    }

    function openPanel() {
      panel.hidden = false;
      requestAnimationFrame(() => {
        panel.classList.add('is-open');
        setTimeout(refreshCalendarSize, 220);
      });
      toggle.setAttribute('aria-expanded', 'true');
      ensureCalendar();
      loadParticipants();
      setStatus(text[lang].ready);
    }

    function closePanel() {
      panel.classList.remove('is-open');
      toggle.setAttribute('aria-expanded', 'false');
      setTimeout(() => {
        panel.hidden = true;
        refreshCalendarSize();
      }, 180);
    }

    function setStatus(message, tone) {
      if (!statusEl) return;
      statusEl.textContent = message || '';
      if (tone) {
        statusEl.dataset.tone = tone;
      } else {
        delete statusEl.dataset.tone;
      }
    }

    function loadParticipants() {
      if (!participantsSelect || participantsLoaded) return;
      setStatus(text[lang].loadingPeople);
      fetch('/api/calendar/participants/', { credentials: 'same-origin' })
        .then((resp) => resp.json())
        .then((data) => {
          const list = data.participants || [];
          participantsSelect.innerHTML = '';
          list.forEach((item) => {
            const option = document.createElement('option');
            option.value = item.id;
            option.textContent = item.name + (item.email ? ` · ${item.email}` : '');
            participantsSelect.appendChild(option);
          });
          participantsLoaded = true;
          setStatus(text[lang].ready);
        })
        .catch(() => {
          setStatus(text[lang].error, 'error');
        });
    }

    function ensureCalendar() {
      if (calendar || !calendarEl) return;
      calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        height: '100%',
        locale: lang,
        direction: lang === 'fa' ? 'rtl' : 'ltr',
        selectable: true,
        handleWindowResize: true,
        dayMaxEventRows: true,
        firstDay: lang === 'fa' ? 6 : 0,
        headerToolbar: {
          left: 'prev,next today',
          center: 'title',
          right: 'dayGridMonth,timeGridWeek,timeGridDay',
        },
        select(info) {
          populateForm({
            id: null,
            title: '',
            description: '',
            start: info.startStr,
            end: info.endStr,
            reminder_minutes_before: reminderSelect ? reminderSelect.value : null,
            participants: [],
            can_edit: true,
          });
          calendar.unselect();
          const titleInput = form?.querySelector('input[name="title"]');
          if (titleInput) {
            titleInput.focus();
          }
        },
        eventClick(info) {
          if (info.event.extendedProps && info.event.extendedProps.raw) {
            populateForm(info.event.extendedProps.raw);
          }
        },
        eventAllow(dropInfo) {
          const raw = dropInfo.event.extendedProps?.raw;
          return raw ? !!raw.can_edit : false;
        },
        eventDrop(info) {
          if (!persistMove(info)) {
            info.revert();
          }
        },
        eventResize(info) {
          if (!persistMove(info)) {
            info.revert();
          }
        },
        events(info, success, failure) {
          const params = new URLSearchParams({ start: info.startStr, end: info.endStr });
          fetch(`/api/calendar/events/?${params.toString()}`, { credentials: 'same-origin' })
            .then((resp) => resp.json())
            .then((data) => {
              const mapped = (data.events || []).map((event) => ({
                id: event.id,
                title: event.title,
                start: event.start,
                end: event.end,
                backgroundColor: event.can_edit ? '#15b8d9' : '#4c4e55',
                borderColor: '#22242a',
                textColor: '#f5f5f5',
                extendedProps: { raw: event },
              }));
              success(mapped);
            })
            .catch(() => {
              failure();
              setStatus(text[lang].error, 'error');
            });
        },
      });
      calendar.render();
      refreshCalendarSize();
    }

    function populateForm(event) {
      if (!form) return;
      currentEventId = event.id || null;
      form.dataset.mode = currentEventId ? 'edit' : 'create';
      form.querySelector('input[name="title"]').value = event.title || '';
      form.querySelector('textarea[name="description"]').value = event.description || '';
      form.querySelector('input[name="start"]').value = toLocalInput(event.start);
      form.querySelector('input[name="end"]').value = toLocalInput(event.end);
      if (reminderSelect) {
        reminderSelect.value = event.reminder_minutes_before || '';
      }
      if (participantsSelect) {
        const participantIds = (event.participants || []).map((p) => String(p.id));
        Array.from(participantsSelect.options).forEach((option) => {
          option.selected = participantIds.includes(option.value);
        });
      }
      if (deleteBtn) {
        deleteBtn.hidden = !currentEventId;
      }
    }

    function resetForm() {
      if (!form) return;
      currentEventId = null;
      form.dataset.mode = 'create';
      form.reset();
      if (deleteBtn) {
        deleteBtn.hidden = true;
      }
      if (participantsSelect) {
        Array.from(participantsSelect.options).forEach((option) => {
          option.selected = false;
        });
      }
      setStatus(text[lang].ready);
    }

    function toUTC(value) {
      if (!value) return null;
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        return null;
      }
      return date.toISOString();
    }

    function toLocalInput(value) {
      if (!value) return '';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        return '';
      }
      const tzOffset = date.getTimezoneOffset();
      const local = new Date(date.getTime() - tzOffset * 60000);
      return local.toISOString().slice(0, 16);
    }

    function collectPayload() {
      const title = form.querySelector('input[name="title"]').value.trim();
      const description = form.querySelector('textarea[name="description"]').value.trim();
      const startVal = form.querySelector('input[name="start"]').value;
      const endVal = form.querySelector('input[name="end"]').value;
      const reminderVal = reminderSelect ? reminderSelect.value : '';
      const participantValues = participantsSelect ? Array.from(participantsSelect.selectedOptions).map((opt) => opt.value) : [];
      return {
        title,
        description,
        start: toUTC(startVal),
        end: toUTC(endVal),
        reminder_minutes_before: reminderVal || null,
        participants: participantValues,
      };
    }

    function persistMove(info) {
      const raw = info.event.extendedProps.raw;
      if (!raw || !raw.can_edit) {
        return false;
      }
      const payload = {
        title: raw.title,
        description: raw.description,
        start: info.event.startStr,
        end: info.event.endStr || info.event.startStr,
        reminder_minutes_before: raw.reminder_minutes_before,
        participants: (raw.participants || []).map((p) => p.id),
      };
      saveEvent('PUT', `/api/calendar/events/${raw.id}/`, payload)
        .then(() => {
          setStatus(text[lang].saved);
          calendar.refetchEvents();
        })
        .catch(() => {
          setStatus(text[lang].error, 'error');
          info.revert();
        });
      return true;
    }

    function saveEvent(method, url, payload) {
      setStatus(method === 'DELETE' ? text[lang].deleting : text[lang].saving);
      return fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': typeof getCookie === 'function' ? getCookie('csrftoken') : '',
        },
        credentials: 'same-origin',
        body: method === 'DELETE' ? null : JSON.stringify(payload),
      }).then((resp) => {
        if (!resp.ok) {
          throw new Error('Request failed');
        }
        if (method === 'DELETE') {
          return resp.json().catch(() => ({}));
        }
        return resp.json();
      });
    }

    if (form) {
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        const payload = collectPayload();
        if (!payload.start || !payload.end) {
          setStatus(text[lang].error, 'error');
          return;
        }
        const url = currentEventId ? `/api/calendar/events/${currentEventId}/` : '/api/calendar/events/';
        const method = currentEventId ? 'PUT' : 'POST';
        saveEvent(method, url, payload)
          .then((data) => {
            if (!data || data.ok === false) {
              throw new Error('Failed');
            }
            setStatus(text[lang].saved);
            if (data.event) {
              populateForm(data.event);
            } else {
              resetForm();
            }
            if (calendar) {
              calendar.refetchEvents();
            }
          })
          .catch(() => {
            setStatus(text[lang].error, 'error');
          });
      });
    }

    if (resetBtn) {
      resetBtn.addEventListener('click', function () {
        resetForm();
      });
    }

    if (deleteBtn) {
      deleteBtn.addEventListener('click', function () {
        if (!currentEventId) return;
        saveEvent('DELETE', `/api/calendar/events/${currentEventId}/`)
          .then(() => {
            setStatus(text[lang].deleted);
            resetForm();
            if (calendar) {
              calendar.refetchEvents();
            }
          })
          .catch(() => {
            setStatus(text[lang].error, 'error');
          });
      });
    }

    toggle.addEventListener('click', function () {
      if (panel.hidden || !panel.classList.contains('is-open')) {
        openPanel();
      } else {
        closePanel();
      }
    });

    closeEls.forEach((btn) => {
      btn.addEventListener('click', () => {
        closePanel();
      });
    });

    panel.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        closePanel();
      }
    });

    let resizeTimer;
    window.addEventListener('resize', () => {
      if (resizeTimer) {
        clearTimeout(resizeTimer);
      }
      resizeTimer = setTimeout(() => {
        refreshCalendarSize();
      }, 150);
    });
  });
})();
