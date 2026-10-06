/**
 * Authentication module for Google Sign-In
 *
 * Architecture: Server-side cookies are the single source of truth for auth state.
 * The server renders the nav with the correct logged-in/logged-out state.
 * This JS only handles:
 * 1. Initializing the Google Sign-In button (when user is not logged in)
 * 2. Processing Google's credential response and sending to server
 * 3. Logout functionality
 *
 * On successful login/logout, we reload the page to get server-rendered state.
 *
 * Two ways the credential arrives:
 *
 * - Popup (a browser tab): Google hands it to `handleCredentialResponse`.
 * - Redirect (the app installed to a home screen): an installed app cannot
 *   receive a popup's answer — on iOS the popup opens outside the app and the
 *   credential never comes back, so the button did nothing. There Google is
 *   asked to POST the credential to `/api/auth/google/redirect` instead, which
 *   renders a small relay page that finishes here in `completeRedirectSignIn`.
 *
 * Both end in `signInWithCredential`, so there is one exchange with the server.
 *
 * Staying signed in: the access token lives 15 minutes and the server cannot
 * renew it during a page load (the refresh cookie is scoped to /api/auth).
 * Nothing used to call the refresh endpoint at all, so every session ended
 * after a quarter of an hour. `renewSession` now does, on a timer while a
 * page is open and whenever one comes back into view; a page the server
 * rendered signed-out for a runner who has a session is renewed and reloaded.
 */
