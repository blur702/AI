<?php
use Drupal\Core\DrupalKernel;
use Symfony\Component\HttpFoundation\Request;

$autoloader = require_once '/var/www/drupal/web/autoload.php';
$request = Request::createFromGlobals();
$kernel = DrupalKernel::createFromRequest($request, $autoloader, 'prod');
$kernel->boot();
$kernel->preHandle($request);

// Use config factory to create webform (bypasses entity validation)
$config = \Drupal::configFactory()->getEditable('webform.webform.test_simple');
$config->setData([
    'uuid' => \Drupal::service('uuid')->generate(),
    'langcode' => 'en',
    'status' => 'open',
    'dependencies' => [],
    'weight' => 0,
    'open' => null,
    'close' => null,
    'uid' => 1,
    'template' => false,
    'archive' => false,
    'id' => 'test_simple',
    'title' => 'Test Simple Form',
    'description' => 'A test form created via MCP',
    'categories' => [],
    'elements' => "name:\n  '#type': textfield\n  '#title': 'Your Name'\n  '#required': true\nemail:\n  '#type': email\n  '#title': 'Your Email'\n  '#required': true\nactions:\n  '#type': webform_actions\n  '#title': 'Submit button(s)'",
    'css' => '',
    'javascript' => '',
    'settings' => [
        'ajax' => false,
        'page' => true,
        'form_title' => 'source_entity_webform',
        'confirmation_type' => 'page',
        'confirmation_message' => 'Thank you for your submission.',
    ],
    'access' => [
        'create' => ['roles' => ['anonymous', 'authenticated'], 'users' => [], 'permissions' => []],
        'view_any' => ['roles' => [], 'users' => [], 'permissions' => []],
        'update_any' => ['roles' => [], 'users' => [], 'permissions' => []],
        'delete_any' => ['roles' => [], 'users' => [], 'permissions' => []],
        'purge_any' => ['roles' => [], 'users' => [], 'permissions' => []],
        'view_own' => ['roles' => [], 'users' => [], 'permissions' => []],
        'update_own' => ['roles' => [], 'users' => [], 'permissions' => []],
        'delete_own' => ['roles' => [], 'users' => [], 'permissions' => []],
        'administer' => ['roles' => [], 'users' => [], 'permissions' => []],
        'test' => ['roles' => [], 'users' => [], 'permissions' => []],
    ],
    'handlers' => [],
    'variants' => [],
]);
$config->save(TRUE);
echo json_encode(['success' => true, 'id' => 'test_simple']);
