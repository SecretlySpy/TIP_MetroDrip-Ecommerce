/**
 * Persistent two-state colour theme for the MetroDrip storefront and consoles.
 *
 * Django's stock admin theme cycles through auto/light/dark and writes `auto`
 * to localStorage. The storefront understands only explicit light/dark values,
 * so merely visiting a console could make the two surfaces disagree. This
 * controller stores only the shared values both surfaces understand.
 */
(function () {
  'use strict';

  var storageKey = 'theme';
  var media = window.matchMedia('(prefers-color-scheme: dark)');

  function storedTheme() {
    try {
      var value = window.localStorage.getItem(storageKey);
      return value === 'light' || value === 'dark' ? value : null;
    } catch (_error) {
      return null;
    }
  }

  function systemTheme() {
    return media.matches ? 'dark' : 'light';
  }

  function syncControls(theme) {
    document.querySelectorAll('[data-console-theme]').forEach(function (button) {
      var selected = button.getAttribute('data-console-theme') === theme;
      button.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
  }

  function applyTheme(theme, persist) {
    var next = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    document.documentElement.style.colorScheme = next;

    if (persist) {
      try {
        window.localStorage.setItem(storageKey, next);
      } catch (_error) {
        // A private or locked-down browser can still use the selected theme
        // for this document even when persistence is unavailable.
      }
    }

    syncControls(next);
  }

  applyTheme(storedTheme() || systemTheme(), false);

  document.addEventListener('DOMContentLoaded', function () {
    syncControls(document.documentElement.getAttribute('data-theme') || systemTheme());

    document.addEventListener('click', function (event) {
      var button = event.target.closest('[data-console-theme]');
      if (!button) return;
      applyTheme(button.getAttribute('data-console-theme'), true);
    });
  });

  function followSystemPreference(event) {
    if (!storedTheme()) applyTheme(event.matches ? 'dark' : 'light', false);
  }

  if (typeof media.addEventListener === 'function') {
    media.addEventListener('change', followSystemPreference);
  } else if (typeof media.addListener === 'function') {
    media.addListener(followSystemPreference);
  }

  window.addEventListener('storage', function (event) {
    if (event.key === storageKey) applyTheme(storedTheme() || systemTheme(), false);
  });
})();