(function () {
    let gsiInitialized = false;

    // Where the redirect flow lands, and where it remembers to return to.
    const REDIRECT_LOGIN_PATH = '/api/auth/google/redirect';
    const RETURN_TO_KEY = 'authReturnTo';

    // localStorage, so every tab and the installed app's next launch see it.
    // The refresh cookie is HttpOnly: this hint is how the page knows a
    // session may exist without asking the server on every guest page view.
    const SESSION_HINT_KEY = 'rc_signed_in';
    const RENEWED_AT_KEY = 'rc_session_renewed_at';
    // Comfortably inside the access token's 15 minutes.
    const RENEW_EVERY_MS = 10 * 60 * 1000;
    const RENEW_CHECK_MS = 60 * 1000;
    // Another tab renewing this recently already rotated the refresh token.
    const RENEW_SETTLE_MS = 60 * 1000;
    const RENEW_RELOAD_KEY = 'rc_renew_reloaded_at';

    function readStore(store, key) {
        try { return store.getItem(key); } catch (e) { return null; }
    }

    function writeStore(store, key, value) {
        try {
            if (value === null) store.removeItem(key);
            else store.setItem(key, value);
        } catch (e) { /* private mode — renewal just runs less cleverly */ }
    }

    function hasSessionHint() {
        return readStore(localStorage, SESSION_HINT_KEY) === '1';
    }

    function msSinceRenewal() {
        const at = Number(readStore(localStorage, RENEWED_AT_KEY));
        return at ? Date.now() - at : Infinity;
    }

    function rememberSession() {
        writeStore(localStorage, SESSION_HINT_KEY, '1');
        writeStore(localStorage, RENEWED_AT_KEY, String(Date.now()));
    }

    function forgetSession() {
        writeStore(localStorage, SESSION_HINT_KEY, null);
        writeStore(localStorage, RENEWED_AT_KEY, null);
    }

    /**
     * One refresh-token exchange. Resolves true when the session is good.
     * A refresh token is single-use, so a tab that loses the race to another
     * gets a 401 for a session that is in fact alive — hence the settle check
     * on both sides of the request.
     */
    async function exchangeRefreshToken() {
        if (msSinceRenewal() < RENEW_SETTLE_MS) return true;
        let res;
        try {
            res = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin' });
        } catch (e) {
            return false;  // offline: the session may well still be there
        }
        if (res.ok) {
            rememberSession();
            return true;
        }
        if (res.status === 401 && msSinceRenewal() >= RENEW_SETTLE_MS) {
            forgetSession();
        }
        return msSinceRenewal() < RENEW_SETTLE_MS;
    }

    let renewing = null;
    /**
     * Renew the session, once at a time across this page and (where the Web
     * Locks API exists) across tabs. Resolves true when signed in afterwards.
     */
    function renewSession() {
        if (!hasSessionHint()) return Promise.resolve(false);
        if (!renewing) {
            const run = navigator.locks
                ? navigator.locks.request('rc-session-renewal', exchangeRefreshToken)
                : exchangeRefreshToken();
            renewing = Promise.resolve(run)
                .catch(() => false)
                .finally(() => { renewing = null; });
        }
        return renewing;
    }

    function renewIfDue() {
        if (!hasSessionHint() || msSinceRenewal() < RENEW_EVERY_MS) {
            return Promise.resolve(hasSessionHint());
        }
        return renewSession();
    }

    /**
     * The server rendered this page signed-out, yet the runner has a session:
     * the access token ran out while the app was closed. Renew and reload —
     * once, so a session the server will not honour cannot loop the page.
     */
    async function restoreExpiredSession() {
        const lastReload = Number(readStore(sessionStorage, RENEW_RELOAD_KEY));
        if (lastReload && Date.now() - lastReload < RENEW_SETTLE_MS) {
            forgetSession();
            return;
        }
        if (await renewSession()) {
            writeStore(sessionStorage, RENEW_RELOAD_KEY, String(Date.now()));
            // The installed app launches on /today, which bounces a signed-out
            // visitor to the home page: send them where they were going.
            if (isInstalledApp() && window.location.pathname === '/') {
                window.location.replace('/today');
            } else {
                window.location.reload();
            }
        }
    }

    function keepSessionAlive() {
        if (document.body.dataset.authed !== 'true') {
            if (hasSessionHint()) restoreExpiredSession();
            return;
        }
        // Signed in before this code shipped: adopt the session as it stands.
        if (!hasSessionHint()) writeStore(localStorage, SESSION_HINT_KEY, '1');
        renewIfDue();
        setInterval(renewIfDue, RENEW_CHECK_MS);
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') renewIfDue();
        });
    }

    function isInstalledApp() {
        return !!(window.RunCoachPWA && window.RunCoachPWA.isStandalone());
    }

    function currentPath() {
        return window.location.pathname + window.location.search;
    }

    /**
     * Exchange Google's credential for a session cookie. Throws on failure.
     */
    async function exchangeCredential(credential) {
        if (!credential) {
            throw new Error('No credential received from Google');
        }

        const res = await fetch('/api/auth/google', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id_token: credential }),
            credentials: 'same-origin'
        });

        if (!res.ok) {
            const errorData = await res.json().catch(() => ({}));
            throw new Error(errorData.detail || `HTTP ${res.status}: ${res.statusText}`);
        }

        const data = await res.json();
        if (!data || !data.user) {
            throw new Error('Invalid response from server');
        }
        rememberSession();
    }

    /**
     * Chained connect: if the user clicked a "connect your watch" affordance
     * while logged out, we stashed the intent before sign-in. Continue straight
     * into the Intervals.icu OAuth flow, so it reads as one uninterrupted
     * action. Resolves true when the browser is on its way there.
     */
    async function continuePendingConnect(returnTo) {
        let pendingConnect = null;
        try {
            pendingConnect = sessionStorage.getItem('pendingConnect');
            if (pendingConnect) sessionStorage.removeItem('pendingConnect');
        } catch (e) { /* private mode — no pending intent */ }

        if (pendingConnect !== 'intervals') return false;

        try {
            // Carry where they started from so the OAuth callback brings
            // them back here. Without it the callback falls through to
            // /my-plans, which for a brand-new runner is an empty page —
            // they'd have linked two accounts to reach "No plans yet".
            const connectRes = await fetch(
                '/api/intervals/connect?return_to=' + encodeURIComponent(returnTo),
                { credentials: 'same-origin' }
            );
            const connectData = await connectRes.json();
            if (connectData && connectData.authorize_url) {
                window.location.href = connectData.authorize_url;
                return true;
            }
        } catch (e) {
            // Fall through — they land logged in and can connect from the nav.
        }
        return false;
    }

    /**
     * Sign in with a Google credential, then show the signed-in page.
     *
     * @param {string} credential  Google ID token.
     * @param {string} returnTo    Page the runner started from.
     * @param {Function} showSignedIn  Loads the server-rendered signed-in state.
     */
    async function signInWithCredential(credential, returnTo, showSignedIn) {
        await exchangeCredential(credential);

        // Pages the service worker saved while signed out must not come back
        // as the fallback for a signed-in runner.
        if (window.RunCoachPWA) {
            await window.RunCoachPWA.onSignIn();
        }

        if (await continuePendingConnect(returnTo)) return;
        showSignedIn();
    }

    function authErrorMessage(err) {
        if (err.message.includes('HTTP 4')) {
            return 'Authentication temporarily unavailable. Please try again.';
        }
        if (err.message.includes('credential') || err.message.includes('token')) {
            return 'Authentication session expired. Please try again.';
        }
        if (err.message.includes('network') || err.message.includes('fetch')) {
            return 'Network error. Please check your connection.';
        }
        return 'Login failed: ' + err.message;
    }

    /**
     * Handle the credential response from Google Sign-In (popup flow)
     */
    async function handleCredentialResponse(response) {

        // Show loading state on the sign-in button
        const navSigninBtn = document.getElementById('nav-google-signin-button');
        if (navSigninBtn) {
            navSigninBtn.style.opacity = '0.5';
            navSigninBtn.style.pointerEvents = 'none';
        }

        try {
            // Reload page to get server-rendered authenticated state
            await signInWithCredential(
                response && response.credential,
                currentPath(),
                () => window.location.reload()
            );
        } catch (err) {
            console.error('Authentication failed:', err);
            showAuthError(authErrorMessage(err));

            // Reset button state
            if (navSigninBtn) {
                navSigninBtn.style.opacity = '1';
                navSigninBtn.style.pointerEvents = 'auto';
            }
        }
    }

    /**
     * Only ever return to a page on this site, whatever storage holds.
     */
    function safeReturnTo(path) {
        // "//host" and "/\host" both leave the site; a lone "/" never does.
        return path && /^\/(?![\/\\])/.test(path) ? path : '/';
    }

    function rememberReturnTo() {
        try {
            sessionStorage.setItem(RETURN_TO_KEY, currentPath());
        } catch (e) { /* private mode — the flow returns to the home page */ }
    }

    function takeReturnTo() {
        let path = null;
        try {
            path = sessionStorage.getItem(RETURN_TO_KEY);
            sessionStorage.removeItem(RETURN_TO_KEY);
        } catch (e) { /* private mode */ }
        return safeReturnTo(path);
    }

    /**
     * Finish the redirect flow on the relay page Google posted the credential
     * to. The exchange happens from here, same-origin, so the session and the
     * anonymous-plan hand-over work exactly as they do for the popup.
     */
    async function completeRedirectSignIn(relay) {
        const returnTo = takeReturnTo();
        try {
            await signInWithCredential(
                relay.dataset.credential,
                returnTo,
                () => window.location.replace(returnTo)
            );
        } catch (err) {
            console.error('Authentication failed:', err);
            relay.querySelector('[data-relay-status]').textContent = authErrorMessage(err);
            relay.querySelector('[data-relay-back]').hidden = false;
        }
    }

    /**
     * Display an authentication error message
     */
    function showAuthError(message) {
        // Remove any existing error
        const existingError = document.getElementById('auth-error');
        if (existingError) {
            existingError.remove();
        }

        const errorDiv = document.createElement('div');
        errorDiv.id = 'auth-error';
        errorDiv.style.cssText = 'background: #fee2e2; color: #991b1b; padding: 0.75rem 1rem; border-radius: 6px; margin: 0.5rem 0; border-left: 4px solid #ef4444; font-size: 0.9rem;';
        const strong = document.createElement('strong');
        strong.textContent = 'Error: ';
        errorDiv.appendChild(strong);
        errorDiv.appendChild(document.createTextNode(message));

        // Insert near the sign-in button
        const navAuth = document.querySelector('.nav-auth');
        if (navAuth) {
            navAuth.appendChild(errorDiv);
            // Auto-remove after 5 seconds
            setTimeout(() => errorDiv.remove(), 5000);
        }
    }

    /**
     * Render the Google Sign-In button
     */
    function renderButton() {
        const navContainer = document.getElementById('nav-google-signin-button');

        if (!navContainer) {
            // No sign-in button container - user is likely already logged in
            return;
        }

        try {
            navContainer.innerHTML = '';
            google.accounts.id.renderButton(
                navContainer, Object.assign({ size: 'medium', width: 200 }, GSI_BUTTON_OPTIONS)
            );
        } catch (e) {
            console.error('Failed to render sign-in button:', e);
            navContainer.innerHTML = '<span style="color: #6b7280; font-size: 0.85rem;">Sign-in unavailable</span>';
        }
    }

    const GSI_BUTTON_OPTIONS = {
        type: 'standard',
        theme: 'outline',
        shape: 'rectangular',
        text: 'signin_with',
        logo_alignment: 'left'
    };

    function closeSignInSheet() {
        const sheet = document.getElementById('signin-sheet');
        if (sheet) sheet.remove();
    }

    /**
     * In the installed app, every "Sign in" affordance opens this sheet.
     *
     * They used to call Google's One Tap prompt, which an installed app cannot
     * complete and which Google stops showing after a dismissal — so the tab
     * bar's Sign in did nothing at all. Only a tap on Google's own button can
     * start the redirect flow, so the sheet puts that button in reach.
     *
     * @returns {boolean} false when not installed (the caller keeps its flow).
     */
    function openInstalledAppSignIn() {
        if (!isInstalledApp() || !gsiInitialized) return false;
        closeSignInSheet();

        const sheet = document.createElement('div');
        sheet.id = 'signin-sheet';
        sheet.className = 'signin-sheet';
        sheet.setAttribute('role', 'dialog');
        sheet.setAttribute('aria-modal', 'true');
        sheet.setAttribute('aria-label', 'Sign in');
        sheet.addEventListener('click', (event) => {
            if (event.target === sheet) closeSignInSheet();
        });

        const panel = document.createElement('div');
        panel.className = 'signin-sheet-panel';
        const title = document.createElement('p');
        title.className = 'signin-sheet-title';
        title.textContent = 'Sign in to RunCoach';
        const button = document.createElement('div');
        button.className = 'signin-sheet-button';
        const cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.className = 'signin-sheet-cancel';
        cancel.textContent = 'Not now';
        cancel.addEventListener('click', closeSignInSheet);

        panel.append(title, button, cancel);
        sheet.appendChild(panel);
        document.body.appendChild(sheet);

        google.accounts.id.renderButton(
            button, Object.assign({ size: 'large', width: 280 }, GSI_BUTTON_OPTIONS)
        );
        return true;
    }

    /**
     * Initialize Google Sign-In
     */
    function initGoogleSignIn() {
        if (gsiInitialized) return;

        // Check if sign-in button exists (only rendered for logged-out users)
        const navContainer = document.getElementById('nav-google-signin-button');
        if (!navContainer) {
            return;
        }

        const clientId = window.googleClientId;

        // Validate client ID
        const isInvalidClientId = !clientId ||
                                  clientId === 'null' ||
                                  clientId === '' ||
                                  /your-/.test(clientId) ||
                                  /placeholder/.test(clientId) ||
                                  clientId.length < 20;

        if (isInvalidClientId) {
            console.warn('Google Client ID not configured');
            navContainer.innerHTML = '<span style="color: #92400e; font-size: 0.85rem;">Sign-in not configured</span>';
            return;
        }

        // Wait for Google Identity Services to load
        if (!(window.google && google.accounts && google.accounts.id)) {
            return;
        }

        const options = {
            client_id: clientId,
            callback: handleCredentialResponse,
            ux_mode: 'popup',
            auto_select: false
        };
        if (isInstalledApp()) {
            options.ux_mode = 'redirect';
            options.login_uri = window.location.origin + REDIRECT_LOGIN_PATH;
            rememberReturnTo();
        }
        google.accounts.id.initialize(options);

        renderButton();
        gsiInitialized = true;
    }

    /**
     * Wait for Google Identity Services script to load
     */
    function waitForGsiAndInit() {
        if (gsiInitialized) return;

        let attempts = 0;
        const maxAttempts = 50;
        const timer = setInterval(() => {
            attempts++;
            if (window.google && google.accounts && google.accounts.id) {
                clearInterval(timer);
                initGoogleSignIn();
            } else if (attempts >= maxAttempts) {
                clearInterval(timer);
                console.error('Google Sign-In script failed to load');
            }
        }, 100);
    }

    /**
     * Logout function - clears server cookie and reloads
     */
    window.logout = async function () {
        if (window.isLoggingOut) {
            return;
        }

        window.isLoggingOut = true;

        // Show loading state on logout button
        const logoutBtns = document.querySelectorAll('.nav-logout-btn, .logout-btn');
        logoutBtns.forEach(btn => {
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Signing out...';
            }
        });

        // Before the session goes: unsubscribing this device needs it, and the
        // cached plan pages must not outlive the runner they belong to.
        if (window.RunCoachPWA) {
            try {
                await window.RunCoachPWA.onSignOut();
            } catch (e) {
                console.warn('Push/offline cleanup on sign-out failed:', e);
            }
        }

        try {
            // Call server to clear the cookie
            await fetch('/api/auth/logout', {
                method: 'POST',
                credentials: 'same-origin'
            });
        } catch (err) {
            console.error('Server logout failed:', err);
        }

        forgetSession();

        // Clear Google Sign-In state
        if (window.google?.accounts?.id) {
            try {
                google.accounts.id.disableAutoSelect();
                google.accounts.id.cancel();
            } catch (e) {
                console.warn('Failed to clear Google Sign-In state:', e);
            }
        }

        window.isLoggingOut = false;

        // Reload page to get server-rendered logged-out state
        // If already on home, just reload. Otherwise redirect to home.
        if (window.location.pathname === '/') {
            window.location.reload();
        } else {
            window.location.href = '/';
        }
    };

    // Initialize on DOM ready
    document.addEventListener('DOMContentLoaded', () => {
        const relay = document.getElementById('auth-relay');
        if (relay) {
            if (relay.dataset.credential) completeRedirectSignIn(relay);
            return;
        }
        keepSessionAlive();
        initGoogleSignIn();
        waitForGsiAndInit();
    });

    window.RunCoachAuth = {
        renewIfDue: renewIfDue,
        openInstalledAppSignIn: openInstalledAppSignIn,
    };

    // Retry initialization on window load (in case GSI wasn't ready)
    window.addEventListener('load', () => {
        if (!gsiInitialized) {
            initGoogleSignIn();
        }
    });
})();
