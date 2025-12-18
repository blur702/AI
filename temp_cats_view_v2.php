<?php
/**
 * Create views for cat breeds content - simplified version.
 * Run with: drush scr /tmp/cats_view.php
 */

use Drupal\views\Entity\View;

echo "=== Creating Cat Breeds Views ===\n\n";

// Check if view already exists
if (View::load('cat_breeds')) {
    echo "View 'cat_breeds' already exists, deleting...\n";
    View::load('cat_breeds')->delete();
}

// Create the view configuration - using proper Drupal 10+ format
$view_config = [
    'id' => 'cat_breeds',
    'label' => 'Cat Breeds',
    'module' => 'views',
    'description' => 'A listing of cat breed articles with filtering',
    'tag' => 'cats',
    'base_table' => 'node_field_data',
    'base_field' => 'nid',
    'display' => [
        'default' => [
            'id' => 'default',
            'display_title' => 'Default',
            'position' => 0,
            'display_options' => [
                'title' => 'Cat Breeds',
                'access' => [
                    'type' => 'perm',
                    'options' => ['perm' => 'access content'],
                ],
                'cache' => [
                    'type' => 'tag',
                    'options' => [],
                ],
                'query' => [
                    'type' => 'views_query',
                    'options' => ['disable_sql_rewrite' => false],
                ],
                'exposed_form' => [
                    'type' => 'basic',
                    'options' => [
                        'submit_button' => 'Filter',
                        'reset_button' => true,
                        'reset_button_label' => 'Reset',
                    ],
                ],
                'pager' => [
                    'type' => 'full',
                    'options' => [
                        'items_per_page' => 12,
                        'offset' => 0,
                        'id' => 0,
                        'total_pages' => null,
                        'expose' => [
                            'items_per_page' => true,
                            'items_per_page_label' => 'Items per page',
                            'items_per_page_options' => '12, 24, 48',
                        ],
                    ],
                ],
                'style' => [
                    'type' => 'default',
                ],
                'row' => [
                    'type' => 'fields',
                ],
                'fields' => [
                    'title' => [
                        'id' => 'title',
                        'table' => 'node_field_data',
                        'field' => 'title',
                        'label' => '',
                        'settings' => ['link_to_entity' => true],
                        'plugin_id' => 'field',
                        'entity_type' => 'node',
                        'entity_field' => 'title',
                    ],
                    'field_origin' => [
                        'id' => 'field_origin',
                        'table' => 'node__field_origin',
                        'field' => 'field_origin',
                        'label' => 'Origin',
                        'plugin_id' => 'field',
                    ],
                    'field_size' => [
                        'id' => 'field_size',
                        'table' => 'node__field_size',
                        'field' => 'field_size',
                        'label' => 'Size',
                        'plugin_id' => 'field',
                    ],
                    'field_coat_type' => [
                        'id' => 'field_coat_type',
                        'table' => 'node__field_coat_type',
                        'field' => 'field_coat_type',
                        'label' => 'Coat',
                        'plugin_id' => 'field',
                    ],
                    'body' => [
                        'id' => 'body',
                        'table' => 'node__body',
                        'field' => 'body',
                        'label' => '',
                        'type' => 'text_trimmed',
                        'settings' => ['trim_length' => 200],
                        'plugin_id' => 'field',
                    ],
                ],
                'filters' => [
                    'status' => [
                        'id' => 'status',
                        'table' => 'node_field_data',
                        'field' => 'status',
                        'value' => '1',
                        'group' => 1,
                        'plugin_id' => 'boolean',
                        'entity_type' => 'node',
                        'entity_field' => 'status',
                    ],
                    'type' => [
                        'id' => 'type',
                        'table' => 'node_field_data',
                        'field' => 'type',
                        'value' => ['cats' => 'cats'],
                        'group' => 1,
                        'plugin_id' => 'bundle',
                        'entity_type' => 'node',
                        'entity_field' => 'type',
                    ],
                    'field_size_value' => [
                        'id' => 'field_size_value',
                        'table' => 'node__field_size',
                        'field' => 'field_size_value',
                        'exposed' => true,
                        'expose' => [
                            'operator_id' => 'field_size_value_op',
                            'label' => 'Size',
                            'identifier' => 'size',
                            'multiple' => true,
                        ],
                        'plugin_id' => 'list_field',
                    ],
                    'field_coat_type_value' => [
                        'id' => 'field_coat_type_value',
                        'table' => 'node__field_coat_type',
                        'field' => 'field_coat_type_value',
                        'exposed' => true,
                        'expose' => [
                            'operator_id' => 'field_coat_type_value_op',
                            'label' => 'Coat Type',
                            'identifier' => 'coat',
                            'multiple' => true,
                        ],
                        'plugin_id' => 'list_field',
                    ],
                    'title' => [
                        'id' => 'title',
                        'table' => 'node_field_data',
                        'field' => 'title',
                        'exposed' => true,
                        'expose' => [
                            'operator_id' => 'title_op',
                            'label' => 'Search',
                            'identifier' => 'search',
                        ],
                        'operator' => 'contains',
                        'plugin_id' => 'string',
                        'entity_type' => 'node',
                        'entity_field' => 'title',
                    ],
                ],
                'sorts' => [
                    'title' => [
                        'id' => 'title',
                        'table' => 'node_field_data',
                        'field' => 'title',
                        'order' => 'ASC',
                        'plugin_id' => 'standard',
                        'entity_type' => 'node',
                        'entity_field' => 'title',
                    ],
                ],
                'empty' => [
                    'area_text_custom' => [
                        'id' => 'area_text_custom',
                        'table' => 'views',
                        'field' => 'area_text_custom',
                        'empty' => true,
                        'content' => 'No cat breeds found matching your criteria.',
                        'plugin_id' => 'text_custom',
                    ],
                ],
                'use_ajax' => true,
            ],
        ],
        'page_1' => [
            'id' => 'page_1',
            'display_title' => 'Page',
            'display_plugin' => 'page',
            'position' => 1,
            'display_options' => [
                'path' => 'cats',
                'menu' => [
                    'type' => 'normal',
                    'title' => 'Cat Breeds',
                    'weight' => 0,
                    'menu_name' => 'main',
                ],
            ],
        ],
        'block_1' => [
            'id' => 'block_1',
            'display_title' => 'Block',
            'display_plugin' => 'block',
            'position' => 2,
            'display_options' => [
                'block_description' => 'Cat Breeds List',
                'pager' => [
                    'type' => 'some',
                    'options' => ['items_per_page' => 5],
                ],
            ],
        ],
    ],
];

try {
    $view = View::create($view_config);
    $view->save();
    echo "Created view: cat_breeds\n";
    echo "  - Page display at /cats\n";
    echo "  - Block display available\n";
    echo "  - Exposed filters: Size, Coat Type, Search\n";
} catch (\Exception $e) {
    echo "Error creating view: " . $e->getMessage() . "\n";
    echo "Trace: " . $e->getTraceAsString() . "\n";
}

// Clear caches
\Drupal::service('router.builder')->rebuild();
drupal_flush_all_caches();
echo "\nCaches cleared. View is ready!\n";
echo "Visit: /cats\n";
