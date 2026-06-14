/**
 * i18n.js — RunCoach internationalisation
 *
 * Supported locales: en (English / UK), pt (Portuguese)
 *
 * Usage:
 *   Any element with a [data-i18n="key"] attribute will have its
 *   textContent replaced when the language is switched.
 *
 *   Any element with [data-i18n-placeholder="key"] will have its
 *   placeholder attribute replaced.
 *
 *   Any element with [data-i18n-aria="key"] will have its aria-label replaced.
 *
 * The current language is stored in localStorage under 'runcoach-lang'.
 * Defaults to 'en'.
 */

window.RC_I18N = (function () {

    // -----------------------------------------------------------------------
    // Translation catalogue
    // -----------------------------------------------------------------------
    const TRANSLATIONS = {
        en: {
            // ---- Nav ----
            'nav.home':          'Home',
            'nav.recipes':       'Recipes',
            'nav.my_plans':      'My Plans',
            'nav.coach_hub':     'Coach Hub',
            'nav.race_prep':     'Race Prep',
            'nav.strava':        'Strava',
            'nav.settings':      'Settings',
            'nav.sign_out':      'Sign Out',
            'nav.delete_account':'Delete Account',
            'nav.connect_strava':'Connect Strava',
            'nav.sync_runs':     'Sync new runs',
            'nav.disconnect_strava': 'Disconnect Strava',
            'nav.connected':     'Connected',
            'nav.yesterday':     'Yesterday',
            'nav.last_7':        'Last 7 days',
            'nav.last_30':       'Last 30 days',
            'nav.fetch_older':   'Fetch older runs',
            'nav.connection':    'Connection',
            'nav.sign_in_google': 'Sign in with Google',

            // ---- Footer ----
            'footer.privacy':    'Privacy',

            // ---- Cookie banner ----
            'cookie.text':       'RunCoach uses strictly necessary cookies for authentication and session management, and collects health-related data (training, readiness) to personalize your plans. See our',
            'cookie.privacy_link': 'Privacy Policy',
            'cookie.accept':     'Accept',
            'cookie.decline':    'Decline non-essential',

            // ---- Settings modal ----
            'settings.title':    'Settings',
            'settings.auto_adjust_label':  'Apply weekly adjustments automatically',
            'settings.auto_adjust_help':   'Once per week, after a training week wraps up, RunCoach evaluates your runs and reshapes the remaining weeks. With this on, the change is applied immediately. With it off, you\'ll see a recommendation and decide.',
            'settings.done':     'Done',

            // ---- Home page ----
            'home.badge':        'Free personalized training',
            'home.title_1':      'Train smarter.',
            'home.title_2':      'Run stronger.',
            'home.subtitle':     'Get a training plan built around your fitness level, race goal, and schedule. Backed by proven progression principles.',
            'home.feat_mileage': 'Progressive weekly mileage',
            'home.feat_nutrition': 'Nutrition & strength guidance',
            'home.feat_adaptive': 'Adaptive to your performance',
            'home.feat_pdf':     'Download as PDF',
            'home.form_title':   'Create your plan',
            'home.form_desc':    'Fill in your details to get started',

            // ---- Recipes page ----
            'recipes.title':     'Recipes',
            'recipes.subtitle':  'Fuel your training with runner-friendly meals',

            // ---- My Plans ----
            'plans.title':       'My Plans',
            'plans.empty':       'No plans yet. Create your first plan on the home page.',

            // ---- Lang toggle aria ----
            'lang.toggle_pt':    'Switch to Portuguese',
            'lang.toggle_en':    'Switch to English',
        },

        pt: {
            // ---- Nav ----
            'nav.home':          'Início',
            'nav.recipes':       'Receitas',
            'nav.my_plans':      'Os Meus Planos',
            'nav.coach_hub':     'Centro do Treinador',
            'nav.race_prep':     'Preparação de Corrida',
            'nav.strava':        'Strava',
            'nav.settings':      'Definições',
            'nav.sign_out':      'Terminar Sessão',
            'nav.delete_account':'Apagar Conta',
            'nav.connect_strava':'Ligar Strava',
            'nav.sync_runs':     'Sincronizar corridas',
            'nav.disconnect_strava': 'Desligar Strava',
            'nav.connected':     'Ligado',
            'nav.yesterday':     'Ontem',
            'nav.last_7':        'Últimos 7 dias',
            'nav.last_30':       'Últimos 30 dias',
            'nav.fetch_older':   'Buscar corridas anteriores',
            'nav.connection':    'Ligação',
            'nav.sign_in_google': 'Entrar com Google',

            // ---- Footer ----
            'footer.privacy':    'Privacidade',

            // ---- Cookie banner ----
            'cookie.text':       'O RunCoach utiliza cookies estritamente necessários para autenticação e gestão de sessão, e recolhe dados relacionados com saúde (treino, prontidão) para personalizar os seus planos. Consulte a nossa',
            'cookie.privacy_link': 'Política de Privacidade',
            'cookie.accept':     'Aceitar',
            'cookie.decline':    'Recusar não essenciais',

            // ---- Settings modal ----
            'settings.title':    'Definições',
            'settings.auto_adjust_label':  'Aplicar ajustes semanais automaticamente',
            'settings.auto_adjust_help':   'Uma vez por semana, após o término de uma semana de treino, o RunCoach avalia as suas corridas e reformula as semanas restantes. Com esta opção ativa, a alteração é aplicada imediatamente. Com ela desativa, verá uma recomendação e decidirá.',
            'settings.done':     'Concluído',

            // ---- Home page ----
            'home.badge':        'Treino personalizado gratuito',
            'home.title_1':      'Treina de forma inteligente.',
            'home.title_2':      'Corre mais forte.',
            'home.subtitle':     'Obtenha um plano de treino adaptado ao seu nível de forma, objetivo de corrida e horário. Baseado em princípios de progressão comprovados.',
            'home.feat_mileage': 'Quilometragem semanal progressiva',
            'home.feat_nutrition': 'Orientação nutricional e de força',
            'home.feat_adaptive': 'Adaptativo ao seu desempenho',
            'home.feat_pdf':     'Transferir como PDF',
            'home.form_title':   'Crie o seu plano',
            'home.form_desc':    'Preencha os seus dados para começar',

            // ---- Recipes page ----
            'recipes.title':     'Receitas',
            'recipes.subtitle':  'Alimente o seu treino com refeições para corredores',

            // ---- My Plans ----
            'plans.title':       'Os Meus Planos',
            'plans.empty':       'Sem planos ainda. Crie o seu primeiro plano na página inicial.',

            // ---- Lang toggle aria ----
            'lang.toggle_pt':    'Mudar para Português',
            'lang.toggle_en':    'Mudar para Inglês',
        }
    };

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    const STORAGE_KEY = 'runcoach-lang';
    const DEFAULT_LANG = 'en';
    let _currentLang = DEFAULT_LANG;

    // -----------------------------------------------------------------------
    // Public API
    // -----------------------------------------------------------------------

    /** Return the translation for key in the current (or specified) locale. */
    function t(key, lang) {
        const locale = lang || _currentLang;
        const catalogue = TRANSLATIONS[locale] || TRANSLATIONS[DEFAULT_LANG];
        return catalogue[key] || TRANSLATIONS[DEFAULT_LANG][key] || key;
    }

    /** Return the active language code ('en' | 'pt'). */
    function getLang() {
        return _currentLang;
    }

    /**
     * Switch language, persist to localStorage, and apply to DOM.
     * @param {string} lang  'en' | 'pt'
     */
    function setLang(lang) {
        if (!TRANSLATIONS[lang]) {
            console.warn('[i18n] Unknown locale:', lang);
            return;
        }
        _currentLang = lang;
        localStorage.setItem(STORAGE_KEY, lang);
        applyTranslations();
        _updateToggleUI();
        document.documentElement.setAttribute('lang', lang === 'pt' ? 'pt' : 'en');
    }

    /** Toggle between 'en' and 'pt'. */
    function toggleLang() {
        setLang(_currentLang === 'en' ? 'pt' : 'en');
    }

    /**
     * Walk the DOM and replace textContent / placeholder / aria-label for
     * all elements that carry [data-i18n*] attributes.
     */
    function applyTranslations() {
        // text content
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            el.textContent = t(key);
        });

        // placeholder attributes (inputs)
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            el.placeholder = t(el.getAttribute('data-i18n-placeholder'));
        });

        // aria-label attributes
        document.querySelectorAll('[data-i18n-aria]').forEach(el => {
            el.setAttribute('aria-label', t(el.getAttribute('data-i18n-aria')));
        });
    }

    /**
     * Initialise from localStorage and apply on first load.
     * Call this once the DOM is ready.
     */
    function init() {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved && TRANSLATIONS[saved]) {
            _currentLang = saved;
        }
        applyTranslations();
        document.documentElement.setAttribute('lang', _currentLang === 'pt' ? 'pt' : 'en');
        _updateToggleUI();
    }

    // -----------------------------------------------------------------------
    // Internal helpers
    // -----------------------------------------------------------------------

    /** Update the flag widget to reflect the active language. */
    function _updateToggleUI() {
        const ptFlag = document.getElementById('langFlagPT');
        const enFlag = document.getElementById('langFlagEN');
        if (!ptFlag || !enFlag) return;

        if (_currentLang === 'pt') {
            ptFlag.classList.add('lang-flag--active');
            enFlag.classList.remove('lang-flag--active');
            ptFlag.setAttribute('aria-pressed', 'true');
            enFlag.setAttribute('aria-pressed', 'false');
        } else {
            enFlag.classList.add('lang-flag--active');
            ptFlag.classList.remove('lang-flag--active');
            enFlag.setAttribute('aria-pressed', 'true');
            ptFlag.setAttribute('aria-pressed', 'false');
        }
    }

    // -----------------------------------------------------------------------
    // Expose
    // -----------------------------------------------------------------------
    return { t, getLang, setLang, toggleLang, applyTranslations, init };

})();
