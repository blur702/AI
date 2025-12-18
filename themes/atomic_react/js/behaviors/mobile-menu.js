/**
 * @file
 * Mobile menu functionality.
 *
 * Provides accessible mobile menu toggle with focus management
 * and keyboard navigation support.
 */

(function (Drupal) {
  'use strict';

  /**
   * Behavior for mobile menu.
   *
   * @type {Drupal~behavior}
   *
   * @prop {Drupal~behaviorAttach} attach
   *   Attaches the mobile menu behavior.
   */
  Drupal.behaviors.atomicReactMobileMenu = {
    attach: function (context) {
      // Only run once on the document
      if (context !== document) {
        return;
      }

      const menuToggle = document.getElementById('mobile-menu-toggle');
      const mobileMenu = document.getElementById('mobile-menu');

      if (!menuToggle || !mobileMenu) {
        return;
      }

      let isOpen = false;
      let focusTrap = null;

      /**
       * Open the mobile menu.
       */
      function openMenu() {
        isOpen = true;
        mobileMenu.hidden = false;
        menuToggle.setAttribute('aria-expanded', 'true');

        // Update icons
        const menuIcon = menuToggle.querySelector('.icon-menu');
        const closeIcon = menuToggle.querySelector('.icon-close');
        if (menuIcon) menuIcon.style.display = 'none';
        if (closeIcon) closeIcon.style.display = 'block';

        // Create focus trap
        if (Drupal.atomicReact && Drupal.atomicReact.FocusTrap) {
          focusTrap = new Drupal.atomicReact.FocusTrap(mobileMenu);
          focusTrap.activate();
        }

        // Prevent body scrolling
        document.body.style.overflow = 'hidden';

        // Announce to screen readers
        if (Drupal.announce) {
          Drupal.announce(Drupal.t('Navigation menu opened'));
        }
      }

      /**
       * Close the mobile menu.
       */
      function closeMenu() {
        isOpen = false;
        mobileMenu.hidden = true;
        menuToggle.setAttribute('aria-expanded', 'false');

        // Update icons
        const menuIcon = menuToggle.querySelector('.icon-menu');
        const closeIcon = menuToggle.querySelector('.icon-close');
        if (menuIcon) menuIcon.style.display = 'block';
        if (closeIcon) closeIcon.style.display = 'none';

        // Deactivate focus trap
        if (focusTrap) {
          focusTrap.deactivate();
          focusTrap = null;
        }

        // Restore body scrolling
        document.body.style.overflow = '';

        // Return focus to toggle button
        menuToggle.focus();

        // Announce to screen readers
        if (Drupal.announce) {
          Drupal.announce(Drupal.t('Navigation menu closed'));
        }
      }

      /**
       * Toggle the mobile menu.
       */
      function toggleMenu() {
        if (isOpen) {
          closeMenu();
        } else {
          openMenu();
        }
      }

      // Handle toggle button click
      menuToggle.addEventListener('click', toggleMenu);

      // Handle Escape key
      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && isOpen) {
          closeMenu();
        }
      });

      // Close menu when clicking outside
      mobileMenu.addEventListener('click', function (event) {
        if (event.target === mobileMenu) {
          closeMenu();
        }
      });

      // Close menu on window resize if desktop view
      let resizeTimeout;
      window.addEventListener('resize', function () {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function () {
          if (isOpen && window.innerWidth >= 1024) {
            closeMenu();
          }
        }, 100);
      });

      // Handle navigation within menu
      mobileMenu.addEventListener('click', function (event) {
        const link = event.target.closest('a');
        if (link) {
          // Close menu after navigation (for same-page links)
          if (link.getAttribute('href').startsWith('#')) {
            closeMenu();
          }
        }
      });
    }
  };

})(Drupal);
