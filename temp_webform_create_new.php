case 'webform_create':
    if (!isset($args['id']) || !isset($args['title'])) error('id and title required');
    $elements_yaml = '';
    if (isset($args['elements'])) {
        if (is_string($args['elements'])) {
            $elements_yaml = $args['elements'];
        } elseif (is_array($args['elements'])) {
            $elements_yaml = \Drupal\Component\Serialization\Yaml::encode($args['elements']);
        }
    }
    $config = \Drupal::configFactory()->getEditable('webform.webform.' . $args['id']);
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
        'id' => $args['id'],
        'title' => $args['title'],
        'description' => $args['description'] ?? '',
        'categories' => [],
        'elements' => $elements_yaml,
        'css' => '',
        'javascript' => '',
        'settings' => [
            'ajax' => false,
            'page' => true,
            'form_title' => 'source_entity_webform',
            'confirmation_type' => 'page',
            'confirmation_message' => $args['confirmation_message'] ?? 'Thank you for your submission.',
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
    \Drupal::service('cache.config')->deleteAll();
    output(['success' => true, 'id' => $args['id'], 'path' => '/webform/' . $args['id']]);
    break;
