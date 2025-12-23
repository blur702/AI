(function (Drupal) {
  'use strict';

  Drupal.behaviors.atomicReactMobileMenu = {
    attach: function (context) {
      if (context !== document) return;

      var menuToggle = document.getElementById('mobile-menu-toggle');
      var mobileMenu = document.getElementById('mobile-menu');
      if (!menuToggle || !mobileMenu) return;

      var isOpen = false;
      var focusTrap = null;

      function openMenu() {
        isOpen = true;
        mobileMenu.hidden = false;
        menuToggle.setAttribute('aria-expanded', 'true');
        var menuIcon = menuToggle.querySelector('.icon-menu');
        var closeIcon = menuToggle.querySelector('.icon-close');
        if (menuIcon) menuIcon.style.display = 'none';
        if (closeIcon) closeIcon.style.display = 'block';
        if (Drupal.atomicReact && Drupal.atomicReact.FocusTrap) {
          focusTrap = new Drupal.atomicReact.FocusTrap(mobileMenu);
          focusTrap.activate();
        }
        document.body.style.overflow = 'hidden';
        if (Drupal.announce) Drupal.announce(Drupal.t('Navigation menu opened'));
      }

      function closeMenu() {
        isOpen = false;
        mobileMenu.hidden = true;
        menuToggle.setAttribute('aria-expanded', 'false');
        var menuIcon = menuToggle.querySelector('.icon-menu');
        var closeIcon = menuToggle.querySelector('.icon-close');
        if (menuIcon) menuIcon.style.display = 'block';
        if (closeIcon) closeIcon.style.display = 'none';
        if (focusTrap) { focusTrap.deactivate(); focusTrap = null; }
        document.body.style.overflow = '';
        menuToggle.focus();
        if (Drupal.announce) Drupal.announce(Drupal.t('Navigation menu closed'));
      }

      menuToggle.addEventListener('click', function () {
        if (isOpen) closeMenu(); else openMenu();
      });

      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && isOpen) closeMenu();
      });

      window.addEventListener('resize', function () {
        if (isOpen && window.innerWidth >= 1024) closeMenu();
      });
    }
  };
})(Drupal);
