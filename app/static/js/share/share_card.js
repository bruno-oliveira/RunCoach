/**
 * share_card.js — ShareCard object: modal, open/close, theme switching, format
 * selection, export actions.
 *
 * Depends on share_themes.js (window.SHARE_THEMES, SHARE_QUALITY_COLORS,
 * SHARE_WORKOUT_COLORS).
 * Rendering methods are attached by share_renderer.js.
 */
(function () {
    'use strict';

    var ShareCard = {
        /* ---------------------------------------------------------- */
        /*  Config                                                     */
        /* ---------------------------------------------------------- */
        FORMATS: {
            square: { w: 1080, h: 1080, label: 'Post' },
            story:  { w: 1080, h: 1920, label: 'Story' },
        },

        THEMES:          window.SHARE_THEMES,
        QUALITY_COLORS:  window.SHARE_QUALITY_COLORS,
        WORKOUT_COLORS:  window.SHARE_WORKOUT_COLORS,

        // Fonts (from design system, loaded via Google Fonts on the page)
        FONT_DISPLAY: '"Bricolage Grotesque", Georgia, serif',
        FONT_BODY:    '"DM Sans", sans-serif',
        FONT_MONO:    '"JetBrains Mono", monospace',

        // Current state
        _modal: null,
        _canvas: null,
        _currentRun: null,
        _currentFormat: 'square',
        _currentTheme: 'midnight',

        /** Shortcut to the active theme palette. */
        _t: function () { return this.THEMES[this._currentTheme]; },

        /* ---------------------------------------------------------- */
        /*  Public API                                                 */
        /* ---------------------------------------------------------- */

        /** Open the share modal for a given run object. */
        open: async function (runData) {
            this._currentRun = runData;
            this._currentFormat = 'square';
            this._ensureModal();
            this._modal.classList.add('share-modal--open');
            document.body.style.overflow = 'hidden';
            await document.fonts.ready;
            this._render();
        },

        close: function () {
            if (this._modal) {
                this._modal.classList.remove('share-modal--open');
                document.body.style.overflow = '';
            }
        },

        /* ---------------------------------------------------------- */
        /*  Modal DOM                                                  */
        /* ---------------------------------------------------------- */
        _ensureModal: function () {
            if (this._modal) return;

            var self = this;

            var themeButtons = Object.keys(this.THEMES).map(function (key) {
                var t = self.THEMES[key];
                var active = key === self._currentTheme ? ' share-theme-btn--active' : '';
                var swatch = t.bg[0];
                return '<button class="share-theme-btn' + active + '" data-theme="' + key + '">' +
                    '<span class="share-theme-swatch" style="background:' + swatch + '"></span>' +
                    t.label +
                '</button>';
            }).join('');

            var modal = document.createElement('div');
            modal.className = 'share-modal';
            modal.innerHTML =
                '<div class="share-modal-backdrop"></div>' +
                '<div class="share-modal-panel">' +
                    '<div class="share-modal-header">' +
                        '<h3 class="share-modal-title">Share Your Run</h3>' +
                        '<button class="share-modal-close" aria-label="Close">&times;</button>' +
                    '</div>' +
                    '<div class="share-modal-controls">' +
                        '<div class="share-modal-formats">' +
                            '<button class="share-format-btn share-format-btn--active" data-fmt="square">' +
                                '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="12" height="12" rx="1.5"/></svg>' +
                                ' Post' +
                            '</button>' +
                            '<button class="share-format-btn" data-fmt="story">' +
                                '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="1" width="8" height="14" rx="1.5"/></svg>' +
                                ' Story' +
                            '</button>' +
                        '</div>' +
                        '<div class="share-modal-themes">' + themeButtons + '</div>' +
                    '</div>' +
                    '<div class="share-modal-preview">' +
                        '<canvas id="shareCardCanvas"></canvas>' +
                    '</div>' +
                    '<div class="share-modal-actions">' +
                        '<button class="share-action-btn share-action-btn--primary" id="shareDownloadBtn">' +
                            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' +
                            ' Save Image' +
                        '</button>' +
                        '<button class="share-action-btn" id="shareCopyBtn">' +
                            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>' +
                            ' Copy' +
                        '</button>' +
                        '<button class="share-action-btn" id="shareNativeBtn" style="display:none">' +
                            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>' +
                            ' Share' +
                        '</button>' +
                    '</div>' +
                '</div>';

            document.body.appendChild(modal);
            this._modal = modal;
            this._canvas = modal.querySelector('#shareCardCanvas');

            // Bind events
            modal.querySelector('.share-modal-backdrop').addEventListener('click', function () { self.close(); });
            modal.querySelector('.share-modal-close').addEventListener('click', function () { self.close(); });

            // Format buttons
            modal.querySelectorAll('.share-format-btn').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    modal.querySelectorAll('.share-format-btn').forEach(function (b) { b.classList.remove('share-format-btn--active'); });
                    btn.classList.add('share-format-btn--active');
                    self._currentFormat = btn.dataset.fmt;
                    self._render();
                });
            });

            // Theme buttons
            modal.querySelectorAll('.share-theme-btn').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    modal.querySelectorAll('.share-theme-btn').forEach(function (b) { b.classList.remove('share-theme-btn--active'); });
                    btn.classList.add('share-theme-btn--active');
                    self._currentTheme = btn.dataset.theme;
                    self._render();
                });
            });

            modal.querySelector('#shareDownloadBtn').addEventListener('click', function () { self._download(); });
            modal.querySelector('#shareCopyBtn').addEventListener('click', function () { self._copyToClipboard(); });

            // Web Share API (mobile)
            if (navigator.canShare) {
                modal.querySelector('#shareNativeBtn').style.display = '';
                modal.querySelector('#shareNativeBtn').addEventListener('click', function () { self._nativeShare(); });
            }

            // Esc key
            document.addEventListener('keydown', function (e) {
                if (e.key === 'Escape') self.close();
            });
        },

        /* ---------------------------------------------------------- */
        /*  Export                                                     */
        /* ---------------------------------------------------------- */
        _toBlob: function () {
            var canvas = this._canvas;
            return new Promise(function (resolve) { canvas.toBlob(resolve, 'image/png'); });
        },

        _download: async function () {
            var blob = await this._toBlob();
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            var run = this._currentRun;
            var datePart = run.date ? new Date(run.date).toISOString().slice(0, 10) : 'run';
            var distPart = run.distance_km ? run.distance_km.toFixed(1) : '';
            a.href = url;
            a.download = 'runcoach-' + datePart + '-' + distPart + 'km.png';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            this._flashButton('shareDownloadBtn', 'Saved!');
        },

        _copyToClipboard: async function () {
            try {
                var blob = await this._toBlob();
                await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
                this._flashButton('shareCopyBtn', 'Copied!');
            } catch (e) {
                this._download();
            }
        },

        _nativeShare: async function () {
            try {
                var blob = await this._toBlob();
                var run = this._currentRun;
                var dist = run.distance_km ? run.distance_km.toFixed(1) : '';
                var file = new File([blob], 'runcoach-' + dist + 'km.png', { type: 'image/png' });
                await navigator.share({ title: dist + ' km run', files: [file] });
            } catch (err) {
                if (err.name !== 'AbortError') {
                    this._download();
                }
            }
        },

        _flashButton: function (id, text) {
            var btn = document.getElementById(id);
            if (!btn) return;
            var orig = btn.innerHTML;
            btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> ' + text;
            btn.classList.add('share-action-btn--success');
            setTimeout(function () {
                btn.innerHTML = orig;
                btn.classList.remove('share-action-btn--success');
            }, 2000);
        },
    };

    // Make accessible globally
    window.ShareCard = ShareCard;
})();
