<?php
/**
 * Import cat breeds view from YAML.
 */

use Drupal\views\Entity\View;
use Symfony\Component\Yaml\Yaml;

echo "=== Importing Cat Breeds View ===\n\n";

// Delete existing view if it exists
if (View::load('cat_breeds')) {
    View::load('cat_breeds')->delete();
    echo "Deleted existing view.\n";
}

// Load the YAML config
$yaml_content = file_get_contents('/tmp/cat_breeds.yml');
$config = Yaml::parse($yaml_content);

// Remove uuid as it will be generated
unset($config['uuid']);

try {
    $view = View::create($config);
    $view->save();
    echo "Successfully imported view: cat_breeds\n";
    echo "  - Page display at /cats\n";
    echo "  - Block display available\n";
    echo "  - Filters: Size, Coat Type, Search\n";
} catch (\Exception $e) {
    echo "Error importing view: " . $e->getMessage() . "\n";
}

// Rebuild routes and clear cache
\Drupal::service('router.builder')->rebuild();
drupal_flush_all_caches();
echo "\nCaches cleared. View is ready!\n";
echo "Visit: https://ssdd.kevinalthaus.com/cats\n";
