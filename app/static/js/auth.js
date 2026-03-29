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
 */
(function () {
    let gsiInitialized = false;

    /**
     * Handle the credential response from Google Sign-In
     */
    async function handleCredentialResponse(response) {
        console.log('Google credential received, authenticating...');

        // Show loading state on the sign-in button
        const navSigninBtn = document.getElementById('nav-google-signin-button');
        if (navSigninBtn) {
            navSigninBtn.style.opacity = '0.5';
            navSigninBtn.style.pointerEvents = 'none';
        }

        try {
            if (!response || !response.credential) {
                throw new Error('No credential received from Google');
            }

            const res = await fetch('/api/auth/google', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id_token: response.credential }),
                credentials: 'same-origin'
            });

            if (!res.ok) {
                const errorData = await res.json().catch(() => ({}));
                throw new Error(errorData.detail || `HTTP ${res.status}: ${res.statusText}`);
            }

            const data = await res.json();

            if (!data || !data.access_token || !data.user) {
                throw new Error('Invalid response from server');
            }

            console.log('Login successful, reloading page...');
            // Reload page to get server-rendered authenticated state
            window.location.reload();

        } catch (err) {
            console.error('Authentication failed:', err);

            // Determine user-friendly error message
            let errorMsg;
            if (err.message.includes('HTTP 4')) {
                errorMsg = 'Authentication temporarily unavailable. Please try again.';
            } else if (err.message.includes('credential') || err.message.includes('token')) {
                errorMsg = 'Authentication session expired. Please try again.';
            } else if (err.message.includes('network') || err.message.includes('fetch')) {
                errorMsg = 'Network error. Please check your connection.';
            } else {
                errorMsg = 'Login failed: ' + err.message;
            }

            // Show error message
            showAuthError(errorMsg);

            // Reset button state
            if (navSigninBtn) {
                navSigninBtn.style.opacity = '1';
                navSigninBtn.style.pointerEvents = 'auto';
            }
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
            google.accounts.id.renderButton(navContainer, {
                type: 'standard',
                theme: 'outline',
                size: 'medium',
                width: 200,
                shape: 'rectangular',
                text: 'signin_with',
                logo_alignment: 'left'
            });
            console.log('Google Sign-In button rendered');
        } catch (e) {
            console.error('Failed to render sign-in button:', e);
            navContainer.innerHTML = '<span style="color: #6b7280; font-size: 0.85rem;">Sign-in unavailable</span>';
        }
    }

    /**
     * Initialize Google Sign-In
     */
    function initGoogleSignIn() {
        if (gsiInitialized) return;

        // Check if sign-in button exists (only rendered for logged-out users)
        const navContainer = document.getElementById('nav-google-signin-button');
        if (!navContainer) {
            console.log('User is logged in, skipping Google Sign-In init');
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

        google.accounts.id.initialize({
            client_id: clientId,
            callback: handleCredentialResponse,
            ux_mode: 'popup',
            auto_select: false
        });

        renderButton();
        gsiInitialized = true;
        console.log('Google Sign-In initialized');
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
        console.log('Logging out...');

        // Show loading state on logout button
        const logoutBtns = document.querySelectorAll('.nav-logout-btn, .logout-btn');
        logoutBtns.forEach(btn => {
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Signing out...';
            }
        });

        try {
            // Call server to clear the cookie
            await fetch('/api/auth/logout', {
                method: 'POST',
                credentials: 'same-origin'
            });
            console.log('Server logout successful');
        } catch (err) {
            console.error('Server logout failed:', err);
        }

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
        console.log('Initializing auth...');
        initGoogleSignIn();
        waitForGsiAndInit();
    });

    // Retry initialization on window load (in case GSI wasn't ready)
    window.addEventListener('load', () => {
        if (!gsiInitialized) {
            initGoogleSignIn();
        }
    });
})();
