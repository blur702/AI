case 'webform_list':
    $storage = \Drupal::entityTypeManager()->getStorage('webform');
    $webforms = $storage->loadMultiple();
    $result = [];
    foreach ($webforms as $webform) {
        $result[] = [
            'id' => $webform->id(),
            'title' => $webform->label(),
            'status' => $webform->get('status'),
            'open' => $webform->isOpen(),
        ];
    }
    output(['webforms' => $result]);
    break;
case 'webform_get':
    if (!isset($args['id'])) error('id required');
    $config = \Drupal::config('webform.webform.' . $args['id']);
    if ($config->isNew()) error('Webform not found');
    $raw = $config->getRawData();
    output([
        'id' => $raw['id'] ?? $args['id'],
        'title' => $raw['title'] ?? '',
        'status' => $raw['status'] ?? '',
        'elements' => $raw['elements'] ?? '',
        'settings' => $raw['settings'] ?? [],
    ]);
    break;
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
    try { $config->save(TRUE); } catch (\Exception $e) { }
    output(['success' => true, 'id' => $args['id'], 'path' => '/webform/' . $args['id']]);
    break;
case 'webform_delete':
    if (!isset($args['id'])) error('id required');
    $config = \Drupal::configFactory()->getEditable('webform.webform.' . $args['id']);
    if ($config->isNew()) error('Webform not found');
    try { $config->delete(); } catch (\Exception $e) { }
    output(['success' => true]);
    break;
case 'webform_submission_list':
    if (!isset($args['webform_id'])) error('webform_id required');
    $storage = \Drupal::entityTypeManager()->getStorage('webform_submission');
    $query = $storage->getQuery()->accessCheck(TRUE)->condition('webform_id', $args['webform_id'])->range(0, $args['limit'] ?? 50);
    $ids = $query->execute();
    $submissions = $storage->loadMultiple($ids);
    $result = [];
    foreach ($submissions as $submission) {
        $result[] = [
            'sid' => $submission->id(),
            'created' => date('Y-m-d H:i:s', $submission->getCreatedTime()),
            'data' => $submission->getData(),
        ];
    }
    output(['submissions' => $result]);
    break;
case 'webform_element_add':
    if (!isset($args['webform_id']) || !isset($args['key']) || !isset($args['type'])) error('webform_id, key, type required');
    $config = \Drupal::configFactory()->getEditable('webform.webform.' . $args['webform_id']);
    if ($config->isNew()) error('Webform not found');
    $elements_yaml = $config->get('elements') ?? '';
    $elements = \Drupal\Component\Serialization\Yaml::decode($elements_yaml) ?? [];
    $element = ['#type' => $args['type'], '#title' => $args['title'] ?? ucfirst($args['key'])];
    if (isset($args['required'])) $element['#required'] = (bool)$args['required'];
    if (isset($args['options'])) $element['#options'] = $args['options'];
    $elements[$args['key']] = $element;
    $config->set('elements', \Drupal\Component\Serialization\Yaml::encode($elements));
    try { $config->save(TRUE); } catch (\Exception $e) { }
    output(['success' => true, 'element' => $element]);
    break;
