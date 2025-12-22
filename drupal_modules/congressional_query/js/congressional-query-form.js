/**
 * @file
 * JavaScript behaviors for the congressional query form.
 */

(function ($, Drupal, once) {
  "use strict";

  /**
   * Congressional Query Form behavior.
   */
  Drupal.behaviors.congressionalQueryForm = {
    attach: function (context, settings) {
      const $wrapper = $(
        once(
          "congressional-query-form",
          ".congressional-query-form-wrapper",
          context,
        ),
      );

      if ($wrapper.length === 0) {
        return;
      }

      const $form = $wrapper.find("form");
      const $textarea = $form.find("#edit-question");
      const $submitBtn = $form.find('input[type="submit"]');
      const $exampleChips = $form.find(".example-question-chip");
      const maxLength = 2000;

      // Create character counter if it doesn't exist.
      if ($textarea.length && !$form.find(".character-counter").length) {
        const $counter = $(
          '<div class="character-counter" aria-live="polite" role="status"></div>',
        );
        $textarea.after($counter);
        updateCharacterCounter($textarea, $counter, maxLength);
      }

      // Handle example question chip clicks.
      $exampleChips.each(function () {
        const $chip = $(this);
        $chip.on("click", function (e) {
          e.preventDefault();
          const question = $chip.attr("data-question");
          if (question && $textarea.length) {
            $textarea.val(question);
            $textarea.trigger("input");
            $textarea.trigger("focus");
            autoResizeTextarea($textarea);

            // Visual feedback on chip.
            $chip.addClass("selected");
            setTimeout(function () {
              $chip.removeClass("selected");
            }, 300);
          }
        });

        // Keyboard support for chips.
        $chip.on("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            $chip.trigger("click");
          }
        });

        // Ensure chips are focusable.
        if (!$chip.attr("tabindex")) {
          $chip.attr("tabindex", "0");
        }
      });

      // Auto-resize textarea as user types.
      if ($textarea.length) {
        $textarea.on("input", function () {
          autoResizeTextarea($(this));
          const $counter = $form.find(".character-counter");
          if ($counter.length) {
            updateCharacterCounter($(this), $counter, maxLength);
          }
        });

        // Initial resize.
        autoResizeTextarea($textarea);
      }

      // Ctrl+Enter to submit form.
      $textarea.on("keydown", function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          $submitBtn.trigger("click");
        }
      });

      // Form submission loading state.
      $form.on("submit", function () {
        const $loadingOverlay = $wrapper.find(".loading-overlay");

        // Show loading state.
        $submitBtn
          .prop("disabled", true)
          .addClass("is-loading")
          .data("original-value", $submitBtn.val())
          .val(Drupal.t("Processing..."));

        // Show loading overlay if it exists.
        if ($loadingOverlay.length) {
          $loadingOverlay.removeClass("hidden").attr("aria-hidden", "false");
        }

        // Announce to screen readers.
        announceMessage(Drupal.t("Processing your question. Please wait."));
      });

      // Handle AJAX errors gracefully.
      $(document).on("ajaxError", function (event, xhr, settings) {
        if (settings.url && settings.url.includes("congressional")) {
          resetFormState($submitBtn, $wrapper.find(".loading-overlay"));
          announceMessage(Drupal.t("An error occurred. Please try again."));
        }
      });
    },
  };

  /**
   * Auto-resize textarea to fit content.
   *
   * @param {jQuery} $textarea
   *   The textarea element.
   */
  function autoResizeTextarea($textarea) {
    // Reset height to auto to get correct scrollHeight.
    $textarea.css("height", "auto");

    // Set minimum height.
    const minHeight = 100;
    const maxHeight = 400;
    const scrollHeight = $textarea[0].scrollHeight;

    // Apply new height within bounds.
    const newHeight = Math.min(Math.max(scrollHeight, minHeight), maxHeight);
    $textarea.css("height", newHeight + "px");

    // Show scrollbar if content exceeds max height.
    if (scrollHeight > maxHeight) {
      $textarea.css("overflow-y", "auto");
    } else {
      $textarea.css("overflow-y", "hidden");
    }
  }

  /**
   * Update character counter display.
   *
   * @param {jQuery} $textarea
   *   The textarea element.
   * @param {jQuery} $counter
   *   The counter element.
   * @param {number} maxLength
   *   Maximum allowed characters.
   */
  function updateCharacterCounter($textarea, $counter, maxLength) {
    const currentLength = $textarea.val().length;
    const remaining = maxLength - currentLength;
    const percentage = (currentLength / maxLength) * 100;

    $counter.text(
      Drupal.t("@remaining characters remaining", {
        "@remaining": remaining,
      }),
    );

    // Update styling based on remaining characters.
    $counter.removeClass("counter-warning counter-danger counter-ok");

    if (percentage >= 90) {
      $counter.addClass("counter-danger");
    } else if (percentage >= 75) {
      $counter.addClass("counter-warning");
    } else {
      $counter.addClass("counter-ok");
    }

    // Update ARIA attributes.
    if (remaining < 0) {
      $textarea.attr("aria-invalid", "true");
    } else {
      $textarea.removeAttr("aria-invalid");
    }
  }

  /**
   * Reset form state after submission or error.
   *
   * @param {jQuery} $submitBtn
   *   The submit button.
   * @param {jQuery} $loadingOverlay
   *   The loading overlay element.
   */
  function resetFormState($submitBtn, $loadingOverlay) {
    $submitBtn
      .prop("disabled", false)
      .removeClass("is-loading")
      .val($submitBtn.data("original-value") || Drupal.t("Ask Question"));

    if ($loadingOverlay.length) {
      $loadingOverlay.addClass("hidden").attr("aria-hidden", "true");
    }
  }

  /**
   * Announce message to screen readers.
   *
   * @param {string} message
   *   The message to announce.
   */
  function announceMessage(message) {
    // Use Drupal.announce if available, otherwise create own live region.
    if (Drupal.announce) {
      Drupal.announce(message);
    } else {
      let $liveRegion = $("#congressional-query-live-region");
      if (!$liveRegion.length) {
        $liveRegion = $(
          '<div id="congressional-query-live-region" aria-live="polite" class="visually-hidden"></div>',
        );
        $("body").append($liveRegion);
      }
      $liveRegion.text(message);
    }
  }
})(jQuery, Drupal, once);
