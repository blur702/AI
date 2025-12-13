<?php
/**
 * Update cat_breeds view to display images.
 */

use Drupal\views\Entity\View;

echo "=== Updating Cat Breeds View to Display Images ===\n\n";

$view = View::load('cat_breeds');
if (!$view) {
    echo "View 'cat_breeds' not found!\n";
    exit(1);
}

$display = &$view->getDisplay('default');

// Add the image field to the beginning of fields
$image_field = [
    'id' => 'field_cat_image',
    'table' => 'node__field_cat_image',
    'field' => 'field_cat_image',
    'relationship' => 'none',
    'group_type' => 'group',
    'admin_label' => '',
    'plugin_id' => 'field',
    'label' => '',
    'exclude' => false,
    'alter' => [
        'alter_text' => false,
        'text' => '',
        'make_link' => false,
        'path' => '',
        'absolute' => false,
        'external' => false,
        'replace_spaces' => false,
        'path_case' => 'none',
        'trim_whitespace' => false,
        'alt' => '',
        'rel' => '',
        'link_class' => '',
        'prefix' => '',
        'suffix' => '',
        'target' => '',
        'nl2br' => false,
        'max_length' => 0,
        'word_boundary' => true,
        'ellipsis' => true,
        'more_link' => false,
        'more_link_text' => '',
        'more_link_path' => '',
        'strip_tags' => false,
        'trim' => false,
        'preserve_tags' => '',
        'html' => false,
    ],
    'element_type' => '',
    'element_class' => '',
    'element_label_type' => '',
    'element_label_class' => '',
    'element_label_colon' => false,
    'element_wrapper_type' => '',
    'element_wrapper_class' => '',
    'element_default_classes' => true,
    'empty' => '',
    'hide_empty' => false,
    'empty_zero' => false,
    'hide_alter_empty' => true,
    'click_sort_column' => 'target_id',
    'type' => 'image',
    'settings' => [
        'image_style' => 'medium',
        'image_link' => 'content',
    ],
    'group_column' => '',
    'group_columns' => [],
    'group_rows' => true,
    'delta_limit' => 0,
    'delta_offset' => 0,
    'delta_reversed' => false,
    'delta_first_last' => false,
    'multi_type' => 'separator',
    'separator' => ', ',
    'field_api_classes' => false,
];

// Get existing fields and prepend image
$existing_fields = $display['display_options']['fields'] ?? [];
$new_fields = ['field_cat_image' => $image_field] + $existing_fields;
$display['display_options']['fields'] = $new_fields;

// Update the style to use a grid/table for better image display
$display['display_options']['style'] = [
    'type' => 'html_list',
    'options' => [
        'grouping' => [],
        'row_class' => 'cat-breed-item',
        'default_row_class' => true,
        'type' => 'ul',
        'wrapper_class' => 'cat-breeds-grid',
        'class' => 'cat-breeds-list',
    ],
];

$view->save();
echo "View updated with image field!\n";

// Clear caches
drupal_flush_all_caches();
echo "Caches cleared.\n";
echo "Visit: https://kevinalthaus.com/cats\n";
