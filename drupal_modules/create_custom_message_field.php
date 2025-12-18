<?php
/**
 * Script to create the missing field_page_password_custom_message field.
 * Run with: drush php:script create_custom_message_field.php
 */

use Drupal\field\Entity\FieldConfig;
use Drupal\field\Entity\FieldStorageConfig;

$field_name = 'field_page_password_custom_message';

// Create field storage if it doesn't exist.
$storage = FieldStorageConfig::loadByName('node', $field_name);
if (!$storage) {
  FieldStorageConfig::create([
    'field_name' => $field_name,
    'entity_type' => 'node',
    'type' => 'string_long',
    'settings' => [],
    'cardinality' => 1,
    'translatable' => FALSE,
  ])->save();
  echo "Created field storage for $field_name\n";
} else {
  echo "Field storage already exists for $field_name\n";
}

// Create field for each node type.
$entity_manager = \Drupal::entityTypeManager();
$node_types = $entity_manager->getStorage('node_type')->loadMultiple();

foreach ($node_types as $bundle => $type) {
  $field = FieldConfig::loadByName('node', $bundle, $field_name);
  if (!$field) {
    FieldConfig::create([
      'field_name' => $field_name,
      'entity_type' => 'node',
      'bundle' => $bundle,
      'label' => 'Custom Access Message',
      'description' => 'Custom message shown on the password form.',
      'settings' => [],
      'required' => FALSE,
      'default_value' => '',
      'cardinality' => 1,
    ])->save();
    echo "Created field for bundle: $bundle\n";
  } else {
    echo "Field already exists for bundle: $bundle\n";
  }
}

echo "Done!\n";
