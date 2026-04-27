(function () {
  let whatsappTemplatesCache = null;

  function closeModal(id) {
    document.getElementById(id)?.classList.remove('open');
  }

  function openWhatsAppFromTrigger(trigger, event) {
    if (!trigger) {
      return;
    }
    event?.preventDefault();
    event?.stopPropagation();
    window.openWaModal(
      trigger.dataset.waId,
      trigger.dataset.waName || '',
      trigger.dataset.waMobile || '',
    );
  }

  function bindWhatsAppTriggers(root = document) {
    root.querySelectorAll('[data-wa-open]').forEach((trigger) => {
      if (trigger.dataset.waBound === 'true') {
        return;
      }
      trigger.dataset.waBound = 'true';
      trigger.addEventListener('click', (event) => openWhatsAppFromTrigger(trigger, event));
    });
  }

  function resetWhatsAppModal(modal) {
    modal.querySelector('#wa_inq_id').value = '';
    modal.querySelector('#wa_name').textContent = '';
    modal.querySelector('#wa_mobile').textContent = '';
    modal.querySelector('#wa_message').value = '';
    modal.querySelector('#wa_template').innerHTML = '<option value="">- Select template -</option>';
  }

  function resolveTemplateMessage(option, name, mobile) {
    if (!option?.dataset?.msg) {
      return '';
    }
    let msg = decodeURIComponent(option.dataset.msg);
    msg = msg.replace(/\[NAME\]/g, name).replace(/\[MOBILE\]/g, mobile);
    return msg;
  }

  function bindTemplateSelection(sel, msgEl, name, mobile) {
    sel.onchange = () => {
      const opt = sel.selectedOptions[0];
      msgEl.value = resolveTemplateMessage(opt, name, mobile);
    };
  }

  async function loadWhatsAppTemplates(modal, name, mobile) {
    const sel = modal.querySelector('#wa_template');
    const msgEl = modal.querySelector('#wa_message');
    bindTemplateSelection(sel, msgEl, name, mobile);

    if (whatsappTemplatesCache === null) {
      try {
        const response = await fetch('/whatsapp/api/templates');
        const data = await response.json();
        if (!response.ok || !data.ok) {
          whatsappTemplatesCache = [];
        } else {
          whatsappTemplatesCache = Array.isArray(data.templates) ? data.templates : [];
        }
      } catch {
        whatsappTemplatesCache = [];
      }
    }

    const templates = whatsappTemplatesCache;
    if (!templates.length) {
      sel.innerHTML = '<option value="">- Manual message only -</option>';
      return;
    }

    sel.innerHTML = '<option value="">- Select template -</option>' +
      templates.map((template) => (
        `<option value="${template.id}" data-msg="${encodeURIComponent(template.description || '')}">${window.HeavyLift.escHtml(template.name)}</option>`
      )).join('');
  }

  window.openWaModal = async function openWaModal(inqId, name, mobile) {
    const modal = document.getElementById('waModal');
    if (!modal) {
      return;
    }
    resetWhatsAppModal(modal);
    modal.querySelector('#wa_inq_id').value = inqId;
    modal.querySelector('#wa_name').textContent = name;
    modal.querySelector('#wa_mobile').textContent = mobile;
    modal.classList.add('open');
    await loadWhatsAppTemplates(modal, name, mobile);
  };

  window.closeWaModal = function closeWaModal() {
    closeModal('waModal');
  };

  window.openPwModal = function openPwModal(uid, username) {
    const modal = document.getElementById('pwModal');
    if (!modal) {
      return;
    }
    modal.querySelector('#pw_uid').value = uid;
    modal.querySelector('#pw_username').textContent = username;
    modal.querySelector('#pw_new').value = '';
    modal.querySelector('#pw_confirm').value = '';
    modal.classList.add('open');
  };

  window.closePwModal = function closePwModal() {
    closeModal('pwModal');
  };

  document.addEventListener('DOMContentLoaded', () => {
    bindWhatsAppTriggers();

    document.addEventListener('click', (event) => {
      const trigger = event.target.closest('[data-wa-open]');
      if (!trigger) {
        return;
      }
      openWhatsAppFromTrigger(trigger, event);
    });

    document.getElementById('waSendBtn')?.addEventListener('click', async () => {
      const modal = document.getElementById('waModal');
      const inqId = modal.querySelector('#wa_inq_id').value;
      const msgEl = modal.querySelector('#wa_message');
      const templateSel = modal.querySelector('#wa_template');
      const templateOpt = templateSel.selectedOptions[0];
      const templateId = templateSel.value;
      const msg = msgEl.value.trim() || resolveTemplateMessage(
        templateOpt,
        modal.querySelector('#wa_name').textContent,
        modal.querySelector('#wa_mobile').textContent,
      );
      const popup = window.open('about:blank', '_blank', 'noopener');
      try {
        const response = await fetch(`/inquiries/${inqId}/whatsapp-send`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': window.HeavyLift?.csrfToken || '',
          },
          body: JSON.stringify({ msg_id: templateId || null, message: msg }),
        });
        const data = await response.json();
        if (data.ok) {
          if (data.url) {
            if (popup) {
              popup.location.replace(data.url);
            } else {
              window.location.href = data.url;
            }
          } else if (popup) {
            popup.close();
          }
          closeModal('waModal');
          if (data.msg) {
            alert(data.msg);
          }
        } else {
          popup?.close();
          alert(data.msg || 'Error sending.');
        }
      } catch {
        popup?.close();
        alert('Error connecting.');
      }
    });

    document.getElementById('pwSaveBtn')?.addEventListener('click', async () => {
      const modal = document.getElementById('pwModal');
      const uid = modal.querySelector('#pw_uid').value;
      const newPw = modal.querySelector('#pw_new').value;
      const conf = modal.querySelector('#pw_confirm').value;
      if (newPw !== conf) {
        alert('Passwords do not match.');
        return;
      }
      if (newPw.length < 8) {
        alert('Minimum 8 characters required.');
        return;
      }
      try {
        const response = await fetch(`/users/${uid}/change-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ new_password: newPw }),
        });
        const data = await response.json();
        if (data.ok) {
          closeModal('pwModal');
          alert('Password updated.');
        } else {
          alert(data.msg);
        }
      } catch {
        alert('Error connecting to server.');
      }
    });

    document.querySelectorAll('.modal-overlay').forEach((modal) => {
      modal.addEventListener('click', (event) => {
        if (event.target === modal) {
          modal.classList.remove('open');
        }
      });
    });
  });
})();
