(function (window, document) {
    'use strict';
    function digits(value) {
        let result = String(value || '').replace(/\D/g, '');
        if ((result.length === 12 || result.length === 13) && result.startsWith('55')) result = result.slice(2);
        return result.slice(0, 11);
    }
    function format(value, partial) {
        const original = String(value || '').trim(), number = digits(value);
        if (!number) return '';
        if (number.length === 11) return `(${number.slice(0, 2)}) ${number[2]} ${number.slice(3, 7)}-${number.slice(7)}`;
        if (number.length === 10) return `(${number.slice(0, 2)}) ${number.slice(2, 6)}-${number.slice(6)}`;
        if (!partial) return original;
        if (number.length <= 2) return number.length === 2 ? `(${number})` : `(${number}`;
        const local = number.slice(2), prefix = `(${number.slice(0, 2)}) `;
        if (local.length <= 4) return prefix + local;
        if (local.length <= 8) return prefix + local.slice(0, 4) + '-' + local.slice(4);
        return prefix + local[0] + ' ' + local.slice(1, 5) + (local.length > 5 ? '-' + local.slice(5, 9) : '');
    }
    function prepare(input) {
        const identity = `${input.id || ''} ${input.name || ''} ${input.dataset.field || ''}`.toLowerCase();
        if (input.dataset.phoneReady || !(input.matches('input[type="tel"], input[data-phone]') || /telefone|celular|whatsapp|fone|phone/.test(identity))) return;
        input.dataset.phoneReady = 'true'; input.type = 'tel'; input.inputMode = 'numeric'; input.maxLength = 16;
        input.autocomplete = input.autocomplete || 'tel-national'; input.placeholder = input.placeholder || '(11) 9 1234-5678';
        input.value = format(input.value, false);
        input.addEventListener('input', function () { this.value = format(this.value, true); });
        input.addEventListener('blur', function () { this.value = format(this.value, false); });
    }
    function prepareAll(root) {
        if (root instanceof HTMLInputElement) prepare(root);
        if (root.querySelectorAll) root.querySelectorAll('input').forEach(prepare);
    }
    window.formatBrazilianPhone = format; window.brazilianPhoneDigits = digits;
    document.addEventListener('DOMContentLoaded', function () {
        prepareAll(document);
        new MutationObserver(function (mutations) { mutations.forEach(function (mutation) { mutation.addedNodes.forEach(function (node) { if (node.nodeType === Node.ELEMENT_NODE) prepareAll(node); }); }); }).observe(document.body, {childList: true, subtree: true});
    });
})(window, document);
