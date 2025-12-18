<?php
/**
 * Add image field to cats content type.
 */

use Drupal\field\Entity\FieldStorageConfig;
use Drupal\field\Entity\FieldConfig;
use Drupal\Core\Entity\Entity\EntityFormDisplay;
use Drupal\Core\Entity\Entity\EntityViewDisplay;

echo "=== Adding Image Field to Cats Content Type ===\n\n";

// Create the field storage if it doesn't exist
$field_storage = FieldStorageConfig::loadByName('node', 'field_cat_image');
if (!$field_storage) {
    $field_storage = FieldStorageConfig::create([
        'field_name' => 'field_cat_image',
        'entity_type' => 'node',
        'type' => 'image',
        'cardinality' => 1,
        'settings' => [
            'target_type' => 'file',
            'display_field' => false,
            'display_default' => false,
            'uri_scheme' => 'public',
        ],
    ]);
    $field_storage->save();
    echo "Created field storage: field_cat_image\n";
} else {
    echo "Field storage already exists: field_cat_image\n";
}

// Create the field instance for cats content type
$field = FieldConfig::loadByName('node', 'cats', 'field_cat_image');
if (!$field) {
    $field = FieldConfig::create([
        'field_storage' => $field_storage,
        'bundle' => 'cats',
        'label' => 'Cat Image',
        'required' => false,
        'settings' => [
            'file_directory' => 'cats',
            'alt_field' => true,
            'alt_field_required' => true,
            'title_field' => false,
            'max_resolution' => '',
            'min_resolution' => '',
            'default_image' => [
                'uuid' => '',
                'alt' => '',
                'title' => '',
                'width' => null,
                'height' => null,
            ],
            'file_extensions' => 'png gif jpg jpeg webp',
            'max_filesize' => '5 MB',
        ],
    ]);
    $field->save();
    echo "Created field instance: field_cat_image on cats\n";
} else {
    echo "Field instance already exists: field_cat_image on cats\n";
}

// Add to form display
$form_display = EntityFormDisplay::load('node.cats.default');
if ($form_display) {
    $form_display->setComponent('field_cat_image', [
        'type' => 'image_image',
        'weight' => 0,
        'settings' => [
            'progress_indicator' => 'throbber',
            'preview_image_style' => 'medium',
        ],
    ])->save();
    echo "Added field to form display\n";
}

// Add to view display
$view_display = EntityViewDisplay::load('node.cats.default');
if ($view_display) {
    $view_display->setComponent('field_cat_image', [
        'type' => 'image',
        'weight' => 0,
        'label' => 'hidden',
        'settings' => [
            'image_style' => 'large',
            'image_link' => '',
        ],
    ])->save();
    echo "Added field to view display\n";
}

// Add teaser display
$teaser_display = EntityViewDisplay::load('node.cats.teaser');
if ($teaser_display) {
    $teaser_display->setComponent('field_cat_image', [
        'type' => 'image',
        'weight' => 0,
        'label' => 'hidden',
        'settings' => [
            'image_style' => 'medium',
            'image_link' => 'content',
        ],
    ])->save();
    echo "Added field to teaser display\n";
}

drupal_flush_all_caches();
echo "\nImage field added successfully!\n";
