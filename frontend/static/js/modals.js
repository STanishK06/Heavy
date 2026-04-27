(function () {
  function closeModal(id) {
    document.getElementById(id)?.classList.remove('open');
  }

  window.openWaModal = async function openWaModal(inqId, name, mobile) {
    const modal = document.getElementById('waModal');
    if (!modal) {
      return;
    }
    modal.querySelector('#wa_inq_id').value = inqId;
    modal.querySelector('#wa_name').textContent = name;
    modal.querySelector('#wa_mobile').textContent = mobile;
    const sel = modal.querySelector('#wa_template');
    const msgEl = modal.querySelector('#wa_message');

    try {
      const response = await fetch('/whatsapp/api/templates');
      const data = await response.json();
      if (!response.ok || !data.ok) {
        sel.innerHTML = '<option value="">- Templates unavailable -</option>';
        msgEl.value = '';
        modal.classList.add('open');
        return;
      }

      const templates = Array.isArray(data.templates) ? data.templates : [];
      sel.innerHTML = '<option value="">- Select template -</option>' +
        templates.map((template) => (
          `<option value="${template.id}" data-msg="${encodeURIComponent(template.description || '')}">${window.HeavyLift.escHtml(template.name)}</option>`
        )).join('');

      sel.onchange = () => {
        const opt = sel.selectedOptions[0];
        if (!opt || !opt.dataset.msg) {
          msgEl.value = '';
          return;
        }
        let msg = decodeURIComponent(opt.dataset.msg);
        msg = msg.replace(/\[NAME\]/g, name).replace(/\[MOBILE\]/g, mobile);
        msgEl.value = msg;
      };
    } catch {}

    modal.classList.add('open');
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
    document.getElementById('waSendBtn')?.addEventListener('click', async () => {
      const modal = document.getElementById('waModal');
      const inqId = modal.querySelector('#wa_inq_id').value;
      const msg = modal.querySelector('#wa_message').value.trim();
      const popup = window.open('', '_blank', 'noopener');
      try {
        const response = await fetch(`/inquiries/${inqId}/whatsapp-send`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: msg }),
        });
        const data = await response.json();
        if (data.ok) {
          if (popup) {
            popup.location = data.url;
          } else {
            window.location.href = data.url;
          }
          closeModal('waModal');
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
