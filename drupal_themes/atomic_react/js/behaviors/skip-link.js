(function (Drupal) {
  'use strict';

  Drupal.behaviors.atomicReactSkipLink = {
    attach: function (context) {
      if (context !== document) return;

      var skipLinks = document.querySelectorAll('.skip-link');
      skipLinks.forEach(function (skipLink) {
        skipLink.addEventListener('click', function (event) {
          var targetId = skipLink.getAttribute('href');
          if (targetId && targetId.startsWith('#')) {
            var targetElement = document.querySelector(targetId);
            if (targetElement) {
              event.preventDefault();
              targetElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
              if (!targetElement.hasAttribute('tabindex')) {
                targetElement.setAttribute('tabindex', '-1');
                targetElement.addEventListener('blur', function () {
                  targetElement.removeAttribute('tabindex');
                }, { once: true });
              }
              targetElement.focus();
              if (Drupal.announce) {
                Drupal.announce(Drupal.t('Skipped to main content'));
              }
            }
          }
        });
      });

      var backToTopButton = document.getElementById('back-to-top');
      if (backToTopButton) {
        var toggleBackToTop = function () {
          if (window.scrollY > 300) {
            backToTopButton.classList.add('back-to-top--visible');
          } else {
            backToTopButton.classList.remove('back-to-top--visible');
          }
        };
        window.addEventListener('scroll', toggleBackToTop, { passive: true });
        toggleBackToTop();

        backToTopButton.addEventListener('click', function () {
          window.scrollTo({ top: 0, behavior: 'smooth' });
          var skipLink = document.querySelector('.skip-link');
          if (skipLink) skipLink.focus();
          if (Drupal.announce) {
            Drupal.announce(Drupal.t('Returned to top of page'));
          }
        });
      }
    }
  };
})(Drupal);
