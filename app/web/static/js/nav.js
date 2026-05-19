/**
 * Navigation Component JavaScript
 * Extracted from nav.html inline script.
 *
 * Handles: theme toggle, mobile nav, scroll hide/show,
 * Strava connect/sync panel, Google Sign-In trigger.
 */

// ---- Theme toggle ----
function initThemeToggle() {
    const btn = document.getElementById('themeToggle');
    if (!btn) return;

    btn.addEventListener('click', () => {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        if (isDark) {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem('runcoach-theme', 'light');
        } else {
            document.documentElement.setAttribute('data-theme', 'dark');
            localStorage.setItem('runcoach-theme', 'dark');
        }
    });
}

function triggerGoogleSignIn() {
    if (window.google && google.accounts && google.accounts.id) {
        google.accounts.id.prompt();
    } else {
        // GSI not loaded yet — wait briefly and retry
        setTimeout(() => {
            if (window.google && google.accounts && google.accounts.id) {
                google.accounts.id.prompt();
            }
        }, 500);
    }
}

// ---- Mobile nav toggle ----
function toggleMobileNav(forceClose) {
    const navMenu  = document.getElementById('navMenu');
    const toggle   = document.getElementById('navToggle');
    const backdrop = document.getElementById('navBackdrop');
    const nav      = document.getElementById('mainNav');

    const willOpen = forceClose === true ? false : !navMenu.classList.contains('active');

    navMenu.classList.toggle('active', willOpen);
    toggle.classList.toggle('is-open', willOpen);
    toggle.setAttribute('aria-expanded', willOpen);
    document.body.style.overflow = willOpen ? 'hidden' : '';

    if (backdrop) backdrop.classList.toggle('is-active', willOpen);

    // When the menu opens, always make the nav visible again
    if (willOpen) nav.classList.remove('nav-is-hidden');
}

// Close on resize to desktop
window.addEventListener('resize', () => {
    if (window.innerWidth > 768) {
        const navMenu = document.getElementById('navMenu');
        if (navMenu.classList.contains('active')) toggleMobileNav(true);
    }
});

// Close on Escape key
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        const navMenu = document.getElementById('navMenu');
        if (navMenu.classList.contains('active')) toggleMobileNav(true);
    }
});

// ---- Scroll: hide nav on scroll-down, reveal on scroll-up ----
(function () {
    const HIDE_THRESHOLD   = 80;
    const DELTA_HIDE       = 12;
    const DELTA_SHOW       = 8;

    let lastY     = window.scrollY;
    let delta     = 0;
    let ticking   = false;

    window.addEventListener('scroll', () => {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => {
            const nav     = document.getElementById('mainNav');
            const navMenu = document.getElementById('navMenu');
            const currentY = window.scrollY;
            const diff     = currentY - lastY;

            // Never hide while the mobile menu is open
            if (!navMenu.classList.contains('active')) {
                if (currentY <= HIDE_THRESHOLD) {
                    nav.classList.remove('nav-is-hidden');
                    delta = 0;
                } else {
                    delta += diff;
                    if (delta > DELTA_HIDE) {
                        nav.classList.add('nav-is-hidden');
                        delta = 0;
                    } else if (delta < -DELTA_SHOW) {
                        nav.classList.remove('nav-is-hidden');
                        delta = 0;
                    }
                }
            }

            nav.classList.toggle('scrolled', currentY > 8);

            lastY   = currentY;
            ticking = false;
        });
    }, { passive: true });
})();

async function connectStrava() {
    try {
        const response = await fetch('/api/strava/connect');
        const data = await response.json();
        if (data.authorize_url) {
            window.location.href = data.authorize_url;
        }
    } catch (err) {
        alert('Failed to connect to Strava. Please try again.');
    }
}

// ---- Strava panel ----

function toggleStravaPanel() {
    const trigger = document.getElementById('stravaTrigger');
    const panel = document.getElementById('stravaPanel');
    if (!trigger || !panel) return;

    const isOpen = panel.classList.toggle('is-open');
    trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
}

function closeStravaPanel() {
    const trigger = document.getElementById('stravaTrigger');
    const panel = document.getElementById('stravaPanel');
    if (!trigger || !panel) return;

    panel.classList.remove('is-open');
    trigger.setAttribute('aria-expanded', 'false');
}

