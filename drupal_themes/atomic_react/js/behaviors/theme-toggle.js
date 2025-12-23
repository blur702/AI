(function (Drupal) {
  'use strict';

  function getPreferredTheme() {
    var storedTheme = localStorage.getItem('atomic-react-theme');
    if (storedTheme) return storedTheme;
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    var themeColorMeta = document.querySelector('meta[name="theme-color"]');
    if (themeColorMeta) {
      themeColorMeta.setAttribute('content', theme === 'dark' ? '#121212' : '#1976d2');
    }
  }

  function updateToggleButton(toggleButton, theme) {
    var sunIcon = toggleButton.querySelector('.icon-sun');
    var moonIcon = toggleButton.querySelector('.icon-moon');
    if (sunIcon && moonIcon) {
      if (theme === 'dark') {
        sunIcon.style.display = 'none';
        moonIcon.style.display = 'block';
        toggleButton.setAttribute('aria-label', Drupal.t('Switch to light mode'));
      } else {
        sunIcon.style.display = 'block';
        moonIcon.style.display = 'none';
        toggleButton.setAttribute('aria-label', Drupal.t('Switch to dark mode'));
      }
    }
  }

  Drupal.behaviors.atomicReactThemeToggle = {
    attach: function (context) {
      if (context !== document) return;
      var toggleButton = document.getElementById('theme-toggle');
      if (!toggleButton) return;

      var currentTheme = getPreferredTheme();
      applyTheme(currentTheme);
      updateToggleButton(toggleButton, currentTheme);

      toggleButton.addEventListener('click', function () {
        var current = document.documentElement.getAttribute('data-theme') || 'light';
        var newTheme = current === 'dark' ? 'light' : 'dark';
        applyTheme(newTheme);
        updateToggleButton(toggleButton, newTheme);
        localStorage.setItem('atomic-react-theme', newTheme);
        if (Drupal.announce) {
          Drupal.announce(newTheme === 'dark' ? Drupal.t('Dark mode enabled') : Drupal.t('Light mode enabled'));
        }
      });

      if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (event) {
          if (!localStorage.getItem('atomic-react-theme')) {
            var newTheme = event.matches ? 'dark' : 'light';
            applyTheme(newTheme);
            updateToggleButton(toggleButton, newTheme);
          }
        });
      }
    }
  };

  var initialTheme = getPreferredTheme();
  applyTheme(initialTheme);
})(Drupal);
