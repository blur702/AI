<?php
/**
 * Add cat images to all cat articles using cataas.com API.
 * Run with: drush scr /tmp/add_cat_images.php
 */

use Drupal\node\Entity\Node;
use Drupal\file\Entity\File;

echo "=== Adding Cat Images to Articles ===\n\n";

// Ensure directory exists
$directory = 'public://cats';
\Drupal::service('file_system')->prepareDirectory($directory, \Drupal\Core\File\FileSystemInterface::CREATE_DIRECTORY);

// Get all cat nodes
$nids = \Drupal::entityQuery('node')
    ->condition('type', 'cats')
    ->accessCheck(FALSE)
    ->execute();

$nodes = Node::loadMultiple($nids);
$count = 0;
$total = count($nodes);

echo "Found $total cat articles to process.\n\n";

foreach ($nodes as $node) {
    $title = $node->getTitle();
    $nid = $node->id();

    // Skip if already has an image
    if (!$node->get('field_cat_image')->isEmpty()) {
        echo "[$nid] $title - already has image, skipping\n";
        continue;
    }

    // Create safe filename
    $safe_name = preg_replace('/[^a-z0-9]+/', '_', strtolower($title));
    $filename = "cat_{$safe_name}_{$nid}.jpg";
    $destination = "$directory/$filename";

    // Fetch a cat image from cataas.com with the breed name as text overlay
    // Using 800x600 for good quality
    $cat_api_url = "https://cataas.com/cat?width=800&height=600";

    echo "[$nid] $title - fetching image... ";

    try {
        // Use Drupal's HTTP client
        $client = \Drupal::httpClient();
        $response = $client->get($cat_api_url, [
            'timeout' => 30,
            'headers' => [
                'User-Agent' => 'Drupal/10',
            ],
        ]);

        if ($response->getStatusCode() == 200) {
            $image_data = $response->getBody()->getContents();

            // Save the file
            $file = \Drupal::service('file.repository')->writeData(
                $image_data,
                $destination,
                \Drupal\Core\File\FileSystemInterface::EXISTS_REPLACE
            );

            if ($file) {
                // Attach to node
                $node->set('field_cat_image', [
                    'target_id' => $file->id(),
                    'alt' => $title . ' cat breed',
                    'title' => $title,
                ]);
                $node->save();

                $count++;
                echo "done (file id: " . $file->id() . ")\n";
            } else {
                echo "failed to save file\n";
            }
        } else {
            echo "API returned " . $response->getStatusCode() . "\n";
        }
    } catch (\Exception $e) {
        echo "error: " . $e->getMessage() . "\n";
    }

    // Small delay to be nice to the API
    usleep(500000); // 0.5 second
}

echo "\n=== Completed! Added images to $count articles ===\n";
