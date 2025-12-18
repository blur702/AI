/**
 * @file
 * Skip link functionality for keyboard navigation.
 *
 * Provides smooth scrolling to main content and proper focus management
 * for skip link functionality.
 */

(function (Drupal) {
  'use strict';

  /**
   * Behavior for handling skip link interactions.
   *
   * @type {Drupal~behavior}
   *
   * @prop {Drupal~behaviorAttach} attach
   *   Attaches the skip link behavior.
   */
  Drupal.behaviors.atomicReactSkipLink = {
    attach: function (context) {
      // Only run once on the document
      if (context !== document) {
        return;
      }

      const skipLinks = document.querySelectorAll('.skip-link');

      skipLinks.forEach(function (skipLink) {
        skipLink.addEventListener('click', function (event) {
          const targetId = skipLink.getAttribute('href');

          if (targetId && targetId.startsWith('#')) {
            const targetElement = document.querySelector(targetId);

            if (targetElement) {
              event.preventDefault();

              // Scroll to the target element
              targetElement.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
              });

              // Set focus to the target element
              // If the element isn't focusable, make it focusable temporarily
              if (!targetElement.hasAttribute('tabindex')) {
                targetElement.setAttribute('tabindex', '-1');

                // Remove tabindex after blur to maintain natural tab order
                targetElement.addEventListener('blur', function () {
                  targetElement.removeAttribute('tabindex');
                }, { once: true });
              }

              targetElement.focus();

              // Announce to screen readers
              if (Drupal.announce) {
                Drupal.announce(Drupal.t('Skipped to main content'));
              }
            }
          }
        });
      });

      // Handle back-to-top button
      const backToTopButton = document.getElementById('back-to-top');

      if (backToTopButton) {
        // Show/hide based on scroll position
        const toggleBackToTop = function () {
          if (window.scrollY > 300) {
            backToTopButton.classList.add('back-to-top--visible');
          } else {
            backToTopButton.classList.remove('back-to-top--visible');
          }
        };

        // Use passive event listener for better scroll performance
        window.addEventListener('scroll', toggleBackToTop, { passive: true });

        // Initial check
        toggleBackToTop();

        // Handle click
        backToTopButton.addEventListener('click', function () {
          // Scroll to top
          window.scrollTo({
            top: 0,
            behavior: 'smooth'
          });

          // Focus on skip link or first focusable element
          const skipLink = document.querySelector('.skip-link');
          if (skipLink) {
            skipLink.focus();
          }

          // Announce to screen readers
          if (Drupal.announce) {
            Drupal.announce(Drupal.t('Returned to top of page'));
          }
        });
      }
    }
  };

})(Drupal);
