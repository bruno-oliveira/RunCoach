/**
 * notify.js — the app's own voice for transient messages and confirmations.
 *
 * Replaces native window.alert()/confirm() so every message lands in RunCoach's
 * register instead of a browser chrome dialog. Fully self-contained: injects its
 * own scoped styles (built on the existing CSS design tokens) and DOM, so it is a
 * drop-in on any page regardless of which modal system that page loads.
 *
 * Public API (also on window):
 *   notify(message, { type, title, duration })      -> toast, auto-dismisses
 *   confirmDialog({ title, body, confirmLabel,
 *                   cancelLabel, danger })            -> Promise<boolean>
 */
(function () {
  'use strict';

  var STYLE_ID = 'rc-notify-styles';
  var TOAST_CONTAINER_ID = 'rc-toast-container';

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = [
      '#' + TOAST_CONTAINER_ID + '{position:fixed;bottom:24px;right:24px;z-index:10000;',
      'display:flex;flex-direction:column;gap:12px;max-width:min(420px,calc(100vw - 32px));pointer-events:none;}',
      '.rc-toast{pointer-events:auto;display:flex;align-items:flex-start;gap:12px;',
      'padding:14px 16px;background:var(--color-bg-elevated,#fff);color:var(--color-text,#111);',
      'border:1px solid var(--color-border,#e5e7eb);border-left:4px solid var(--color-primary,#2563eb);',
      'border-radius:var(--radius-xl,14px);box-shadow:0 8px 32px rgba(0,0,0,0.15);',
      'font-size:0.925rem;line-height:1.4;animation:rcToastIn 0.28s ease;}',
      '.rc-toast.rc-toast-success{border-left-color:var(--color-success,#16a34a);}',
      '.rc-toast.rc-toast-error{border-left-color:var(--color-error,#dc2626);}',
      '.rc-toast.rc-toast-info{border-left-color:var(--color-primary,#2563eb);}',
      '.rc-toast .rc-toast-icon{flex-shrink:0;font-size:1.1rem;line-height:1.3;}',
      '.rc-toast .rc-toast-content{flex:1;min-width:0;}',
      '.rc-toast .rc-toast-title{font-weight:600;margin-bottom:2px;}',
      '.rc-toast .rc-toast-close{flex-shrink:0;background:none;border:none;cursor:pointer;',
      'font-size:1.15rem;line-height:1;color:var(--color-text-muted,#9ca3af);padding:0 2px;}',
      '.rc-toast .rc-toast-close:hover{color:var(--color-text,#111);}',
      '.rc-toast-out{animation:rcToastOut 0.25s ease forwards;}',
      '@keyframes rcToastIn{from{opacity:0;transform:translateY(16px);}to{opacity:1;transform:translateY(0);}}',
      '@keyframes rcToastOut{to{opacity:0;transform:translateY(10px);}}',
      // Confirm dialog
      '.rc-confirm-overlay{position:fixed;inset:0;z-index:10001;display:flex;align-items:center;',
      'justify-content:center;padding:16px;background:rgba(0,0,0,0.5);animation:rcFadeIn 0.2s ease;}',
      '.rc-confirm{background:var(--color-bg-elevated,#fff);color:var(--color-text,#111);',
      'border-radius:12px;box-shadow:0 10px 25px rgba(0,0,0,0.25);width:100%;max-width:440px;',
      'overflow:hidden;animation:rcDialogIn 0.24s ease-out;}',
      '.rc-confirm-head{padding:1.25rem 1.5rem 0;}',
      '.rc-confirm-title{margin:0;font-size:1.2rem;font-weight:600;}',
      '.rc-confirm-body{padding:0.5rem 1.5rem 1.25rem;color:var(--color-text-secondary,#4b5563);line-height:1.5;}',
      '.rc-confirm-foot{display:flex;justify-content:flex-end;gap:0.75rem;padding:1rem 1.5rem;',
      'border-top:1px solid var(--color-border,#e5e7eb);}',
      '.rc-confirm-btn{padding:0.625rem 1.25rem;border:none;border-radius:6px;cursor:pointer;',
      'font-size:0.95rem;font-weight:500;}',
      '.rc-confirm-cancel{background:var(--color-surface,#f3f4f6);color:var(--color-text,#111);}',
      '.rc-confirm-cancel:hover{background:var(--color-border,#e5e7eb);}',
      '.rc-confirm-ok{background:var(--color-primary,#2563eb);color:var(--color-text-on-primary,#fff);}',
      '.rc-confirm-ok:hover{filter:brightness(0.94);}',
      '.rc-confirm-ok.rc-danger{background:var(--color-error,#dc2626);}',
      '@keyframes rcFadeIn{from{opacity:0;}to{opacity:1;}}',
      '@keyframes rcDialogIn{from{opacity:0;transform:translateY(-24px);}to{opacity:1;transform:translateY(0);}}'
    ].join('');
    (document.head || document.documentElement).appendChild(style);
  }

  function toastContainer() {
    var el = document.getElementById(TOAST_CONTAINER_ID);
    if (!el) {
      el = document.createElement('div');
      el.id = TOAST_CONTAINER_ID;
      document.body.appendChild(el);
    }
    return el;
  }

  var ICONS = { success: '✓', error: '✕', info: 'ℹ' };

  // Map a notify type onto the public ApiClient toast method, when available.
  var API_METHOD = {
    success: 'showSuccess',
    error: 'showError',
    warning: 'showWarning',
    info: 'showInfo'
  };

  /**
   * Show a transient toast in the app's voice.
   *
   * Delegates to the existing ApiClient toast (window.api) so there is a single
   * toast look across the app; only falls back to a self-contained toast if that
   * system isn't loaded on the page.
   * @param {string} message
   * @param {{type?:'success'|'error'|'info'|'warning', title?:string, duration?:number}} [opts]
   */
  function notify(message, opts) {
    opts = opts || {};
    var type = opts.type || 'info';
    var text = opts.title ? opts.title + ' — ' + message : message;

    var api = window.api;
    var method = API_METHOD[type] || API_METHOD.info;
    if (api && typeof api[method] === 'function') {
      api[method](text);
      return function () {};
    }

    // --- Fallback: self-contained toast (ApiClient not present on this page) ---
    injectStyles();
    var duration = typeof opts.duration === 'number' ? opts.duration : 4200;

    var toast = document.createElement('div');
    toast.className = 'rc-toast rc-toast-' + type;
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');

    var icon = document.createElement('span');
    icon.className = 'rc-toast-icon';
    icon.textContent = ICONS[type] || ICONS.info;

    var content = document.createElement('div');
    content.className = 'rc-toast-content';
    if (opts.title) {
      var title = document.createElement('div');
      title.className = 'rc-toast-title';
      title.textContent = opts.title;
      content.appendChild(title);
    }
    var body = document.createElement('div');
    body.textContent = message;
    content.appendChild(body);

    var close = document.createElement('button');
    close.className = 'rc-toast-close';
    close.setAttribute('aria-label', 'Dismiss');
    close.innerHTML = '&times;';

    toast.appendChild(icon);
    toast.appendChild(content);
    toast.appendChild(close);
    toastContainer().appendChild(toast);

    var timer;
    function dismiss() {
      if (!toast.parentNode) return;
      clearTimeout(timer);
      toast.classList.add('rc-toast-out');
      toast.addEventListener('animationend', function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      });
    }
    close.addEventListener('click', dismiss);
    if (duration > 0) timer = setTimeout(dismiss, duration);
    return dismiss;
  }

  /**
   * Ask the user to confirm an action, in the app's own styled dialog.
   * Preserves the friction of native confirm() — the user must click Confirm.
   * @param {{title?:string, body?:string, confirmLabel?:string,
   *          cancelLabel?:string, danger?:boolean}} opts
   * @returns {Promise<boolean>} resolves true on confirm, false on cancel/dismiss.
   */
  function confirmDialog(opts) {
    opts = opts || {};
    injectStyles();
    var previousFocus = document.activeElement;

    return new Promise(function (resolve) {
      var overlay = document.createElement('div');
      overlay.className = 'rc-confirm-overlay';

      var dialog = document.createElement('div');
      dialog.className = 'rc-confirm';
      dialog.setAttribute('role', 'dialog');
      dialog.setAttribute('aria-modal', 'true');

      var head = document.createElement('div');
      head.className = 'rc-confirm-head';
      var h = document.createElement('h3');
      h.className = 'rc-confirm-title';
      h.textContent = opts.title || 'Are you sure?';
      head.appendChild(h);

      var body = document.createElement('div');
      body.className = 'rc-confirm-body';
      body.textContent = opts.body || '';

      var foot = document.createElement('div');
      foot.className = 'rc-confirm-foot';
      var cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.className = 'rc-confirm-btn rc-confirm-cancel';
      cancelBtn.textContent = opts.cancelLabel || 'Cancel';
      var okBtn = document.createElement('button');
      okBtn.type = 'button';
      okBtn.className = 'rc-confirm-btn rc-confirm-ok' + (opts.danger ? ' rc-danger' : '');
      okBtn.textContent = opts.confirmLabel || 'Confirm';
      foot.appendChild(cancelBtn);
      foot.appendChild(okBtn);

      dialog.appendChild(head);
      dialog.appendChild(body);
      dialog.appendChild(foot);
      overlay.appendChild(dialog);
      document.body.appendChild(overlay);
      var prevOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      okBtn.focus();

      function cleanup(result) {
        document.removeEventListener('keydown', onKey);
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
        document.body.style.overflow = prevOverflow;
        if (previousFocus && previousFocus.focus) previousFocus.focus();
        resolve(result);
      }
      function onKey(e) {
        if (e.key === 'Escape') cleanup(false);
        else if (e.key === 'Tab') {
          // Minimal focus trap between the two buttons.
          e.preventDefault();
          (document.activeElement === okBtn ? cancelBtn : okBtn).focus();
        }
      }
      cancelBtn.addEventListener('click', function () { cleanup(false); });
      okBtn.addEventListener('click', function () { cleanup(true); });
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) cleanup(false);
      });
      document.addEventListener('keydown', onKey);
    });
  }

  window.notify = notify;
  window.confirmDialog = confirmDialog;
})();
