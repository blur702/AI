/**
 * @file
 * JavaScript behaviors for the congressional query results page.
 */

(function ($, Drupal, once) {
  "use strict";

  /**
   * Congressional Query Results behavior.
   */
  Drupal.behaviors.congressionalQueryResults = {
    attach: function (context, settings) {
      const $results = $(
        once(
          "congressional-query-results",
          ".congressional-query-results",
          context,
        ),
      );

      if ($results.length === 0) {
        return;
      }

      initCopyButton($results);
      initSourceExpansion($results);
      initFollowUpActions($results);
      initFeedbackButtons($results);
      initSourceContentExpansion($results);
      initPrintView($results);
      initSourceHighlighting($results);
    },
  };

  /**
   * Initialize copy-to-clipboard functionality.
   *
   * @param {jQuery} $results
   *   The results container.
   */
  function initCopyButton($results) {
    const $copyBtn = $results.find(".copy-answer-btn");

    if (!$copyBtn.length) {
      return;
    }

    $copyBtn.on("click", function (e) {
      e.preventDefault();
      const $btn = $(this);
      const $answerContent = $results.find(".answer-content");
      const textToCopy = $answerContent.text().trim();

      copyToClipboard(textToCopy)
        .then(function () {
          const originalText = $btn.text();
          $btn
            .text(Drupal.t("Copied!"))
            .addClass("copied")
            .prop("disabled", true);

          // Announce to screen readers.
          if (Drupal.announce) {
            Drupal.announce(Drupal.t("Answer copied to clipboard."));
          }

          setTimeout(function () {
            $btn
              .text(originalText)
              .removeClass("copied")
              .prop("disabled", false);
          }, 2000);
        })
        .catch(function (err) {
          console.error("Failed to copy text:", err);
          showToast(
            Drupal.t("Failed to copy. Please try selecting the text manually."),
            "error",
          );
        });
    });
  }

  /**
   * Initialize source list expansion/collapse.
   *
   * @param {jQuery} $results
   *   The results container.
   */
  function initSourceExpansion($results) {
    const $sourcesSection = $results.find(".sources-section");
    const $sourcesList = $sourcesSection.find(".sources-list");
    const $sources = $sourcesList.find(".source-item");
    const initialShowCount = 3;

    if ($sources.length <= initialShowCount) {
      return;
    }

    // Hide sources beyond initial count.
    $sources.each(function (index) {
      if (index >= initialShowCount) {
        $(this).addClass("hidden-source");
      }
    });

    // Create toggle button.
    const hiddenCount = $sources.length - initialShowCount;
    const $toggleBtn = $(
      '<button type="button" class="show-more-sources-btn">' +
        Drupal.t("Show @count more sources", { "@count": hiddenCount }) +
        "</button>",
    );

    $sourcesList.after($toggleBtn);

    // Toggle handler.
    $toggleBtn.on("click", function () {
      const $hiddenSources = $sourcesList.find(".source-item.hidden-source");
      const isExpanded = $toggleBtn.hasClass("expanded");

      if (isExpanded) {
        $hiddenSources.addClass("hidden-source").hide();
        $toggleBtn
          .removeClass("expanded")
          .text(
            Drupal.t("Show @count more sources", { "@count": hiddenCount }),
          );
      } else {
        $hiddenSources.removeClass("hidden-source").slideDown(200);
        $toggleBtn.addClass("expanded").text(Drupal.t("Show fewer sources"));
      }
    });
  }

  /**
   * Initialize follow-up action buttons.
   *
   * @param {jQuery} $results
   *   The results container.
   */
  function initFollowUpActions($results) {
    const $followUpBtn = $results.find(".follow-up-btn");

    if (!$followUpBtn.length) {
      return;
    }

    $followUpBtn.on("click", function (e) {
      e.preventDefault();
      const queryId = $results.data("query-id");
      const question = $results.find(".question-text").text().trim();

      // Store context for follow-up.
      sessionStorage.setItem(
        "congressional_query_context",
        JSON.stringify({
          query_id: queryId,
          original_question: question,
        }),
      );

      // Navigate to query form.
      window.location.href = Drupal.url("congressional/query");
    });

    // Share via email button.
    const $emailShareBtn = $results.find(".share-email-btn");
    if ($emailShareBtn.length) {
      $emailShareBtn.on("click", function (e) {
        e.preventDefault();
        const question = $results.find(".question-text").text().trim();
        const answer = $results.find(".answer-content").text().trim();
        const subject = encodeURIComponent(
          "Congressional Query: " + question.substring(0, 50) + "...",
        );
        const body = encodeURIComponent(
          "Question: " +
            question +
            "\n\n" +
            "Answer: " +
            answer +
            "\n\n" +
            "Source: " +
            window.location.href,
        );
        window.location.href = "mailto:?subject=" + subject + "&body=" + body;
      });
    }

    // Copy link button.
    const $copyLinkBtn = $results.find(".copy-link-btn");
    if ($copyLinkBtn.length) {
      $copyLinkBtn.on("click", function (e) {
        e.preventDefault();
        copyToClipboard(window.location.href)
          .then(function () {
            showToast(Drupal.t("Link copied to clipboard!"), "success");
          })
          .catch(function () {
            showToast(Drupal.t("Failed to copy link."), "error");
          });
      });
    }
  }

  /**
   * Initialize feedback buttons (thumbs up/down).
   *
   * @param {jQuery} $results
   *   The results container.
   */
  function initFeedbackButtons($results) {
    const $feedbackBtns = $results.find(".feedback-btn");

    if (!$feedbackBtns.length) {
      return;
    }

    $feedbackBtns.on("click", function (e) {
      e.preventDefault();
      const $btn = $(this);
      const feedbackType = $btn.data("feedback");
      const queryId = $results.data("query-id");

      // Visual feedback.
      $feedbackBtns.removeClass("selected");
      $btn.addClass("selected");

      // Log feedback (could be extended to send to server).
      console.log("Feedback logged:", feedbackType, "for query:", queryId);
      showToast(Drupal.t("Thank you for your feedback!"), "success");

      // Disable buttons after feedback.
      $feedbackBtns.prop("disabled", true);
    });
  }

  /**
   * Initialize source content expansion (read more).
   *
   * @param {jQuery} $results
   *   The results container.
   */
  function initSourceContentExpansion($results) {
    const $sourceItems = $results.find(".source-item");

    $sourceItems.each(function () {
      const $source = $(this);
      const $content = $source.find(".source-content");
      const $fullContent = $source.find(".source-content-full");
      const $expandBtn = $source.find(".expand-content-btn");

      // Skip if no expand button or no full content element.
      if (!$expandBtn.length || !$fullContent.length) {
        return;
      }

      $expandBtn.on("click", function (e) {
        e.preventDefault();
        const isExpanded = $source.hasClass("content-expanded");
        const $btnText = $expandBtn.find(".btn-text");

        if (isExpanded) {
          // Collapse: show truncated, hide full.
          $source.removeClass("content-expanded");
          $content.show();
          $fullContent.hide();
          $expandBtn.attr("aria-expanded", "false");
          if ($btnText.length) {
            $btnText.text(Drupal.t("Read more"));
          } else {
            $expandBtn.text(Drupal.t("Read more"));
          }
        } else {
          // Expand: hide truncated, show full.
          $source.addClass("content-expanded");
          $content.hide();
          $fullContent.show();
          $expandBtn.attr("aria-expanded", "true");
          if ($btnText.length) {
            $btnText.text(Drupal.t("Show less"));
          } else {
            $expandBtn.text(Drupal.t("Show less"));
          }
        }
      });
    });
  }

  /**
   * Initialize print-friendly view toggle.
   *
   * @param {jQuery} $results
   *   The results container.
   */
  function initPrintView($results) {
    const $printBtn = $results.find(".print-view-btn");

    if (!$printBtn.length) {
      return;
    }

    $printBtn.on("click", function (e) {
      e.preventDefault();

      // Expand all sources before printing.
      $results.find(".source-item.hidden-source").removeClass("hidden-source");
      $results.addClass("print-view");

      window.print();

      // Reset after print dialog closes.
      setTimeout(function () {
        $results.removeClass("print-view");
      }, 100);
    });
  }

  /**
   * Initialize source highlighting when hovering over references.
   *
   * @param {jQuery} $results
   *   The results container.
   */
  function initSourceHighlighting($results) {
    const $answerContent = $results.find(".answer-content");
    const $sources = $results.find(".source-item");

    // Highlight source when hovering over reference numbers in answer.
    $answerContent.on("mouseenter", "[data-source-index]", function () {
      const sourceIndex = $(this).data("source-index");
      $sources.eq(sourceIndex).addClass("highlighted");
    });

    $answerContent.on("mouseleave", "[data-source-index]", function () {
      $sources.removeClass("highlighted");
    });

    // Smooth scroll to sources section when clicking source reference.
    $answerContent.on("click", "[data-source-index]", function (e) {
      e.preventDefault();
      const sourceIndex = $(this).data("source-index");
      const $targetSource = $sources.eq(sourceIndex);

      if ($targetSource.length) {
        // Expand hidden sources if target is hidden.
        if ($targetSource.hasClass("hidden-source")) {
          $results.find(".show-more-sources-btn").trigger("click");
        }

        // Scroll to source.
        $("html, body").animate(
          {
            scrollTop: $targetSource.offset().top - 100,
          },
          300,
        );

        // Highlight temporarily.
        $targetSource.addClass("highlighted");
        setTimeout(function () {
          $targetSource.removeClass("highlighted");
        }, 2000);
      }
    });
  }

  /**
   * Copy text to clipboard using modern API with fallback.
   *
   * @param {string} text
   *   The text to copy.
   *
   * @return {Promise}
   *   Promise that resolves on success.
   */
  function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }

    // Fallback for older browsers.
    return new Promise(function (resolve, reject) {
      const textArea = document.createElement("textarea");
      textArea.value = text;
      textArea.style.position = "fixed";
      textArea.style.left = "-9999px";
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();

      try {
        const successful = document.execCommand("copy");
        document.body.removeChild(textArea);
        if (successful) {
          resolve();
        } else {
          reject(new Error("Copy command failed"));
        }
      } catch (err) {
        document.body.removeChild(textArea);
        reject(err);
      }
    });
  }

  /**
   * Show a toast notification.
   *
   * @param {string} message
   *   The message to display.
   * @param {string} type
   *   The type of toast: 'success' or 'error'.
   */
  function showToast(message, type) {
    const $toast = $(
      '<div class="status-toast toast-' + type + '">' + message + "</div>",
    );

    $("body").append($toast);

    setTimeout(function () {
      $toast.fadeOut(300, function () {
        $toast.remove();
      });
    }, 3000);
  }
})(jQuery, Drupal, once);