function formatRelativeTime(ts) {
    if (!ts) return 'Never synced';

    const tsNum = parseInt(ts, 10);
    if (isNaN(tsNum) || tsNum <= 0) return 'Never synced';

    const nowSec = Math.floor(Date.now() / 1000);
    const diffSec = nowSec - tsNum;

    if (diffSec < 60) return 'just now';
    if (diffSec < 3600) {
        const m = Math.floor(diffSec / 60);
        return m + 'm ago';
    }
    if (diffSec < 86400) {
        const h = Math.floor(diffSec / 3600);
        return h + 'h ago';
    }
    if (diffSec < 172800) return 'yesterday';
    const d = Math.floor(diffSec / 86400);
    return d + ' days ago';
}

function initStravaPanel() {
    const panel = document.getElementById('stravaPanel');
    if (!panel) return;

    // Populate "last synced" text from the data attribute
    const ts = panel.getAttribute('data-ts');
    const lastSyncedEl = document.getElementById('stravaLastSynced');
    if (lastSyncedEl) {
        lastSyncedEl.textContent = formatRelativeTime(ts);
    }

    // Close panel on outside click
    document.addEventListener('click', (e) => {
        const trigger = document.getElementById('stravaTrigger');
        if (!trigger || !panel) return;
        if (!trigger.contains(e.target) && !panel.contains(e.target)) {
            closeStravaPanel();
        }
    });

    // Close panel on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeStravaPanel();
        }
    });
}

async function doStravaSync(forceDays) {
    const syncBtn = document.getElementById('stravaSyncBtn');
    const chips = document.querySelectorAll('.strava-chip');
    const feedback = document.getElementById('stravaFeedback');
    const refreshIcon = syncBtn ? syncBtn.querySelector('.strava-refresh-icon') : null;
    const spinner = syncBtn ? syncBtn.querySelector('.strava-spinner') : null;
    const label = syncBtn ? syncBtn.querySelector('.strava-primary-label') : null;

    // Set loading state
    if (syncBtn) syncBtn.disabled = true;
    chips.forEach(c => { c.disabled = true; });
    if (refreshIcon) refreshIcon.style.display = 'none';
    if (spinner) spinner.style.display = '';
    if (label) label.textContent = 'Syncing\u2026';
    if (feedback) feedback.style.display = 'none';

    try {
        let url = '/api/strava/sync';
        if (forceDays !== null && forceDays !== undefined) {
            url += '?force_days=' + encodeURIComponent(forceDays);
        }

        const response = await fetch(url, { method: 'POST' });
        const data = await response.json();

        if (response.ok) {
            // Update "last synced" text to now
            const lastSyncedEl = document.getElementById('stravaLastSynced');
            if (lastSyncedEl) lastSyncedEl.textContent = 'just now';
            const panelEl = document.getElementById('stravaPanel');
            if (panelEl) panelEl.setAttribute('data-ts', String(Math.floor(Date.now() / 1000)));

            // Show success feedback
            const synced = data.synced || 0;
            const errorCount = (data.errors && data.errors.length) || 0;
            let message;
            if (synced === 0) {
                message = 'Already up to date.';
            } else {
                const runWord = synced === 1 ? 'run' : 'runs';
                message = synced + ' new ' + runWord + ' synced.';
            }
            if (errorCount > 0) {
                message += ' (' + errorCount + ' import error' + (errorCount > 1 ? 's' : '') + ' — check logs)';
            }
            // Show adjustment results if any plans were auto-adjusted
            if (data.adjustment_results && data.adjustment_results.length > 0) {
                const adjusted = data.adjustment_results.filter(r => r.adjusted);
                const mapped = data.adjustment_results.reduce((sum, r) => sum + (r.runs_mapped || 0), 0);
                if (mapped > 0) {
                    message += ' ' + mapped + ' run' + (mapped !== 1 ? 's' : '') + ' mapped to plan' + (data.adjustment_results.length !== 1 ? 's' : '') + '.';
                }
                if (adjusted.length > 0) {
                    message += ' ' + adjusted.length + ' plan' + (adjusted.length !== 1 ? 's' : '') + ' auto-adjusted.';
                }
            }
            if (feedback) {
                feedback.textContent = message;
                feedback.className = 'strava-feedback ' + (errorCount > 0 ? 'is-error' : 'is-success');
                feedback.style.display = '';
            }

            // Auto-hide feedback after 4 seconds
            setTimeout(() => {
                if (feedback) feedback.style.display = 'none';
            }, 4000);

            // If the analytics dashboard is open, reload so stats stay fresh
            if (window.AnalyticsDashboard && window.AnalyticsDashboard.allRuns !== undefined) {
                await window.AnalyticsDashboard.reloadRuns();
                const periodSel = document.getElementById('periodSelector');
                const period = periodSel ? periodSel.value : '30';
                window.AnalyticsDashboard.filterByPeriod(period);
            }

            // On the plan page, server-rendered cards (week pulse, readiness, logged-run
            // badges) go stale after a sync. Reload so they reflect the new runs.
            const mappedAny = (data.adjustment_results || []).some(r => (r.runs_mapped || 0) > 0);
            if ((synced > 0 || mappedAny) && window.location.pathname.startsWith('/plan/')) {
                setTimeout(() => window.location.reload(), 800);
            }
        } else {
            const detail = (data && data.detail) ? data.detail : 'Unknown error';
            if (feedback) {
                feedback.textContent = 'Sync failed: ' + detail;
                feedback.className = 'strava-feedback is-error';
                feedback.style.display = '';
            }
        }
    } catch (err) {
        if (feedback) {
            feedback.textContent = 'Failed to reach Strava. Please try again.';
            feedback.className = 'strava-feedback is-error';
            feedback.style.display = '';
        }
    } finally {
        // Restore button state
        if (syncBtn) syncBtn.disabled = false;
        chips.forEach(c => { c.disabled = false; });
        if (refreshIcon) refreshIcon.style.display = '';
        if (spinner) spinner.style.display = 'none';
        if (label) label.textContent = 'Sync new runs';
    }
}

