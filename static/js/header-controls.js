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
        var container = document.getElementById('pending-access-notifications');
        if (!container) return;
        fetch(container.dataset.pendingUrl, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        }).then(function (response) {
            if (!response.ok) throw new Error('Não foi poss?vel consultar os acessos pendentes.');
            return response.json();
        }).then(function (payload) {
            var count = Number(payload.pending_count) || 0;
            document.getElementById('pending-access-badge').textContent = count;
            document.getElementById('pending-access-header-count').textContent = count;
            document.getElementById('pending-access-message-count').textContent = count;
            document.getElementById('pending-access-user-label').textContent = count === 1 ? 'novo usuário' : 'novos usuários';
            if (!count) return;
            document.getElementById('pending-access-badge').classList.remove('d-none');
            document.getElementById('pending-access-item').classList.remove('d-none');
            var toast = document.getElementById('pending-access-toast');
            var seenKey = 'pending-access-toast-' + count;
            if (toast && sessionStorage.getItem(seenKey) !== '1') {
                document.getElementById('pending-access-toast-title').textContent = count === 1 ? '1 liberação aguardando análise' : count + ' liberações aguardando análise';
                document.getElementById('pending-access-toast-message').textContent = count === 1 ? 'Um usuário aguarda a sua revisão de acesso.' : 'Há ' + count + ' usuários aguardando a sua revisão de acesso.';
                toast.classList.remove('d-none');
                sessionStorage.setItem(seenKey, '1');
                document.getElementById('pending-access-toast-close').addEventListener('click', function () { toast.classList.add('d-none'); });
            }
        }).catch(function (error) {
            console.warn(error.message);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        configureThemeToggle();
        configurePendingAccessAlert();
    });
})();
