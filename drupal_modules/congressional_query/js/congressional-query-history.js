/**
 * @file
 * JavaScript for Congressional Query history page.
 */

(function ($, Drupal, once) {
  'use strict';

  /**
   * Query history behavior.
   */
  Drupal.behaviors.congressionalQueryHistory = {
    attach: function (context, settings) {
      const $page = $(once('query-history', '.congressional-query-history', context));

      if ($page.length === 0) {
        return;
      }

      // Handle delete button clicks.
      $page.on('click', '.delete-link', function (e) {
        e.preventDefault();

        const $btn = $(this);
        const queryId = $btn.data('query-id');
        const deleteUrl = $btn.data('delete-url');

        if (!confirm(Drupal.t('Are you sure you want to delete query #@id?', {'@id': queryId}))) {
          return;
        }

        $btn.prop('disabled', true).text(Drupal.t('Deleting...'));

        $.ajax({
          url: deleteUrl,
          method: 'POST',
          headers: {
            'X-Requested-With': 'XMLHttpRequest'
          },
          success: function (response) {
            // Remove the row with animation.
            $('#query-row-' + queryId).fadeOut(300, function () {
              $(this).remove();
              updateResultsCount();
            });
            showMessage(Drupal.t('Query deleted successfully.'), 'status');
          },
          error: function (xhr) {
            $btn.prop('disabled', false).text(Drupal.t('Delete'));
            showMessage(Drupal.t('Failed to delete query.'), 'error');
          }
        });
      });

      // Client-side quick filter.
      const $quickFilter = $('<input>', {
        type: 'text',
        class: 'quick-filter',
        placeholder: Drupal.t('Quick filter...'),
      });

      $page.find('.results-summary').after($quickFilter);

      $quickFilter.on('keyup', debounce(function () {
        const filterValue = $(this).val().toLowerCase();
        $page.find('.query-row').each(function () {
          const $row = $(this);
          const text = $row.text().toLowerCase();
          $row.toggle(text.includes(filterValue));
        });
      }, 200));

      // Row selection for bulk operations.
      initRowSelection($page);

      /**
       * Update results count after deletion.
       */
      function updateResultsCount() {
        const $summary = $page.find('.results-summary');
        const currentText = $summary.text();
        const match = currentText.match(/of (\d+) results/);
        if (match) {
          const total = parseInt(match[1]) - 1;
          const newText = currentText.replace(/of \d+ results/, 'of ' + total + ' results');
          $summary.text(newText);
        }
      }

      /**
       * Show a message.
       */
      function showMessage(message, type) {
        if (typeof Drupal.Message !== 'undefined') {
          const messageArea = new Drupal.Message();
          messageArea.add(message, {type: type});
        } else {
          alert(message);
        }
      }

      /**
       * Initialize row selection.
       */
      function initRowSelection($container) {
        // Add checkboxes to each row.
        $container.find('.query-row').each(function () {
          const $row = $(this);
          const queryId = $row.attr('id').replace('query-row-', '');
          const $checkbox = $('<input>', {
            type: 'checkbox',
            class: 'row-select',
            'data-query-id': queryId,
          });
          $row.find('td:first').prepend($checkbox);
        });

        // Add select all checkbox to header.
        const $selectAll = $('<input>', {
          type: 'checkbox',
          class: 'select-all',
        });
        $container.find('th.column-id').prepend($selectAll);

        // Select all handler.
        $selectAll.on('change', function () {
          const checked = $(this).is(':checked');
          $container.find('.row-select').prop('checked', checked);
          updateBulkActions();
        });

        // Individual checkbox handler.
        $container.on('change', '.row-select', function () {
          updateBulkActions();
        });
      }

      /**
       * Update bulk action visibility.
       */
      function updateBulkActions() {
        const selectedCount = $page.find('.row-select:checked').length;
        let $bulkActions = $page.find('.bulk-actions');

        if (selectedCount > 0) {
          if ($bulkActions.length === 0) {
            $bulkActions = $('<div>', {class: 'bulk-actions'});
            $bulkActions.html(
              '<span class="selected-count">' + selectedCount + ' ' + Drupal.t('selected') + '</span>' +
              '<button type="button" class="button bulk-delete">' + Drupal.t('Delete Selected') + '</button>'
            );
            $page.find('.history-header').append($bulkActions);

            $bulkActions.find('.bulk-delete').on('click', function () {
              if (!confirm(Drupal.t('Are you sure you want to delete @count queries?', {'@count': selectedCount}))) {
                return;
              }
              // Collect selected IDs and delete them.
              const ids = [];
              $page.find('.row-select:checked').each(function () {
                ids.push($(this).data('query-id'));
              });
              // For now, delete one by one.
              ids.forEach(function (id) {
                $page.find('.delete-link[data-query-id="' + id + '"]').trigger('click');
              });
            });
          } else {
            $bulkActions.find('.selected-count').text(selectedCount + ' ' + Drupal.t('selected'));
          }
        } else {
          $bulkActions.remove();
        }
      }

      /**
       * Debounce function.
       */
      function debounce(func, wait) {
        let timeout;
        return function () {
          const context = this;
          const args = arguments;
          clearTimeout(timeout);
          timeout = setTimeout(function () {
            func.apply(context, args);
          }, wait);
        };
      }
    }
  };

})(jQuery, Drupal, once);
