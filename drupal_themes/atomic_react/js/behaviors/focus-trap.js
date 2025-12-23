(function (Drupal) {
  'use strict';

  var FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

  function getFocusableElements(container) {
    return Array.from(container.querySelectorAll(FOCUSABLE)).filter(function (el) {
      return !!(el.offsetWidth || el.offsetHeight);
    });
  }

  function FocusTrap(container) {
    this.container = container;
    this.previouslyFocused = null;
    this.handleKeyDown = this.handleKeyDown.bind(this);
  }

  FocusTrap.prototype.activate = function () {
    this.previouslyFocused = document.activeElement;
    document.addEventListener('keydown', this.handleKeyDown);
    var focusable = getFocusableElements(this.container);
    if (focusable.length > 0) {
      focusable[0].focus();
    } else {
      this.container.setAttribute('tabindex', '-1');
      this.container.focus();
    }
    document.body.classList.add('dialog-open');
  };

  FocusTrap.prototype.deactivate = function () {
    document.removeEventListener('keydown', this.handleKeyDown);
    document.body.classList.remove('dialog-open');
    if (this.previouslyFocused && typeof this.previouslyFocused.focus === 'function') {
      this.previouslyFocused.focus();
    }
  };

  FocusTrap.prototype.handleKeyDown = function (event) {
    if (event.key !== 'Tab') return;
    var focusable = getFocusableElements(this.container);
    if (focusable.length === 0) { event.preventDefault(); return; }
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey) {
      if (document.activeElement === first) { event.preventDefault(); last.focus(); }
    } else {
      if (document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  };

  Drupal.atomicReact = Drupal.atomicReact || {};
  Drupal.atomicReact.FocusTrap = FocusTrap;

  Drupal.behaviors.atomicReactFocusTrap = {
    attach: function (context) {
      var dialogs = context.querySelectorAll('[role="dialog"][aria-modal="true"]');
      dialogs.forEach(function (dialog) {
        if (dialog.hasAttribute('data-focus-trap-initialized')) return;
        dialog.setAttribute('data-focus-trap-initialized', 'true');
        var focusTrap = new FocusTrap(dialog);
        dialog.focusTrap = focusTrap;
        if (!dialog.hidden && dialog.style.display !== 'none') {
          focusTrap.activate();
        }
      });
    }
  };
})(Drupal);
