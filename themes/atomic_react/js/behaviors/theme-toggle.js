/**
 * @file
 * Theme toggle functionality for dark/light mode.
 *
 * Provides dark mode toggle with localStorage persistence
 * and respects user's system preference.
 */

(function (Drupal) {
  'use strict';

  /**
   * Get the user's preferred color scheme.
   *
   * @return {string}
   *   The preferred theme ('light' or 'dark').
   */
  function getPreferredTheme() {
    // Check localStorage first
    const storedTheme = localStorage.getItem('atomic-react-theme');
    if (storedTheme) {
      return storedTheme;
    }

    // Fall back to system preference
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }

    return 'light';
  }

  /**
   * Apply the theme to the document.
   *
   * @param {string} theme
   *   The theme to apply ('light' or 'dark').
   */
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);

    // Update theme-color meta tag for browsers
    const themeColorMeta = document.querySelector('meta[name="theme-color"]');
    if (themeColorMeta) {
      themeColorMeta.setAttribute('content', theme === 'dark' ? '#121212' : '#1976d2');
    }
  }

  /**
   * Update toggle button appearance.
   *
   * @param {HTMLElement} toggleButton
   *   The toggle button element.
   * @param {string} theme
   *   The current theme ('light' or 'dark').
   */
  function updateToggleButton(toggleButton, theme) {
    const sunIcon = toggleButton.querySelector('.icon-sun');
    const moonIcon = toggleButton.querySelector('.icon-moon');

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

  /**
   * Behavior for theme toggle.
   *
   * @type {Drupal~behavior}
   *
   * @prop {Drupal~behaviorAttach} attach
   *   Attaches the theme toggle behavior.
   */
  Drupal.behaviors.atomicReactThemeToggle = {
    attach: function (context) {
      // Only run once on the document
      if (context !== document) {
        return;
      }

      const toggleButton = document.getElementById('theme-toggle');

      if (!toggleButton) {
        return;
      }

      // Apply initial theme
      const currentTheme = getPreferredTheme();
      applyTheme(currentTheme);
      updateToggleButton(toggleButton, currentTheme);

      // Handle toggle click
      toggleButton.addEventListener('click', function () {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

        // Apply the new theme
        applyTheme(newTheme);
        updateToggleButton(toggleButton, newTheme);

        // Store preference
        localStorage.setItem('atomic-react-theme', newTheme);

        // Announce to screen readers
        if (Drupal.announce) {
          const message = newTheme === 'dark'
            ? Drupal.t('Dark mode enabled')
            : Drupal.t('Light mode enabled');
          Drupal.announce(message);
        }
      });

      // Listen for system preference changes
      if (window.matchMedia) {
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

        mediaQuery.addEventListener('change', function (event) {
          // Only update if no stored preference
          if (!localStorage.getItem('atomic-react-theme')) {
            const newTheme = event.matches ? 'dark' : 'light';
            applyTheme(newTheme);
            updateToggleButton(toggleButton, newTheme);
          }
        });
      }
    }
  };

  // Apply theme immediately (before DOM ready) to prevent flash
  const initialTheme = getPreferredTheme();
  applyTheme(initialTheme);

})(Drupal);
