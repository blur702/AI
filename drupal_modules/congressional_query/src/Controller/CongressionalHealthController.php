<?php

namespace Drupal\congressional_query\Controller;

use Drupal\congressional_query\Service\OllamaLLMService;
use Drupal\congressional_query\Service\SSHTunnelService;
use Drupal\congressional_query\Service\WeaviateClientService;
use Drupal\Core\Cache\CacheBackendInterface;
use Drupal\Core\Controller\ControllerBase;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\JsonResponse;

/**
 * Controller for health checks.
 */
class CongressionalHealthController extends ControllerBase {

  /**
   * The SSH tunnel service.
   *
   * @var \Drupal\congressional_query\Service\SSHTunnelService
   */
  protected $sshTunnel;

  /**
   * The Ollama LLM service.
   *
   * @var \Drupal\congressional_query\Service\OllamaLLMService
   */
  protected $ollamaService;

  /**
   * The Weaviate client service.
   *
   * @var \Drupal\congressional_query\Service\WeaviateClientService
   */
  protected $weaviateClient;

  /**
   * The cache backend.
   *
   * @var \Drupal\Core\Cache\CacheBackendInterface
   */
  protected $cache;


  /**
   * Constructs the controller.
   *
   * @param \Drupal\congressional_query\Service\SSHTunnelService $ssh_tunnel
   *   The SSH tunnel service.
   * @param \Drupal\congressional_query\Service\OllamaLLMService $ollama_service
   *   The Ollama LLM service.
   * @param \Drupal\congressional_query\Service\WeaviateClientService $weaviate_client
   *   The Weaviate client service.
   * @param \Drupal\Core\Cache\CacheBackendInterface $cache
   *   The cache backend.
   */
  public function __construct(
    SSHTunnelService $ssh_tunnel,
    OllamaLLMService $ollama_service,
    WeaviateClientService $weaviate_client,
    CacheBackendInterface $cache
  ) {
    $this->sshTunnel = $ssh_tunnel;
    $this->ollamaService = $ollama_service;
    $this->weaviateClient = $weaviate_client;
    $this->cache = $cache;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('congressional_query.ssh_tunnel'),
      $container->get('congressional_query.ollama_llm'),
      $container->get('congressional_query.weaviate_client'),
      $container->get('cache.default')
    );
  }

  /**
   * Perform health check on all services.
   *
   * @return \Symfony\Component\HttpFoundation\JsonResponse
   *   JSON response with health status.
   */
  public function check(): JsonResponse {
    // Check cache first.
    $cacheKey = 'congressional_query:health_check';
    $cached = $this->cache->get($cacheKey);

    if ($cached) {
      return new JsonResponse($cached->data);
    }

    $response = [
      'timestamp' => time(),
      'overall' => 'ok',
      'services' => [],
    ];

    // Check SSH tunnel.
    try {
      $sshHealth = $this->sshTunnel->checkTunnelHealth();
      $response['services']['ssh'] = [
        'status' => $sshHealth['status'],
        'message' => $sshHealth['message'],
        'details' => $sshHealth['details'] ?? [],
      ];
    }
    catch (\Exception $e) {
      $response['services']['ssh'] = [
        'status' => 'error',
        'message' => $e->getMessage(),
        'details' => [],
      ];
    }

    // Check Ollama.
    try {
      $ollamaHealth = $this->ollamaService->checkHealth();
      $response['services']['ollama'] = [
        'status' => $ollamaHealth['status'],
        'message' => $ollamaHealth['message'],
        'models' => $ollamaHealth['models'] ?? [],
        'details' => $ollamaHealth['details'] ?? [],
      ];
    }
    catch (\Exception $e) {
      $response['services']['ollama'] = [
        'status' => 'error',
        'message' => $e->getMessage(),
        'models' => [],
        'details' => [],
      ];
    }

    // Check Weaviate.
    try {
      $weaviateHealth = $this->weaviateClient->checkHealth();
      $collectionStats = $this->weaviateClient->getCollectionStats();
      $response['services']['weaviate'] = [
        'status' => $weaviateHealth['status'],
        'message' => $weaviateHealth['message'],
        'details' => array_merge(
          $weaviateHealth['details'] ?? [],
          ['document_count' => $collectionStats['count'] ?? 0]
        ),
      ];
    }
    catch (\Exception $e) {
      $response['services']['weaviate'] = [
        'status' => 'error',
        'message' => $e->getMessage(),
        'details' => [],
      ];
    }

    // Determine overall status.
    $hasError = FALSE;
    $hasWarning = FALSE;

    foreach ($response['services'] as $service) {
      if ($service['status'] === 'error') {
        $hasError = TRUE;
      }
      elseif ($service['status'] === 'warning') {
        $hasWarning = TRUE;
      }
    }

    if ($hasError) {
      $response['overall'] = 'error';
    }
    elseif ($hasWarning) {
      $response['overall'] = 'warning';
    }

    // Cache the response using the configurable health check interval.
    $cacheInterval = $this->sshTunnel->getHealthCheckInterval();
    $this->cache->set($cacheKey, $response, time() + $cacheInterval);

    return new JsonResponse($response);
  }

  /**
   * Test a specific connection.
   *
   * @param string $type
   *   The connection type (ssh, ollama, weaviate).
   *
   * @return \Symfony\Component\HttpFoundation\JsonResponse
   *   JSON response with test result.
   */
  public function testConnection(string $type): JsonResponse {
    $result = [
      'type' => $type,
      'timestamp' => time(),
    ];

    try {
      switch ($type) {
        case 'ssh':
          $health = $this->sshTunnel->checkTunnelHealth();
          $result['status'] = $health['status'];
          $result['message'] = $health['message'];
          $result['details'] = $health['details'] ?? [];
          break;

        case 'ollama':
          $health = $this->ollamaService->checkHealth();
          $result['status'] = $health['status'];
          $result['message'] = $health['message'];
          $result['models'] = $health['models'] ?? [];
          break;

        case 'weaviate':
          $health = $this->weaviateClient->checkHealth();
          $stats = $this->weaviateClient->getCollectionStats();
          $result['status'] = $health['status'];
          $result['message'] = $health['message'];
          $result['details'] = $health['details'] ?? [];
          $result['collection'] = $stats;
          break;

        default:
          return new JsonResponse([
            'error' => 'Unknown connection type: ' . $type,
          ], 400);
      }
    }
    catch (\Exception $e) {
      $result['status'] = 'error';
      $result['message'] = $e->getMessage();
    }

    // Clear health cache after test.
    $this->cache->delete('congressional_query:health_check');

    return new JsonResponse($result);
  }

}
