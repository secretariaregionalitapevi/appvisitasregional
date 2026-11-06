(function () {
    'use strict';

    function configureThemeToggle() {
        var button = document.getElementById('header-theme-toggle');
        var checkbox = document.getElementById('appThemeDarkMode');
        if (!button || !checkbox) return;

        function refreshIcon() {
            var dark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
            button.querySelector('i').className = dark ? 'fa fa-sun' : 'fa fa-moon';
            button.title = dark ? 'Ativar modo claro' : 'Ativar modo escuro';
            button.setAttribute('aria-label', button.title);
        }

        button.addEventListener('click', function () {
            checkbox.click();
            window.setTimeout(refreshIcon, 0);
        });
        window.addEventListener('theme-reload', refreshIcon);
        refreshIcon();
    }

    function configurePendingAccessAlert() {
        const container = document.getElementById('pending-access-notifications');
        if (!container) return;
        const el = id => document.getElementById(id);
        let running = false;
        async function count(url) {
            if (!url) return 0;
            const response = await fetch(url, {credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}});
            if (!response.ok || response.redirected) return 0;
            return Number((await response.json()).pending_count) || 0;
        }
        async function refresh() {
            if (running || document.hidden) return;
            running = true;
            try {
                const results = await Promise.allSettled([count(container.dataset.pendingUrl), count(container.dataset.lettersUrl)]);
                const [access, letters] = results.map(r => r.status === 'fulfilled' ? r.value : 0);
                const total = access + letters;
                el('pending-access-badge').textContent = total;
                el('pending-access-header-count').textContent = total;
                el('pending-access-badge').classList.toggle('d-none', !total);
                el('notifications-empty').classList.toggle('d-none', !!total);
                if (el('pending-access-item')) {
                    el('pending-access-item').classList.toggle('d-none', !access);
                    el('pending-access-message-count').textContent = access;
                    el('pending-access-user-label').textContent = access === 1 ? 'novo usuário' : 'novos usuários';
                }
                el('pending-letters-item').classList.toggle('d-none', !letters);
                el('pending-letters-count').textContent = letters;
                const key = 'pending-notifications-' + access + '-' + letters;
                const toast = el('pending-access-toast');
                if (!total) toast.classList.add('d-none');
                let seen = false;
                try { seen = sessionStorage.getItem(key) === '1'; } catch (_) {}
                if (total && !seen) {
                    el('pending-access-toast-title').textContent = letters ? letters + (letters === 1 ? ' carta pendente de análise' : ' cartas pendentes de análise') : access + (access === 1 ? ' liberação aguardando análise' : ' liberações aguardando análise');
                    el('pending-access-toast-message').textContent = letters ? 'Situação GEM/SAM: aluno inativo ou com status Excluir. Consulte as pendências no sino.' : 'Há usuários aguardando a sua revisão de acesso.';
                    el('pending-toast-link').href = letters ? el('pending-letters-item').href : el('pending-access-item').href;
                    toast.classList.remove('d-none');
                    try { sessionStorage.setItem(key, '1'); } catch (_) {}
                }
            } finally { running = false; }
        }
        el('pending-access-toast-close').addEventListener('click', () => el('pending-access-toast').classList.add('d-none'));
        container.addEventListener('click', e => { if (e.target.closest('[data-bs-toggle=dropdown]')) el('pending-access-toast').classList.add('d-none'); });
        refresh();
        window.setInterval(refresh, 60000);
        window.addEventListener('letters-updated', refresh);
    }

    document.addEventListener('DOMContentLoaded', function () {
        configureThemeToggle();
        configurePendingAccessAlert();
    });
})();
