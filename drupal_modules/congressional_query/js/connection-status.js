/**
 * @file
 * Congressional Query connection status JavaScript.
 */

(function ($, Drupal, drupalSettings, once) {
  "use strict";

  /**
   * Connection status behavior.
   */
  Drupal.behaviors.congressionalQueryStatus = {
    attach: function (context, settings) {
      const elements = once(
        "congressional-status",
        ".connection-status-block",
        context,
      );

      if (elements.length === 0) {
        return;
      }

      const statusBlock = $(elements);

      const config = drupalSettings.congressionalQueryStatus || {};
      const healthUrl = config.healthUrl || "/congressional/health";
      const refreshInterval = config.refreshInterval || 30000;
      const autoRefresh = config.autoRefresh !== false;

      let intervalId = null;

      // Handle refresh button click.
      statusBlock.on("click", ".refresh-status-btn", function (e) {
        e.preventDefault();
        refreshStatus();
      });

      // Start auto-refresh if enabled.
      if (autoRefresh && refreshInterval > 0) {
        intervalId = setInterval(refreshStatus, refreshInterval);
      }

      /**
       * Refresh status from server.
       */
      function refreshStatus() {
        const refreshBtn = statusBlock.find(".refresh-status-btn");
        refreshBtn.prop("disabled", true).addClass("loading");

        $.ajax({
          url: healthUrl,
          method: "GET",
          dataType: "json",
          success: function (response) {
            updateStatusDisplay(response);
            showNotification("Status updated", "success");
          },
          error: function (xhr) {
            showNotification("Failed to refresh status", "error");
          },
          complete: function () {
            refreshBtn.prop("disabled", false).removeClass("loading");
          },
        });
      }

      /**
       * Update status display.
       */
      function updateStatusDisplay(data) {
        const services = data.services || {};

        // Update SSH status.
        if (services.ssh) {
          updateServiceStatus("ssh", services.ssh);
        }

        // Update Ollama status.
        if (services.ollama) {
          updateServiceStatus("ollama", services.ollama);
        }

        // Update Weaviate status.
        if (services.weaviate) {
          updateServiceStatus("weaviate", services.weaviate);
        }

        // Update timestamp.
        const timestamp = new Date(data.timestamp * 1000);
        statusBlock
          .find(".last-check-time")
          .text(timestamp.toLocaleTimeString());

        // Update overall status.
        statusBlock
          .find(".overall-status")
          .removeClass("status-ok status-warning status-error")
          .addClass("status-" + data.overall);
      }

      /**
       * Update individual service status.
       */
      function updateServiceStatus(service, status) {
        const serviceEl = statusBlock.find(".service-status-" + service);

        if (serviceEl.length === 0) {
          return;
        }

        // Update status indicator.
        serviceEl
          .find(".status-indicator")
          .removeClass("status-ok status-warning status-error status-unknown")
          .addClass("status-" + status.status);

        // Update status text.
        serviceEl.find(".status-text").text(status.message || status.status);

        // Update details if shown.
        const detailsEl = serviceEl.find(".status-details");
        if (detailsEl.length > 0 && status.details) {
          let detailsHtml = "";
          for (const key in status.details) {
            detailsHtml +=
              '<div class="detail-item"><span class="detail-key">' +
              escapeHtml(key) +
              ':</span> <span class="detail-value">' +
              escapeHtml(String(status.details[key])) +
              "</span></div>";
          }
          detailsEl.html(detailsHtml);
        }

        // Show models for Ollama.
        if (service === "ollama" && status.models) {
          const modelsEl = serviceEl.find(".ollama-models");
          if (modelsEl.length > 0) {
            modelsEl.text(status.models.length + " models available");
          }
        }

        // Show document count for Weaviate.
        if (
          service === "weaviate" &&
          status.details &&
          status.details.document_count !== undefined
        ) {
          const countEl = serviceEl.find(".weaviate-count");
          if (countEl.length > 0) {
            countEl.text(status.details.document_count + " documents");
          }
        }
      }

      /**
       * Show notification toast.
       */
      function showNotification(message, type) {
        // Check if Drupal messages are available.
        if (typeof Drupal.Message !== "undefined") {
          const messageArea = new Drupal.Message();
          messageArea.add(message, {
            type: type === "error" ? "error" : "status",
          });
        } else {
          // Fallback - simple toast.
          const toast = $("<div>")
            .addClass("status-toast toast-" + type)
            .text(message)
            .appendTo("body");

          setTimeout(function () {
            toast.fadeOut(300, function () {
              $(this).remove();
            });
          }, 3000);
        }
      }

      /**
       * Escape HTML.
       */
      function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
      }

      // Cleanup on detach.
      $(window).on("unload", function () {
        if (intervalId) {
          clearInterval(intervalId);
        }
      });
    },
  };
})(jQuery, Drupal, drupalSettings, once);
