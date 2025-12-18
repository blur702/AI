<?php

namespace Drupal\congressional_query\Entity;

/**
 * Represents an API key for REST API authentication.
 */
class ApiKey {

  /**
   * The key ID.
   *
   * @var int
   */
  protected $id;

  /**
   * The hashed API key.
   *
   * @var string
   */
  protected $apiKey;

  /**
   * The key prefix for identification.
   *
   * @var string
   */
  protected $keyPrefix;

  /**
   * The human-readable name.
   *
   * @var string
   */
  protected $name;

  /**
   * The user ID who owns this key.
   *
   * @var int
   */
  protected $uid;

  /**
   * The creation timestamp.
   *
   * @var int
   */
  protected $created;

  /**
   * The last used timestamp.
   *
   * @var int|null
   */
  protected $lastUsed;

  /**
   * Whether the key is active.
   *
   * @var bool
   */
  protected $isActive;

  /**
   * Custom rate limit for this key.
   *
   * @var int|null
   */
  protected $rateLimitOverride;

  /**
   * Allowed IP addresses (JSON).
   *
   * @var string|null
   */
  protected $allowedIps;

  /**
   * Constructs an ApiKey object.
   *
   * @param array $data
   *   The key data.
   */
  public function __construct(array $data = []) {
    $this->id = $data['id'] ?? NULL;
    $this->apiKey = $data['api_key'] ?? '';
    $this->keyPrefix = $data['key_prefix'] ?? '';
    $this->name = $data['name'] ?? '';
    $this->uid = (int) ($data['uid'] ?? 0);
    $this->created = (int) ($data['created'] ?? time());
    $this->lastUsed = $data['last_used'] ?? NULL;
    $this->isActive = (bool) ($data['is_active'] ?? TRUE);
    $this->rateLimitOverride = $data['rate_limit_override'] ?? NULL;
    $this->allowedIps = $data['allowed_ips'] ?? NULL;
  }

  /**
   * Gets the key ID.
   *
   * @return int|null
   *   The key ID.
   */
  public function getId(): ?int {
    return $this->id;
  }

  /**
   * Gets the hashed API key.
   *
   * @return string
   *   The hashed key.
   */
  public function getApiKey(): string {
    return $this->apiKey;
  }

  /**
   * Gets the key prefix.
   *
   * @return string
   *   The key prefix.
   */
  public function getKeyPrefix(): string {
    return $this->keyPrefix;
  }

  /**
   * Gets the key name.
   *
   * @return string
   *   The name.
   */
  public function getName(): string {
    return $this->name;
  }

  /**
   * Gets the owner user ID.
   *
   * @return int
   *   The user ID.
   */
  public function getUid(): int {
    return $this->uid;
  }

  /**
   * Gets the creation timestamp.
   *
   * @return int
   *   The timestamp.
   */
  public function getCreated(): int {
    return $this->created;
  }

  /**
   * Gets the last used timestamp.
   *
   * @return int|null
   *   The timestamp or NULL.
   */
  public function getLastUsed(): ?int {
    return $this->lastUsed;
  }

  /**
   * Checks if the key is active.
   *
   * @return bool
   *   TRUE if active.
   */
  public function isActive(): bool {
    return $this->isActive;
  }

  /**
   * Gets the rate limit override.
   *
   * @return int|null
   *   The rate limit or NULL.
   */
  public function getRateLimitOverride(): ?int {
    return $this->rateLimitOverride;
  }

  /**
   * Gets allowed IPs.
   *
   * @return array
   *   Array of allowed IPs.
   */
  public function getAllowedIps(): array {
    if (empty($this->allowedIps)) {
      return [];
    }
    $ips = json_decode($this->allowedIps, TRUE);
    return is_array($ips) ? $ips : [];
  }

  /**
   * Checks if an IP is allowed.
   *
   * @param string $ip
   *   The IP address to check.
   *
   * @return bool
   *   TRUE if allowed or no restrictions.
   */
  public function isIpAllowed(string $ip): bool {
    $allowed = $this->getAllowedIps();
    if (empty($allowed)) {
      return TRUE;
    }
    return in_array($ip, $allowed, TRUE);
  }

  /**
   * Converts the entity to an array.
   *
   * @return array
   *   The entity data.
   */
  public function toArray(): array {
    return [
      'id' => $this->id,
      'api_key' => $this->apiKey,
      'key_prefix' => $this->keyPrefix,
      'name' => $this->name,
      'uid' => $this->uid,
      'created' => $this->created,
      'last_used' => $this->lastUsed,
      'is_active' => $this->isActive ? 1 : 0,
      'rate_limit_override' => $this->rateLimitOverride,
      'allowed_ips' => $this->allowedIps,
    ];
  }

}
