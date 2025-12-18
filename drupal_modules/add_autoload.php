<?php
$json = file_get_contents("/var/www/drupal/composer.json");
$data = json_decode($json, true);
$data["autoload"] = [
    "psr-4" => [
        "Drupal\\page_password_protect\\" => "web/modules/custom/page_password_protect/src/"
    ]
];
file_put_contents("/var/www/drupal/composer.json", json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
echo "Added autoload section\n";
