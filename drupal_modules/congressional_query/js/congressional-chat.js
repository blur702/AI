/**
 * @file
 * Congressional Query chat interface JavaScript with streaming and auto-save.
 */

(function ($, Drupal, drupalSettings, once) {
  "use strict";

  /**
   * Congressional chat behavior.
   */
  Drupal.behaviors.congressionalChat = {
    attach: function (context, settings) {
      const elements = once(
        "congressional-chat",
        ".congressional-chat-container",
        context,
      );

      if (elements.length === 0) {
        return;
      }

      const chatContainer = $(elements);

      const config = drupalSettings.congressionalQuery || {};
      const sendUrl = config.sendUrl || "/congressional/chat/send";
      const streamUrl = config.streamUrl || "/congressional/chat/stream";
      const exportUrl = config.exportUrl || "/congressional/chat/export";
      let conversationId = config.conversationId || null;
      const memberFilter = config.memberFilter || null;
      const useStreaming = config.useStreaming !== false; // Default to true

      const messagesContainer = chatContainer.find(".chat-messages");
      const inputForm = chatContainer.find(".chat-input-form");
      const messageInput = chatContainer.find(".chat-message-input");
      const sendButton = chatContainer.find(".chat-send-button");
      const typingIndicator = chatContainer.find(".typing-indicator");
      const characterCount = chatContainer.find(".current-count");
      const draftBanner = chatContainer.find(".draft-recovery-banner");

      // Auto-save configuration
      const AUTOSAVE_INTERVAL = 2000; // 2 seconds
      const DRAFT_KEY = "congressional_chat_draft_" + (conversationId || "new");
      let autosaveTimer = null;

      // Initialize.
      init();

      function init() {
        scrollToBottom();
        checkForDraft();
        setupEventListeners();
        updateCharacterCount();
        announceToScreenReader("Chat interface loaded");
      }

      function setupEventListeners() {
        // Handle form submission.
        inputForm.on("submit", function (e) {
          e.preventDefault();
          sendMessage();
        });

        // Handle send button click.
        sendButton.on("click", function (e) {
          e.preventDefault();
          sendMessage();
        });

        // Handle Enter key (without Shift).
        messageInput.on("keydown", function (e) {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
          }
        });

        // Handle input for character count and auto-save.
        messageInput.on("input", function () {
          updateCharacterCount();
          scheduleAutosave();
        });

        // Handle example question clicks.
        chatContainer.on("click", ".example-question-chip", function (e) {
          e.preventDefault();
          const question = $(this).data("question") || $(this).text();
          messageInput.val(question);
          updateCharacterCount();
          sendMessage();
        });

        // Handle source expansion with accessibility.
        chatContainer.on("click", ".source-toggle", function (e) {
          e.preventDefault();
          const sourcesContainer = $(this).closest(".message-sources");
          const sourcesList = sourcesContainer.find(".sources-list");
          const isExpanded = sourcesContainer.hasClass("expanded");

          sourcesContainer.toggleClass("expanded");
          $(this).attr("aria-expanded", !isExpanded);
          sourcesList.attr("aria-hidden", isExpanded);

          // Update toggle icon
          $(this)
            .find(".toggle-icon")
            .text(isExpanded ? "+" : "-");
        });

        // Handle copy button.
        chatContainer.on("click", ".copy-answer-btn", function (e) {
          e.preventDefault();
          const content =
            $(this).data("content") ||
            $(this).closest(".chat-message").find(".message-content").text();
          copyToClipboard(content);
          const btn = $(this);
          btn.html('<span aria-hidden="true">&#10003;</span> Copied!');
          announceToScreenReader("Response copied to clipboard");
          setTimeout(function () {
            btn.html('<span aria-hidden="true">&#128203;</span> Copy');
          }, 2000);
        });

        // Handle new conversation button.
        chatContainer.on("click", ".new-conversation-btn", function (e) {
          e.preventDefault();
          if (
            confirm(
              Drupal.t(
                "Start a new conversation? This will clear the current chat.",
              ),
            )
          ) {
            startNewConversation();
          }
        });

        // Handle export button.
        chatContainer.on("click", ".export-conversation-btn", function (e) {
          e.preventDefault();
          showExportOptions();
        });

        // Handle edit message button.
        chatContainer.on("click", ".edit-message-btn", function (e) {
          e.preventDefault();
          const messageIndex = $(this).data("message-index");
          editMessage(messageIndex);
        });

        // Handle delete message button.
        chatContainer.on("click", ".delete-message-btn", function (e) {
          e.preventDefault();
          const messageIndex = $(this).data("message-index");
          if (confirm(Drupal.t("Delete this message?"))) {
            deleteMessage(messageIndex);
          }
        });

        // Handle draft recovery.
        draftBanner.on("click", ".restore-draft-btn", function () {
          restoreDraft();
        });

        draftBanner.on("click", ".discard-draft-btn", function () {
          discardDraft();
        });

        // Handle keyboard navigation in messages.
        messagesContainer.on("keydown", function (e) {
          if (e.key === "Escape") {
            // Close any expanded sources
            chatContainer.find(".message-sources.expanded").each(function () {
              $(this).removeClass("expanded");
              $(this).find(".source-toggle").attr("aria-expanded", "false");
              $(this).find(".sources-list").attr("aria-hidden", "true");
            });
          }
        });
      }

      /**
       * Send a message (with optional streaming).
       */
      function sendMessage() {
        const message = messageInput.val().trim();

        if (!message) {
          return;
        }

        // Clear autosave and draft.
        clearAutosave();
        clearDraft();

        // Disable input.
        messageInput.prop("disabled", true);
        sendButton.prop("disabled", true);

        // Add user message to UI.
        addMessage("user", message);

        // Clear input.
        messageInput.val("");
        updateCharacterCount();

        // Show typing indicator.
        showTypingIndicator();

        if (useStreaming && typeof EventSource !== "undefined") {
          sendMessageStreaming(message);
        } else {
          sendMessageAjax(message);
        }
      }

      /**
       * Send message with streaming (SSE).
       */
      function sendMessageStreaming(message) {
        // For SSE, we need to use fetch with POST
        fetch(streamUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            message: message,
            conversation_id: conversationId,
            member_filter: memberFilter,
          }),
        })
          .then(function (response) {
            if (!response.ok) {
              throw new Error("Network response was not ok");
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            let assistantMessageEl = null;
            let fullContent = "";

            function processChunk(result) {
              if (result.done) {
                hideTypingIndicator();
                enableInput();
                return;
              }

              buffer += decoder.decode(result.value, { stream: true });
              const lines = buffer.split("\n");
              buffer = lines.pop(); // Keep incomplete line in buffer

              lines.forEach(function (line) {
                if (line.startsWith("data: ")) {
                  try {
                    const data = JSON.parse(line.substring(6));

                    if (data.type === "chunk") {
                      if (!assistantMessageEl) {
                        hideTypingIndicator();
                        assistantMessageEl = addStreamingMessage();
                      }
                      fullContent += data.content;
                      updateStreamingMessage(assistantMessageEl, fullContent);
                    } else if (data.type === "complete") {
                      if (data.conversation_id) {
                        conversationId = data.conversation_id;
                      }
                      finalizeStreamingMessage(
                        assistantMessageEl,
                        data.sources,
                        data.model,
                      );
                      enableInput();
                      announceToScreenReader("Response received");
                    } else if (data.type === "error") {
                      hideTypingIndicator();
                      addErrorMessage(data.error);
                      enableInput();
                    }
                  } catch (e) {
                    console.error("Error parsing SSE data:", e);
                  }
                }
              });

              return reader.read().then(processChunk);
            }

            return reader.read().then(processChunk);
          })
          .catch(function (error) {
            hideTypingIndicator();
            addErrorMessage(
              "Failed to connect. Falling back to standard mode.",
            );
            // Fallback to AJAX
            sendMessageAjax(message);
          });
      }

      /**
       * Send message with standard AJAX.
       */
      function sendMessageAjax(message) {
        $.ajax({
          url: sendUrl,
          method: "POST",
          contentType: "application/json",
          data: JSON.stringify({
            message: message,
            conversation_id: conversationId,
            member_filter: memberFilter,
          }),
          success: function (response) {
            hideTypingIndicator();

            if (response.conversation_id) {
              conversationId = response.conversation_id;
            }

            addMessage(
              "assistant",
              response.answer,
              response.sources,
              response.model,
            );
            enableInput();
            announceToScreenReader("Response received");
          },
          error: function (xhr) {
            hideTypingIndicator();

            let errorMessage = "An error occurred. Please try again.";
            if (xhr.status === 429) {
              errorMessage = "Rate limit exceeded. Please wait a moment.";
            } else if (xhr.responseJSON && xhr.responseJSON.error) {
              errorMessage = xhr.responseJSON.error;
            }

            addErrorMessage(errorMessage);
            enableInput();
          },
        });
      }

      /**
       * Add a streaming message placeholder.
       */
      function addStreamingMessage() {
        const messageEl = $("<div>")
          .addClass("chat-message message-assistant streaming")
          .attr("role", "article")
          .attr("aria-label", "Assistant response");

        const avatar = $("<div>")
          .addClass("message-avatar")
          .attr("aria-hidden", "true")
          .text("AI");

        const contentWrapper = $("<div>").addClass("message-content-wrapper");
        const contentEl = $("<div>")
          .addClass("message-content")
          .html('<span class="streaming-cursor">|</span>');

        contentWrapper.append(contentEl);
        messageEl.append(avatar);
        messageEl.append(contentWrapper);

        messagesContainer.append(messageEl);
        scrollToBottom();

        return messageEl;
      }

      /**
       * Update streaming message content.
       */
      function updateStreamingMessage(messageEl, content) {
        const contentEl = messageEl.find(".message-content");
        contentEl.html(
          escapeHtml(content) + '<span class="streaming-cursor">|</span>',
        );
        scrollToBottom();
      }

      /**
       * Finalize streaming message with sources and metadata.
       */
      function finalizeStreamingMessage(messageEl, sources, model) {
        messageEl.removeClass("streaming");
        const contentWrapper = messageEl.find(".message-content-wrapper");

        // Remove cursor
        const contentEl = messageEl.find(".message-content");
        contentEl.find(".streaming-cursor").remove();

        // Add sources if available.
        if (sources && sources.length > 0) {
          const sourcesEl = buildSourcesElement(sources);
          contentWrapper.append(sourcesEl);
        }

        // Add metadata.
        const metaEl = $("<div>")
          .addClass("message-meta")
          .attr("role", "contentinfo")
          .html(
            '<span class="model-name">' +
              escapeHtml(model || "") +
              "</span>" +
              '<button class="copy-answer-btn" aria-label="Copy response to clipboard">' +
              '<span aria-hidden="true">&#128203;</span> Copy</button>',
          );
        contentWrapper.append(metaEl);

        scrollToBottom();
      }

      /**
       * Add a message to the chat.
       */
      function addMessage(role, content, sources, model) {
        const messageEl = $("<div>")
          .addClass("chat-message")
          .addClass("message-" + role)
          .attr("role", "article")
          .attr(
            "aria-label",
            role === "user" ? "Your message" : "Assistant response",
          );

        const avatar = $("<div>")
          .addClass("message-avatar")
          .attr("aria-hidden", "true")
          .text(role === "user" ? "U" : "AI");

        const contentWrapper = $("<div>").addClass("message-content-wrapper");
        const contentEl = $("<div>").addClass("message-content").text(content);

        contentWrapper.append(contentEl);

        // Add sources if available.
        if (sources && sources.length > 0) {
          const sourcesEl = buildSourcesElement(sources);
          contentWrapper.append(sourcesEl);
        }

        // Add metadata for assistant messages.
        if (role === "assistant") {
          const metaEl = $("<div>")
            .addClass("message-meta")
            .attr("role", "contentinfo")
            .html(
              '<span class="model-name">' +
                escapeHtml(model || "") +
                "</span>" +
                '<button class="copy-answer-btn" aria-label="Copy response to clipboard">' +
                '<span aria-hidden="true">&#128203;</span> Copy</button>',
            );
          contentWrapper.append(metaEl);
        }

        messageEl.append(avatar);
        messageEl.append(contentWrapper);

        messagesContainer.append(messageEl);
        scrollToBottom();
      }

      /**
       * Build sources element.
       */
      function buildSourcesElement(sources) {
        const sourcesEl = $("<div>")
          .addClass("message-sources")
          .attr("aria-label", "Source documents");

        const toggleBtn = $("<button>")
          .addClass("source-toggle")
          .attr("aria-expanded", "false")
          .html(
            '<span class="toggle-icon" aria-hidden="true">+</span> ' +
              sources.length +
              " sources",
          );

        sourcesEl.append(toggleBtn);

        const sourcesList = $("<div>")
          .addClass("sources-list")
          .attr("role", "list")
          .attr("aria-hidden", "true");

        sources.forEach(function (source) {
          const sourceItem = $("<div>")
            .addClass("source-item")
            .attr("role", "listitem");

          const partyClass = source.party_class || getPartyClass(source.party);

          const header = $("<div>")
            .addClass("source-header")
            .html(
              '<span class="member-chip ' +
                partyClass +
                '">' +
                escapeHtml(source.member_name) +
                " (" +
                escapeHtml(source.party || "?") +
                "-" +
                escapeHtml(source.state || "??") +
                ")" +
                "</span>",
            );

          const title = $("<div>")
            .addClass("source-title")
            .text(source.title || "Untitled");

          const content = $("<div>")
            .addClass("source-content")
            .text(source.content || "");

          sourceItem.append(header);
          sourceItem.append(title);
          sourceItem.append(content);

          if (source.url) {
            const link = $("<a>")
              .addClass("source-link")
              .attr("href", source.url)
              .attr("target", "_blank")
              .attr("rel", "noopener noreferrer")
              .attr(
                "aria-label",
                "View source: " +
                  (source.title || "Untitled") +
                  " (opens in new tab)",
              )
              .html(
                'View source <span class="external-icon" aria-hidden="true">&#8599;</span>',
              );
            sourceItem.append(link);
          }

          sourcesList.append(sourceItem);
        });

        sourcesEl.append(sourcesList);

        return sourcesEl;
      }

      /**
       * Add error message.
       */
      function addErrorMessage(message) {
        const errorEl = $("<div>")
          .addClass("chat-message message-error")
          .attr("role", "alert")
          .html('<div class="error-content">' + escapeHtml(message) + "</div>");

        messagesContainer.append(errorEl);
        scrollToBottom();
        announceToScreenReader("Error: " + message);
      }

      /**
       * Edit a message.
       */
      function editMessage(messageIndex) {
        const messageEl = messagesContainer.find(
          '[data-message-index="' + messageIndex + '"]',
        );
        const contentEl = messageEl.find(".message-content");
        const currentContent = contentEl.text();

        const editForm = $(
          '<div class="edit-form">' +
            '<textarea class="edit-input">' +
            escapeHtml(currentContent) +
            "</textarea>" +
            '<div class="edit-actions">' +
            '<button type="button" class="save-edit-btn">Save</button>' +
            '<button type="button" class="cancel-edit-btn">Cancel</button>' +
            "</div></div>",
        );

        contentEl.hide();
        contentEl.after(editForm);

        const editInput = editForm.find(".edit-input").focus();

        editForm.find(".save-edit-btn").on("click", function () {
          const newContent = editInput.val().trim();
          if (newContent && newContent !== currentContent) {
            $.ajax({
              url:
                "/congressional/chat/message/" +
                conversationId +
                "/" +
                messageIndex,
              method: "PATCH",
              contentType: "application/json",
              data: JSON.stringify({ content: newContent }),
              success: function () {
                contentEl.text(newContent);
                editForm.remove();
                contentEl.show();

                // Add edited indicator
                if (!messageEl.find(".edited-indicator").length) {
                  contentEl.after(
                    '<span class="edited-indicator">(edited)</span>',
                  );
                }
              },
              error: function () {
                alert("Failed to update message.");
              },
            });
          } else {
            editForm.remove();
            contentEl.show();
          }
        });

        editForm.find(".cancel-edit-btn").on("click", function () {
          editForm.remove();
          contentEl.show();
        });
      }

      /**
       * Delete a message.
       */
      function deleteMessage(messageIndex) {
        $.ajax({
          url:
            "/congressional/chat/message/" +
            conversationId +
            "/" +
            messageIndex,
          method: "DELETE",
          success: function () {
            const messageEl = messagesContainer.find(
              '[data-message-index="' + messageIndex + '"]',
            );
            messageEl.fadeOut(function () {
              $(this).remove();
              // Re-index remaining messages
              messagesContainer.find(".chat-message").each(function (index) {
                $(this).attr("data-message-index", index);
                $(this)
                  .find("[data-message-index]")
                  .attr("data-message-index", index);
              });
            });
            announceToScreenReader("Message deleted");
          },
          error: function () {
            alert("Failed to delete message.");
          },
        });
      }

      /**
       * Start a new conversation.
       */
      function startNewConversation() {
        $.ajax({
          url: "/congressional/chat/new",
          method: "POST",
          contentType: "application/json",
          data: JSON.stringify({ member_filter: memberFilter }),
          success: function (response) {
            conversationId = response.conversation_id;
            messagesContainer.empty();
            // Show welcome message
            location.href =
              "/congressional/chat?conversation_id=" +
              conversationId +
              (memberFilter
                ? "&member_filter=" + encodeURIComponent(memberFilter)
                : "");
          },
          error: function () {
            alert("Failed to create new conversation.");
          },
        });
      }

      /**
       * Show export options.
       */
      function showExportOptions() {
        if (!conversationId) {
          alert("No conversation to export.");
          return;
        }

        const format = prompt(
          "Export format (json, markdown, html):",
          "markdown",
        );
        if (
          format &&
          ["json", "markdown", "html"].includes(format.toLowerCase())
        ) {
          window.location.href =
            exportUrl + "/" + conversationId + "/" + format.toLowerCase();
        }
      }

      /**
       * Auto-save functionality.
       */
      function scheduleAutosave() {
        if (autosaveTimer) {
          clearTimeout(autosaveTimer);
        }
        autosaveTimer = setTimeout(saveDraft, AUTOSAVE_INTERVAL);
      }

      function clearAutosave() {
        if (autosaveTimer) {
          clearTimeout(autosaveTimer);
          autosaveTimer = null;
        }
      }

      function saveDraft() {
        const content = messageInput.val().trim();
        if (content) {
          const draft = {
            conversation_id: conversationId,
            content: content,
            member_filter: memberFilter,
            timestamp: Date.now(),
          };
          try {
            localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
          } catch (e) {
            console.warn("Could not save draft to localStorage");
          }
        }
      }

      function checkForDraft() {
        try {
          const draftData = localStorage.getItem(DRAFT_KEY);
          if (draftData) {
            const draft = JSON.parse(draftData);
            // Only show if draft is less than 24 hours old
            if (
              Date.now() - draft.timestamp < 24 * 60 * 60 * 1000 &&
              draft.content
            ) {
              draftBanner.data("draft", draft).removeClass("hidden");
            } else {
              clearDraft();
            }
          }
        } catch (e) {
          console.warn("Could not read draft from localStorage");
        }
      }

      function restoreDraft() {
        const draft = draftBanner.data("draft");
        if (draft && draft.content) {
          messageInput.val(draft.content);
          updateCharacterCount();
          draftBanner.addClass("hidden");
          messageInput.focus();
          announceToScreenReader("Draft restored");
        }
      }

      function discardDraft() {
        clearDraft();
        draftBanner.addClass("hidden");
      }

      function clearDraft() {
        try {
          localStorage.removeItem(DRAFT_KEY);
        } catch (e) {
          // Ignore
        }
      }

      /**
       * Update character count.
       */
      function updateCharacterCount() {
        const length = messageInput.val().length;
        characterCount.text(length);

        const countContainer = characterCount.parent();
        countContainer.removeClass("counter-ok counter-warning counter-danger");

        if (length >= 1800) {
          countContainer.addClass("counter-danger");
        } else if (length >= 1500) {
          countContainer.addClass("counter-warning");
        } else {
          countContainer.addClass("counter-ok");
        }
      }

      /**
       * Enable input.
       */
      function enableInput() {
        messageInput.prop("disabled", false);
        sendButton.prop("disabled", false);
        messageInput.focus();
      }

      /**
       * Show typing indicator.
       */
      function showTypingIndicator() {
        typingIndicator.removeClass("hidden").show();
        scrollToBottom();
      }

      /**
       * Hide typing indicator.
       */
      function hideTypingIndicator() {
        typingIndicator.addClass("hidden").hide();
      }

      /**
       * Scroll to bottom of messages.
       */
      function scrollToBottom() {
        messagesContainer.scrollTop(messagesContainer[0].scrollHeight);
      }

      /**
       * Copy text to clipboard.
       */
      function copyToClipboard(text) {
        if (navigator.clipboard) {
          navigator.clipboard.writeText(text);
        } else {
          const textarea = document.createElement("textarea");
          textarea.value = text;
          textarea.style.position = "fixed";
          textarea.style.opacity = "0";
          document.body.appendChild(textarea);
          textarea.select();
          document.execCommand("copy");
          document.body.removeChild(textarea);
        }
      }

      /**
       * Announce to screen reader.
       */
      function announceToScreenReader(message) {
        if (Drupal.announce) {
          Drupal.announce(message);
        }
      }

      /**
       * Get party class.
       */
      function getPartyClass(party) {
        if (!party) return "party-other";
        const lower = party.toLowerCase();
        if (lower.includes("republican") || lower === "r") {
          return "party-republican";
        }
        if (lower.includes("democrat") || lower === "d") {
          return "party-democrat";
        }
        return "party-other";
      }

      /**
       * Escape HTML.
       */
      function escapeHtml(text) {
        if (!text) return "";
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
      }
    },
  };
})(jQuery, Drupal, drupalSettings, once);
