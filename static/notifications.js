(() => {
    const stack = document.getElementById('notification-stack');
    const dialog = document.getElementById('app-confirm-dialog');
    const title = document.getElementById('app-dialog-title');
    const message = document.getElementById('app-dialog-message');
    const cancelButton = document.getElementById('app-dialog-cancel');
    const acceptButton = document.getElementById('app-dialog-accept');
    let finishDialog = null;

    function showToast(text, type = 'info') {
        if (!stack) return;

        const toast = document.createElement('div');
        toast.className = `app-toast is-${type}`;
        toast.setAttribute(
            'role',
            type === 'error' ? 'alert' : 'status'
        );

        const icon = document.createElement('span');
        icon.className = 'app-toast-icon';
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = type === 'success' ? '✓' : type === 'error' ? '!' : 'i';

        const body = document.createElement('p');
        body.className = 'app-toast-message';
        body.textContent = text;

        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'app-toast-close';
        close.setAttribute('aria-label', 'Tutup notifikasi');
        close.textContent = '×';

        const dismiss = () => {
            toast.classList.add('is-leaving');
            window.setTimeout(() => toast.remove(), 180);
        };

        close.addEventListener('click', dismiss);
        toast.append(icon, body, close);
        stack.append(toast);
        window.setTimeout(dismiss, type === 'error' ? 7000 : 5000);
    }

    function confirmAction(
        text,
        {
            heading = 'Konfirmasi tindakan',
            acceptText = 'Lanjutkan',
            cancelText = 'Batal',
            danger = false
        } = {}
    ) {
        if (!dialog) {
            showToast('Dialog konfirmasi tidak tersedia.', 'error');
            return Promise.resolve(false);
        }

        if (finishDialog) finishDialog(false);

        title.textContent = heading;
        message.textContent = text;
        cancelButton.textContent = cancelText;
        acceptButton.textContent = acceptText;
        acceptButton.classList.toggle('is-danger', danger);
        dialog.hidden = false;
        document.body.classList.add('app-dialog-open');

        return new Promise((resolve) => {
            const previousFocus = document.activeElement;
            const finish = (answer) => {
                if (!finishDialog) return;
                finishDialog = null;
                dialog.hidden = true;
                document.body.classList.remove('app-dialog-open');
                document.removeEventListener('keydown', onKeydown);
                cancelButton.removeEventListener('click', onCancel);
                acceptButton.removeEventListener('click', onAccept);
                dialog.removeEventListener('click', onBackdrop);
                if (previousFocus instanceof HTMLElement) previousFocus.focus();
                resolve(answer);
            };
            const onCancel = () => finish(false);
            const onAccept = () => finish(true);
            const onBackdrop = (event) => {
                if (event.target === dialog) finish(false);
            };
            const onKeydown = (event) => {
                if (event.key === 'Escape') {
                    event.preventDefault();
                    finish(false);
                } else if (event.key === 'Tab') {
                    event.preventDefault();
                    (document.activeElement === cancelButton
                        ? acceptButton
                        : cancelButton).focus();
                }
            };

            finishDialog = finish;
            cancelButton.addEventListener('click', onCancel);
            acceptButton.addEventListener('click', onAccept);
            dialog.addEventListener('click', onBackdrop);
            document.addEventListener('keydown', onKeydown);
            cancelButton.focus();
        });
    }

    document.querySelectorAll('.notification-seed [data-notification-type]')
        .forEach((item) => showToast(item.textContent.trim(), item.dataset.notificationType));

    window.JotoastNotifications = {
        show: showToast,
        confirm: confirmAction
    };

    document.addEventListener('click', (event) => {
        const link = event.target.closest('a[data-confirm]');
        if (!link) return;

        event.preventDefault();
        confirmAction(link.dataset.confirm, {
            heading: link.dataset.confirmTitle || 'Konfirmasi tindakan',
            acceptText: link.dataset.confirmAccept || 'Ya, lanjutkan',
            danger: link.dataset.confirmTone === 'danger'
        }).then((confirmed) => {
            if (confirmed) window.location.assign(link.href);
        });
    });

    document.addEventListener('submit', (event) => {
        const form = event.target;
        if (!form.matches('form[data-confirm]') || event.defaultPrevented) return;

        event.preventDefault();
        confirmAction(form.dataset.confirm, {
            heading: form.dataset.confirmTitle || 'Konfirmasi transaksi',
            acceptText: form.dataset.confirmAccept || 'Ya, simpan',
            danger: form.dataset.confirmTone === 'danger'
        }).then((confirmed) => {
            if (!confirmed) return;

            const submitter = event.submitter;
            if (submitter && form.dataset.confirmLoading) {
                submitter.disabled = true;
                submitter.textContent = form.dataset.confirmLoading;
            }
            HTMLFormElement.prototype.submit.call(form);
        });
    });
})();