function syncStrava() {
    doStravaSync(null);
}

function syncStravaForDays(days) {
    doStravaSync(days);
}

async function disconnectStrava() {
    if (!confirm('Disconnect Strava? This removes all stored Strava credentials. Your synced runs will be kept.')) return;

    const btn = document.getElementById('stravaDisconnectBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Disconnecting…'; }

    try {
        const res = await fetch('/api/strava/disconnect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin'
        });
        if (res.ok) {
            window.location.reload();
        } else {
            alert('Failed to disconnect Strava. Please try again.');
            if (btn) { btn.disabled = false; btn.textContent = 'Disconnect Strava'; }
        }
    } catch (err) {
        alert('Failed to disconnect Strava. Please try again.');
        if (btn) { btn.disabled = false; btn.textContent = 'Disconnect Strava'; }
    }
}

async function deleteAccount() {
    if (!confirm('Delete your account? This permanently removes all your data including plans, runs, and recipes. This cannot be undone.')) return;

    try {
        const res = await fetch('/api/auth/account', {
            method: 'DELETE',
            credentials: 'same-origin'
        });
        if (res.ok) {
            window.location.href = '/';
        } else {
            alert('Failed to delete account. Please try again.');
        }
    } catch (err) {
        alert('Failed to delete account. Please try again.');
    }
}

function openSettingsModal() {
    const overlay = document.getElementById('settingsOverlay');
    if (!overlay) return;
    overlay.classList.add('is-open');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    const toggle = document.getElementById('autoAdjustToggle');
    if (toggle) toggle.focus();
}

function closeSettingsModal() {
    const overlay = document.getElementById('settingsOverlay');
    if (!overlay) return;
    overlay.classList.remove('is-open');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    const trigger = document.getElementById('navSettingsBtn');
    if (trigger) trigger.focus();
}

function closeSettingsModalOnBackdrop(evt) {
    if (evt.target && evt.target.id === 'settingsOverlay') {
        closeSettingsModal();
    }
}

async function saveAutoAdjustSetting(enabled) {
    const toggle = document.getElementById('autoAdjustToggle');
    const feedback = document.getElementById('settingsFeedback');
    if (feedback) {
        feedback.textContent = 'Saving…';
        feedback.classList.remove('is-saved', 'is-error');
    }
    if (toggle) toggle.disabled = true;
    try {
        const res = await fetch('/api/auth/me/settings', {
            method: 'PATCH',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ auto_adjust_enabled: !!enabled }),
        });
        if (!res.ok) throw new Error('save_failed');
        const data = await res.json();
        if (toggle) toggle.checked = !!data.auto_adjust_enabled;
        if (feedback) {
            feedback.textContent = data.auto_adjust_enabled
                ? 'Auto-adjust on — weekly adjustments will apply automatically.'
                : 'Auto-adjust off — weekly adjustments will wait for your approval.';
            feedback.classList.add('is-saved');
        }
    } catch (err) {
        if (toggle) toggle.checked = !enabled;
        if (feedback) {
            feedback.textContent = 'Could not save. Please try again.';
            feedback.classList.add('is-error');
        }
    } finally {
        if (toggle) toggle.disabled = false;
    }
}

document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const overlay = document.getElementById('settingsOverlay');
    if (overlay && overlay.classList.contains('is-open')) {
        closeSettingsModal();
    }
});

document.addEventListener('DOMContentLoaded', () => {
    initThemeToggle();
    initStravaPanel();
});
