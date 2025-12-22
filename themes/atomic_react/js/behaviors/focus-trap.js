/**
 * @file
 * Focus trap utility for modal dialogs.
 *
 * Provides focus trapping within modal dialogs to ensure
 * keyboard users cannot tab outside the dialog.
 */

(function (Drupal) {
  "use strict";

  /**
   * Focusable element selectors.
   *
   * @type {string}
   */
  const FOCUSABLE_SELECTORS = [
    "a[href]",
    "area[href]",
    'input:not([disabled]):not([type="hidden"])',
    "select:not([disabled])",
    "textarea:not([disabled])",
    "button:not([disabled])",
    "iframe",
    "object",
    "embed",
    "[contenteditable]",
    '[tabindex]:not([tabindex="-1"])',
  ].join(", ");

  /**
   * Get all focusable elements within a container.
   *
   * @param {HTMLElement} container
   *   The container element.
   * @return {HTMLElement[]}
   *   Array of focusable elements.
   */
  function getFocusableElements(container) {
    const elements = container.querySelectorAll(FOCUSABLE_SELECTORS);
    return Array.from(elements).filter(function (element) {
      // Filter out elements that are not visible
      return !!(
        element.offsetWidth ||
        element.offsetHeight ||
        element.getClientRects().length
      );
    });
  }

  /**
   * Focus trap manager.
   *
   * @param {HTMLElement} container
   *   The container element to trap focus within.
   */
  function FocusTrap(container) {
    this.container = container;
    this.previouslyFocused = null;
    this.handleKeyDown = this.handleKeyDown.bind(this);
  }

  /**
   * Activate the focus trap.
   */
  FocusTrap.prototype.activate = function () {
    // Store the previously focused element
    this.previouslyFocused = document.activeElement;

    // Add keyboard listener
    document.addEventListener("keydown", this.handleKeyDown);

    // Set focus to the first focusable element
    const focusableElements = getFocusableElements(this.container);
    if (focusableElements.length > 0) {
      focusableElements[0].focus();
    } else {
      // If no focusable elements, focus the container itself
      this.container.setAttribute("tabindex", "-1");
      this.container.focus();
    }

    // Add class to body to prevent scrolling
    document.body.classList.add("dialog-open");
  };

  /**
   * Deactivate the focus trap.
   */
  FocusTrap.prototype.deactivate = function () {
    // Remove keyboard listener
    document.removeEventListener("keydown", this.handleKeyDown);

    // Remove body class
    document.body.classList.remove("dialog-open");

    // Restore focus to the previously focused element
    if (
      this.previouslyFocused &&
      typeof this.previouslyFocused.focus === "function"
    ) {
      this.previouslyFocused.focus();
    }
  };

  /**
   * Handle keydown events for focus trapping.
   *
   * @param {KeyboardEvent} event
   *   The keyboard event.
   */
  FocusTrap.prototype.handleKeyDown = function (event) {
    if (event.key !== "Tab") {
      return;
    }

    const focusableElements = getFocusableElements(this.container);

    if (focusableElements.length === 0) {
      event.preventDefault();
      return;
    }

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    if (event.shiftKey) {
      // Shift + Tab: If on first element, wrap to last
      if (document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      }
    } else {
      // Tab: If on last element, wrap to first
      if (document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    }
  };

  /**
   * Expose FocusTrap as a Drupal utility.
   */
  Drupal.atomicReact = Drupal.atomicReact || {};
  Drupal.atomicReact.FocusTrap = FocusTrap;

  /**
   * Behavior for automatic focus trap on dialogs.
   *
   * @type {Drupal~behavior}
   *
   * @prop {Drupal~behaviorAttach} attach
   *   Attaches the focus trap behavior to dialogs.
   */
  Drupal.behaviors.atomicReactFocusTrap = {
    attach: function (context) {
      // Auto-attach to Drupal dialogs
      const dialogs = context.querySelectorAll(
        '[role="dialog"][aria-modal="true"]',
      );

      dialogs.forEach(function (dialog) {
        if (dialog.hasAttribute("data-focus-trap-initialized")) {
          return;
        }

        dialog.setAttribute("data-focus-trap-initialized", "true");

        const focusTrap = new FocusTrap(dialog);

        // Store reference for later cleanup
        dialog.focusTrap = focusTrap;

        // Activate if dialog is visible
        if (!dialog.hidden && dialog.style.display !== "none") {
          focusTrap.activate();
        }

        // Watch for dialog visibility changes
        const observer = new MutationObserver(function (mutations) {
          mutations.forEach(function (mutation) {
            if (mutation.type === "attributes") {
              const isHidden = dialog.hidden || dialog.style.display === "none";
              if (isHidden) {
                focusTrap.deactivate();
              } else {
                focusTrap.activate();
              }
            }
          });
        });

        observer.observe(dialog, {
          attributes: true,
          attributeFilter: ["hidden", "style", "class"],
        });
      });
    },

    detach: function (context, settings, trigger) {
      if (trigger !== "unload") {
        return;
      }

      const dialogs = context.querySelectorAll("[data-focus-trap-initialized]");

      dialogs.forEach(function (dialog) {
        if (dialog.focusTrap) {
          dialog.focusTrap.deactivate();
        }
      });
    },
  };
})(Drupal);
