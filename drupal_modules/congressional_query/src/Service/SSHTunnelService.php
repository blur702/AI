<?php

namespace Drupal\congressional_query\Service;

use Drupal\congressional_query\Exception\SSHAuthenticationException;
use Drupal\congressional_query\Exception\SSHCommandException;
use Drupal\congressional_query\Exception\SSHConnectionException;
use Drupal\congressional_query\Exception\SSHTimeoutException;
use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\State\StateInterface;
use phpseclib3\Net\SSH2;
use phpseclib3\Crypt\PublicKeyLoader;
use Psr\Log\LoggerInterface;

/**
 * Service for managing SSH connections to access remote AI services.
 *
 * IMPORTANT ARCHITECTURE NOTE:
 * This service uses a "remote curl execution" pattern rather than true SSH port
 * forwarding. This approach was chosen because phpseclib3 does not support
 * native SSH port forwarding (-L flag). Instead of forwarding ports locally,
 * this service:
 *
 * 1. Establishes an SSH connection to the target host (typically a Windows
 *    machine running Ollama and Weaviate services).
 * 2. Executes curl commands remotely on the SSH target to access localhost
 *    services (Ollama on port 11434, Weaviate on port 8080).
 * 3. Returns the results over the SSH connection back to Drupal.
 *
 * IMPLICATIONS:
 * - There is NO shared forwarded port available for arbitrary consumers.
 * - All HTTP requests to Ollama/Weaviate must go through this service's
 *   makeHttpRequest() method.
 * - External code cannot directly connect to the AI services; they must use
 *   the provided service classes (OllamaLLMService, WeaviateClientService).
 *
 * REMOTE OS SUPPORT:
 * - The remote target OS is configurable via 'ssh.remote_os' setting.
 * - Supported values: 'linux' (default), 'windows'.
 * - Linux targets use /tmp and POSIX shell quoting.
 * - Windows targets use %TEMP% and PowerShell-compatible escaping.
 *
 * @see \Drupal\congressional_query\Service\OllamaLLMService
 * @see \Drupal\congressional_query\Service\WeaviateClientService
 */
class SSHTunnelService {

  /**
   * Maximum connection retry attempts.
   */
  const DEFAULT_MAX_RETRIES = 3;

  /**
   * Connection timeout in seconds.
   */
  const DEFAULT_CONNECTION_TIMEOUT = 30;

  /**
   * Command timeout in seconds.
   */
  const DEFAULT_COMMAND_TIMEOUT = 120;

  /**
   * Connection idle timeout before refresh (5 minutes).
   */
  const CONNECTION_IDLE_TIMEOUT = 300;

  /**
   * Health check cache duration in seconds.
   */
  const HEALTH_CHECK_CACHE_DURATION = 30;

  /**
   * The config factory.
   *
   * @var \Drupal\Core\Config\ConfigFactoryInterface
   */
  protected $configFactory;

  /**
   * The logger.
   *
   * @var \Psr\Log\LoggerInterface
   */
  protected $logger;

  /**
   * The state service.
   *
   * @var \Drupal\Core\State\StateInterface
   */
  protected $state;

  /**
   * The SSH connection instance.
   *
   * @var \phpseclib3\Net\SSH2|null
   */
  protected $sshConnection = NULL;

  /**
   * Configuration validation state.
   *
   * @var bool|null
   */
  protected $configValid = NULL;

  /**
   * Configuration validation errors.
   *
   * @var array
   */
  protected $configErrors = [];

  /**
   * Last error details.
   *
   * @var array|null
   */
  protected $lastError = NULL;

  /**
   * Constructs the SSHTunnelService.
   *
   * @param \Drupal\Core\Config\ConfigFactoryInterface $config_factory
   *   The config factory.
   * @param \Psr\Log\LoggerInterface $logger
   *   The logger.
   * @param \Drupal\Core\State\StateInterface $state
   *   The state service.
   */
  public function __construct(
    ConfigFactoryInterface $config_factory,
    LoggerInterface $logger,
    StateInterface $state
  ) {
    $this->configFactory = $config_factory;
    $this->logger = $logger;
    $this->state = $state;

    // Validate configuration on construction.
    $this->validateConfig();
  }

  // ===========================================================================
  // Configuration Validation Methods (Step 1)
  // ===========================================================================

  /**
   * Validate SSH and service endpoint configuration completeness.
   *
   * Validates SSH settings, Ollama endpoint, Weaviate endpoint, and
   * remote OS configuration. All configuration must be valid for
   * connect() to succeed.
   *
   * @return bool
   *   TRUE if configuration is valid.
   */
  public function validateConfig(): bool {
    if ($this->configValid !== NULL) {
      return $this->configValid;
    }

    $this->configErrors = [];
    $config = $this->getConfig();

    // =======================================================================
    // SSH Configuration Validation
    // =======================================================================

    // Check required SSH fields.
    if (empty($config->get('ssh.host'))) {
      $this->configErrors[] = 'SSH host is not configured.';
    }

    if (empty($config->get('ssh.username'))) {
      $this->configErrors[] = 'SSH username is not configured.';
    }

    // Check authentication - need either password or private key.
    $hasPassword = !empty($config->get('ssh.password'));
    $hasPrivateKey = !empty($config->get('ssh.private_key_path'));

    if (!$hasPassword && !$hasPrivateKey) {
      $this->configErrors[] = 'SSH authentication not configured. Provide either password or private key path.';
    }

    // Validate private key path if specified.
    $privateKeyPath = $config->get('ssh.private_key_path');
    if (!empty($privateKeyPath) && !file_exists($privateKeyPath)) {
      $this->configErrors[] = 'SSH private key file does not exist: ' . $privateKeyPath;
    }

    // Validate SSH port range.
    $sshPort = $config->get('ssh.port');
    if ($sshPort && ($sshPort < 1 || $sshPort > 65535)) {
      $this->configErrors[] = 'SSH port must be between 1 and 65535.';
    }

    // Validate remote_os setting if present.
    $remoteOs = $config->get('ssh.remote_os');
    if (!empty($remoteOs) && !in_array($remoteOs, ['linux', 'windows'], TRUE)) {
      $this->configErrors[] = 'SSH remote_os must be "linux" or "windows". Got: ' . $remoteOs;
    }

    // =======================================================================
    // Ollama Endpoint Validation
    // =======================================================================

    $ollamaEndpoint = $config->get('ollama.endpoint');
    if (empty($ollamaEndpoint)) {
      $this->configErrors[] = 'Ollama endpoint is not configured.';
    }
    else {
      // Validate URL format.
      if (!preg_match('#^https?://#i', $ollamaEndpoint)) {
        $this->configErrors[] = 'Ollama endpoint must start with http:// or https://. Got: ' . $ollamaEndpoint;
      }
      elseif (!filter_var($ollamaEndpoint, FILTER_VALIDATE_URL)) {
        $this->configErrors[] = 'Ollama endpoint is not a valid URL: ' . $ollamaEndpoint;
      }
    }

    // =======================================================================
    // Weaviate Endpoint Validation
    // =======================================================================

    $weaviateUrl = $config->get('weaviate.url');
    if (empty($weaviateUrl)) {
      $this->configErrors[] = 'Weaviate URL is not configured.';
    }
    else {
      // Validate URL format.
      if (!preg_match('#^https?://#i', $weaviateUrl)) {
        $this->configErrors[] = 'Weaviate URL must start with http:// or https://. Got: ' . $weaviateUrl;
      }
      elseif (!filter_var($weaviateUrl, FILTER_VALIDATE_URL)) {
        $this->configErrors[] = 'Weaviate URL is not a valid URL: ' . $weaviateUrl;
      }
    }

    // Validate Weaviate gRPC port range.
    $weaviateGrpcPort = $config->get('weaviate.grpc_port');
    if ($weaviateGrpcPort && ($weaviateGrpcPort < 1 || $weaviateGrpcPort > 65535)) {
      $this->configErrors[] = 'Weaviate gRPC port must be between 1 and 65535.';
    }

    // =======================================================================
    // Finalize Validation
    // =======================================================================

    $this->configValid = empty($this->configErrors);

    if (!$this->configValid) {
      $this->logger->warning('Configuration invalid: @errors', [
        '@errors' => implode(' ', $this->configErrors),
      ]);
    }

    return $this->configValid;
  }

  /**
   * Get configuration validation errors.
   *
   * @return array
   *   Array of error messages.
   */
  public function getConfigErrors(): array {
    if ($this->configValid === NULL) {
      $this->validateConfig();
    }
    return $this->configErrors;
  }

  /**
   * Reset configuration validation state.
   *
   * Call this after configuration changes to force re-validation.
   */
  public function resetConfigValidation(): void {
    $this->configValid = NULL;
    $this->configErrors = [];
  }

  // ===========================================================================
  // Configuration Helper Methods (Step 7)
  // ===========================================================================

  /**
   * Get configuration.
   *
   * @return \Drupal\Core\Config\ImmutableConfig
   *   The configuration object.
   */
  protected function getConfig() {
    return $this->configFactory->get('congressional_query.settings');
  }

  /**
   * Get SSH host.
   *
   * @return string
   *   The SSH host.
   */
  public function getSSHHost(): string {
    return $this->getConfig()->get('ssh.host') ?: '';
  }

  /**
   * Get SSH port.
   *
   * @return int
   *   The SSH port.
   */
  public function getSSHPort(): int {
    return (int) ($this->getConfig()->get('ssh.port') ?: 22);
  }

  /**
   * Get SSH username.
   *
   * @return string
   *   The SSH username.
   */
  public function getSSHUsername(): string {
    return $this->getConfig()->get('ssh.username') ?: '';
  }

  /**
   * Check if private key authentication is configured.
   *
   * @return bool
   *   TRUE if private key path is set.
   */
  public function hasPrivateKey(): bool {
    $path = $this->getConfig()->get('ssh.private_key_path');
    return !empty($path) && file_exists($path);
  }

  /**
   * Get the Ollama endpoint URL.
   *
   * @return string
   *   The Ollama endpoint URL.
   */
  public function getOllamaEndpoint(): string {
    return $this->getConfig()->get('ollama.endpoint') ?: 'http://localhost:11434';
  }

  /**
   * Get the Weaviate URL.
   *
   * @return string
   *   The Weaviate URL.
   */
  public function getWeaviateUrl(): string {
    return $this->getConfig()->get('weaviate.url') ?: 'http://localhost:8080';
  }

  /**
   * Get the Weaviate gRPC port.
   *
   * @return int
   *   The gRPC port.
   */
  public function getWeaviateGrpcPort(): int {
    return (int) ($this->getConfig()->get('weaviate.grpc_port') ?: 50051);
  }

  /**
   * Get connection timeout.
   *
   * @return int
   *   Timeout in seconds.
   */
  public function getConnectionTimeout(): int {
    return (int) ($this->getConfig()->get('ssh.connection_timeout') ?: self::DEFAULT_CONNECTION_TIMEOUT);
  }

  /**
   * Get command timeout.
   *
   * @return int
   *   Timeout in seconds.
   */
  public function getCommandTimeout(): int {
    return (int) ($this->getConfig()->get('ssh.command_timeout') ?: self::DEFAULT_COMMAND_TIMEOUT);
  }

  /**
   * Get maximum retry attempts.
   *
   * @return int
   *   Max retries.
   */
  public function getMaxRetries(): int {
    return (int) ($this->getConfig()->get('ssh.max_retries') ?: self::DEFAULT_MAX_RETRIES);
  }

  /**
   * Get health check interval from configuration.
   *
   * @return int
   *   Health check interval in seconds.
   */
  public function getHealthCheckInterval(): int {
    return (int) ($this->getConfig()->get('ssh.health_check_interval') ?: self::HEALTH_CHECK_CACHE_DURATION);
  }

  /**
   * Get the remote OS type.
   *
   * @return string
   *   The remote OS: 'linux' or 'windows'.
   */
  public function getRemoteOS(): string {
    $os = $this->getConfig()->get('ssh.remote_os');
    if (!empty($os) && in_array($os, ['linux', 'windows'], TRUE)) {
      return $os;
    }
    // Default to linux for backwards compatibility.
    return 'linux';
  }

  /**
   * Check if remote OS is Windows.
   *
   * @return bool
   *   TRUE if remote is Windows.
   */
  public function isRemoteWindows(): bool {
    return $this->getRemoteOS() === 'windows';
  }

  // ===========================================================================
  // Connection Methods with Retry Logic (Step 2)
  // ===========================================================================

  /**
   * Establish SSH connection with automatic retry.
   *
   * @return \phpseclib3\Net\SSH2
   *   The SSH connection.
   *
   * @throws \Drupal\congressional_query\Exception\SSHConnectionException
   *   If connection fails after all retries.
   * @throws \Drupal\congressional_query\Exception\SSHAuthenticationException
   *   If authentication fails.
   */
  public function connect(): SSH2 {
    // Return existing connection if valid.
    if ($this->sshConnection !== NULL && $this->isConnected()) {
      $this->updateLastActivity();
      return $this->sshConnection;
    }

    // Validate configuration first.
    if (!$this->validateConfig()) {
      $errors = implode(' ', $this->configErrors);
      throw new SSHConnectionException(
        'SSH configuration invalid: ' . $errors,
        $this->getSSHHost(),
        $this->getSSHPort()
      );
    }

    $maxRetries = $this->getMaxRetries();
    $lastException = NULL;
    $errors = [];

    for ($attempt = 1; $attempt <= $maxRetries; $attempt++) {
      try {
        $ssh = $this->attemptConnection($attempt);
        $this->resetConnectionState();
        return $ssh;
      }
      catch (\Exception $e) {
        $lastException = $e;
        $errors[] = "Attempt $attempt: " . $e->getMessage();

        $this->logger->warning('SSH connection attempt @attempt/@max failed: @message', [
          '@attempt' => $attempt,
          '@max' => $maxRetries,
          '@message' => $e->getMessage(),
        ]);

        // Track connection attempts in state.
        $this->state->set('congressional_query.ssh_connection_attempts', $attempt);
        $this->state->set('congressional_query.ssh_last_failure', time());

        // Exponential backoff before next attempt.
        if ($attempt < $maxRetries) {
          $backoffSeconds = pow(2, $attempt);
          $this->logger->info('Waiting @seconds seconds before retry...', [
            '@seconds' => $backoffSeconds,
          ]);
          sleep($backoffSeconds);
        }
      }
    }

    // All attempts failed.
    $this->setLastError('connection', implode('; ', $errors), [
      'attempts' => $maxRetries,
      'host' => $this->getSSHHost(),
      'port' => $this->getSSHPort(),
    ]);

    throw new SSHConnectionException(
      'SSH connection failed after ' . $maxRetries . ' attempts: ' . implode('; ', $errors),
      $this->getSSHHost(),
      $this->getSSHPort(),
      $maxRetries,
      $lastException
    );
  }

  /**
   * Attempt a single SSH connection.
   *
   * @param int $attempt
   *   The attempt number (for logging).
   *
   * @return \phpseclib3\Net\SSH2
   *   The SSH connection.
   *
   * @throws \Drupal\congressional_query\Exception\SSHConnectionException
   *   If connection fails.
   * @throws \Drupal\congressional_query\Exception\SSHAuthenticationException
   *   If authentication fails.
   * @throws \Drupal\congressional_query\Exception\SSHTimeoutException
   *   If connection times out.
   */
  protected function attemptConnection(int $attempt): SSH2 {
    $host = $this->getSSHHost();
    $port = $this->getSSHPort();
    $username = $this->getSSHUsername();
    $timeout = $this->getConnectionTimeout();

    $this->logger->info('SSH connection attempt @attempt to @host:@port as @user', [
      '@attempt' => $attempt,
      '@host' => $host,
      '@port' => $port,
      '@user' => $username,
    ]);

    try {
      $ssh = new SSH2($host, $port);
      $ssh->setTimeout($timeout);
    }
    catch (\Exception $e) {
      if (strpos($e->getMessage(), 'timed out') !== FALSE) {
        throw new SSHTimeoutException(
          'SSH connection timed out after ' . $timeout . ' seconds',
          'connection',
          $timeout,
          $e
        );
      }
      throw new SSHConnectionException(
        'Failed to create SSH connection: ' . $e->getMessage(),
        $host,
        $port,
        $attempt,
        $e
      );
    }

    // Authenticate.
    $authenticated = FALSE;
    $authMethod = 'none';

    // Try private key first.
    $privateKeyPath = $this->getConfig()->get('ssh.private_key_path');
    if (!empty($privateKeyPath) && file_exists($privateKeyPath)) {
      try {
        $keyContent = file_get_contents($privateKeyPath);
        $key = PublicKeyLoader::load($keyContent);
        $authenticated = $ssh->login($username, $key);
        $authMethod = 'private_key';

        if ($authenticated) {
          $this->logger->debug('SSH authenticated with private key');
        }
      }
      catch (\Exception $e) {
        $this->logger->warning('Private key authentication failed: @message', [
          '@message' => $e->getMessage(),
        ]);
      }
    }

    // Try password if key failed or not configured.
    if (!$authenticated) {
      $password = $this->getConfig()->get('ssh.password');
      if (!empty($password)) {
        $authenticated = $ssh->login($username, $password);
        $authMethod = 'password';

        if ($authenticated) {
          $this->logger->debug('SSH authenticated with password');
        }
      }
    }

    if (!$authenticated) {
      throw new SSHAuthenticationException(
        'SSH authentication failed for user ' . $username . '. Check credentials.',
        $username,
        $authMethod
      );
    }

    // Store connection.
    $this->sshConnection = $ssh;
    $this->state->set('congressional_query.ssh_connected', TRUE);
    $this->state->set('congressional_query.ssh_connected_at', time());
    $this->state->set('congressional_query.ssh_auth_method', $authMethod);
    $this->updateLastActivity();

    $this->logger->info('SSH connection established to @host (auth: @method)', [
      '@host' => $host,
      '@method' => $authMethod,
    ]);

    return $ssh;
  }

  /**
   * Reset connection state after successful connection.
   */
  protected function resetConnectionState(): void {
    $this->state->set('congressional_query.ssh_connection_attempts', 0);
    $this->state->delete('congressional_query.ssh_last_failure');
    $this->lastError = NULL;
  }

  /**
   * Get current connection attempt count.
   *
   * @return int
   *   The attempt count.
   */
  public function getConnectionAttempts(): int {
    return (int) $this->state->get('congressional_query.ssh_connection_attempts', 0);
  }

  // ===========================================================================
  // Connection Persistence and Pooling (Step 4)
  // ===========================================================================

  /**
   * Check if SSH connection is active.
   *
   * Uses phpseclib's built-in connection state methods as the primary check,
   * avoiding expensive command execution for routine checks.
   *
   * @param bool $deep_check
   *   If TRUE, performs a command execution to verify connection is working.
   *   If FALSE (default), only uses lightweight phpseclib state methods.
   *
   * @return bool
   *   TRUE if connected.
   */
  public function isConnected(bool $deep_check = FALSE): bool {
    if ($this->sshConnection === NULL) {
      return FALSE;
    }

    // Primary check: use phpseclib's built-in connection state methods.
    // These are lightweight and don't require executing commands.
    try {
      if (!$this->sshConnection->isConnected()) {
        return FALSE;
      }
      if (!$this->sshConnection->isAuthenticated()) {
        return FALSE;
      }
    }
    catch (\Exception $e) {
      $this->logger->debug('SSH state check failed: @message', [
        '@message' => $e->getMessage(),
      ]);
      return FALSE;
    }

    // If deep check requested, verify with actual command execution.
    if ($deep_check) {
      try {
        $result = $this->sshConnection->exec('echo "ping"');
        if (trim($result) !== 'ping') {
          $this->logger->warning('SSH deep check returned unexpected output');
          return FALSE;
        }
      }
      catch (\Exception $e) {
        $this->logger->warning('SSH deep check failed: @message', [
          '@message' => $e->getMessage(),
        ]);
        return FALSE;
      }
    }

    return TRUE;
  }

  /**
   * Check if connection should be refreshed.
   *
   * Uses lightweight phpseclib state checks by default. Only performs
   * deep (command-based) checks when connection is stale.
   *
   * @return bool
   *   TRUE if reconnection is needed.
   */
  protected function shouldReconnect(): bool {
    if ($this->sshConnection === NULL) {
      return TRUE;
    }

    // First, use lightweight phpseclib state check.
    if (!$this->isConnected(FALSE)) {
      $this->logger->debug('SSH connection state check failed');
      return TRUE;
    }

    // Check if connection is stale (idle too long).
    $lastActivity = $this->state->get('congressional_query.ssh_last_activity', 0);
    if ((time() - $lastActivity) > self::CONNECTION_IDLE_TIMEOUT) {
      $this->logger->debug('SSH connection stale (idle > @seconds seconds)', [
        '@seconds' => self::CONNECTION_IDLE_TIMEOUT,
      ]);
      // For stale connections, perform a deep check before deciding to reconnect.
      if (!$this->isConnected(TRUE)) {
        return TRUE;
      }
    }

    return FALSE;
  }

  /**
   * Refresh connection if needed.
   *
   * @return bool
   *   TRUE if connection was refreshed, FALSE if no refresh needed.
   *
   * @throws \Drupal\congressional_query\Exception\SSHConnectionException
   *   If reconnection fails.
   */
  public function refreshConnection(): bool {
    if ($this->shouldReconnect()) {
      $this->logger->info('Refreshing SSH connection');
      $this->disconnect();
      $this->connect();
      return TRUE;
    }
    return FALSE;
  }

  /**
   * Update last activity timestamp.
   */
  protected function updateLastActivity(): void {
    $this->state->set('congressional_query.ssh_last_activity', time());
  }

  /**
   * Close SSH connection.
   */
  public function disconnect(): void {
    if ($this->sshConnection !== NULL) {
      try {
        $this->sshConnection->disconnect();
      }
      catch (\Exception $e) {
        // Ignore disconnect errors.
      }
      $this->sshConnection = NULL;
      $this->state->set('congressional_query.ssh_connected', FALSE);
      $this->logger->info('SSH connection closed');
    }
  }

  // ===========================================================================
  // Tunnel Lifecycle Management (Step 8)
  // ===========================================================================

  /**
   * Start SSH tunnel (connect with success boolean).
   *
   * @return bool
   *   TRUE if connection successful.
   */
  public function startTunnel(): bool {
    try {
      $this->connect();
      return TRUE;
    }
    catch (\Exception $e) {
      $this->logger->error('Failed to start SSH tunnel: @message', [
        '@message' => $e->getMessage(),
      ]);
      return FALSE;
    }
  }

  /**
   * Stop SSH tunnel.
   */
  public function stopTunnel(): void {
    $this->disconnect();
  }

  /**
   * Restart SSH tunnel.
   *
   * @return bool
   *   TRUE if restart successful.
   */
  public function restartTunnel(): bool {
    $this->disconnect();
    return $this->startTunnel();
  }

  /**
   * Check if tunnel is active and healthy.
   *
   * @return bool
   *   TRUE if tunnel is active.
   */
  public function isTunnelActive(): bool {
    if (!$this->isConnected()) {
      return FALSE;
    }

    // Optionally check service health too.
    $health = $this->checkTunnelHealth();
    return $health['status'] === 'ok';
  }

  /**
   * Warmup connection and verify all services.
   *
   * @return array
   *   Health status for all services.
   */
  public function warmupConnection(): array {
    $this->logger->info('Warming up SSH connection');

    try {
      $this->connect();
    }
    catch (\Exception $e) {
      return [
        'status' => 'error',
        'message' => 'Connection warmup failed: ' . $e->getMessage(),
        'services' => [],
      ];
    }

    // Run full health check.
    return $this->checkTunnelHealth();
  }

  // ===========================================================================
  // Command Execution (Step 5 - Enhanced Error Handling)
  // ===========================================================================

  /**
   * Execute command over SSH.
   *
   * @param string $command
   *   The command to execute.
   *
   * @return string
   *   The command output.
   *
   * @throws \Drupal\congressional_query\Exception\SSHCommandException
   *   If execution fails.
   * @throws \Drupal\congressional_query\Exception\SSHConnectionException
   *   If connection fails.
   */
  public function executeCommand(string $command): string {
    $this->refreshConnection();
    $ssh = $this->sshConnection;

    $this->logger->debug('Executing SSH command: @cmd', [
      '@cmd' => $this->sanitizeForLog($command),
    ]);

    try {
      $output = $ssh->exec($command);
      $exitCode = $ssh->getExitStatus();

      $this->updateLastActivity();
      $this->incrementCommandCount();

      if ($exitCode !== 0) {
        $this->logger->warning('SSH command returned non-zero exit code: @code', [
          '@code' => $exitCode,
        ]);

        throw new SSHCommandException(
          'SSH command failed with exit code ' . $exitCode,
          $this->sanitizeForLog($command),
          $exitCode,
          $output
        );
      }

      return $output;
    }
    catch (SSHCommandException $e) {
      throw $e;
    }
    catch (\Exception $e) {
      $this->setLastError('command', $e->getMessage(), [
        'command' => $this->sanitizeForLog($command),
      ]);

      throw new SSHCommandException(
        'SSH command execution failed: ' . $e->getMessage(),
        $this->sanitizeForLog($command),
        NULL,
        '',
        $e
      );
    }
  }

  /**
   * Build a curl command appropriate for the remote OS.
   *
   * Handles differences between Linux (POSIX shell) and Windows (PowerShell/cmd)
   * for temp file paths, quoting, and cleanup commands.
   *
   * @param string $method
   *   HTTP method.
   * @param string $url
   *   The URL to request.
   * @param array $headers
   *   Request headers.
   * @param string|null $body
   *   Request body.
   * @param int $timeout
   *   Timeout in seconds.
   *
   * @return array
   *   Array with 'command' (the curl command) and 'temp_file' (path or NULL).
   */
  protected function buildCurlCommand(
    string $method,
    string $url,
    array $headers = [],
    ?string $body = NULL,
    int $timeout = 30
  ): array {
    $isWindows = $this->isRemoteWindows();
    $tempFile = NULL;

    if ($isWindows) {
      // Windows: Use PowerShell-compatible syntax.
      // Curl is available on Windows 10+ and Windows Server 2019+.
      $curlCmd = 'curl.exe -s -w "`n%{http_code}" -X ' . $method;
      $curlCmd .= ' --max-time ' . (int) $timeout;

      foreach ($headers as $key => $value) {
        // Windows: Use double quotes, escape inner double quotes.
        $headerValue = str_replace('"', '\"', "$key: $value");
        $curlCmd .= ' -H "' . $headerValue . '"';
      }

      if ($body !== NULL) {
        // Windows: Use %TEMP% directory.
        $tempFile = '%TEMP%\\drupal_curl_body_' . uniqid() . '.txt';
        // Escape body for Windows. Replace double quotes.
        $escapedBody = str_replace('"', '\"', $body);
        $escapedBody = str_replace("\n", "`n", $escapedBody);
        $curlCmd .= ' -d "@' . $tempFile . '"';
      }

      // Windows: Escape URL if it contains special characters.
      $curlCmd .= ' "' . str_replace('"', '\"', $url) . '"';
    }
    else {
      // Linux/POSIX: Use standard shell syntax.
      $curlCmd = 'curl -s -w "\n%{http_code}" -X ' . escapeshellarg($method);
      $curlCmd .= ' --max-time ' . (int) $timeout;

      foreach ($headers as $key => $value) {
        $curlCmd .= ' -H ' . escapeshellarg("$key: $value");
      }

      if ($body !== NULL) {
        // Linux: Use /tmp directory.
        $tempFile = '/tmp/drupal_curl_body_' . uniqid();
        $curlCmd .= ' -d @' . $tempFile;
      }

      $curlCmd .= ' ' . escapeshellarg($url);
    }

    return [
      'command' => $curlCmd,
      'temp_file' => $tempFile,
      'body' => $body,
    ];
  }

  /**
   * Write body to temp file on remote system.
   *
   * @param string $tempFile
   *   Path to temp file.
   * @param string $body
   *   Content to write.
   */
  protected function writeRemoteTempFile(string $tempFile, string $body): void {
    $ssh = $this->sshConnection;
    $isWindows = $this->isRemoteWindows();

    if ($isWindows) {
      // Windows: Use PowerShell to write file.
      // Escape for PowerShell single-quoted string.
      $escapedBody = str_replace("'", "''", $body);
      $cmd = "powershell -Command \"Set-Content -Path '" . $tempFile . "' -Value '" . $escapedBody . "'\"";
      $ssh->exec($cmd);
    }
    else {
      // Linux: Use echo with proper escaping.
      $escapedBody = str_replace("'", "'\"'\"'", $body);
      $ssh->exec("echo '$escapedBody' > $tempFile");
    }
  }

  /**
   * Delete temp file on remote system.
   *
   * @param string $tempFile
   *   Path to temp file.
   */
  protected function deleteRemoteTempFile(string $tempFile): void {
    $ssh = $this->sshConnection;
    $isWindows = $this->isRemoteWindows();

    if ($isWindows) {
      // Windows: Use del command.
      $ssh->exec('del /q "' . $tempFile . '" 2>nul');
    }
    else {
      // Linux: Use rm command.
      $ssh->exec('rm -f ' . escapeshellarg($tempFile));
    }
  }

  /**
   * Make streaming HTTP request through SSH tunnel using curl.
   *
   * This method executes curl commands on the remote SSH target and invokes
   * the callback as data arrives, enabling true incremental streaming.
   *
   * @param string $method
   *   HTTP method.
   * @param string $url
   *   The URL to request.
   * @param array $headers
   *   Request headers.
   * @param string|null $body
   *   Request body.
   * @param callable $callback
   *   Callback invoked for each chunk of data: function(string $chunk).
   * @param int $timeout
   *   Timeout in seconds.
   *
   * @return int
   *   HTTP status code (extracted from the last line of output).
   *
   * @throws \Drupal\congressional_query\Exception\SSHCommandException
   *   If request fails.
   * @throws \Drupal\congressional_query\Exception\SSHConnectionException
   *   If connection fails.
   */
  public function makeHttpRequestStreaming(
    string $method,
    string $url,
    array $headers = [],
    ?string $body = NULL,
    callable $callback,
    int $timeout = 0
  ): int {
    $this->refreshConnection();
    $ssh = $this->sshConnection;

    $timeout = $timeout ?: $this->getCommandTimeout();

    // Build OS-appropriate curl command for streaming.
    // For streaming, we use -N (--no-buffer) to disable output buffering.
    $curlData = $this->buildStreamingCurlCommand($method, $url, $headers, $body, $timeout);
    $curlCmd = $curlData['command'];
    $tempFile = $curlData['temp_file'];

    // Write body to temp file if needed.
    if ($tempFile !== NULL && $body !== NULL) {
      $this->writeRemoteTempFile($tempFile, $body);
    }

    $this->logger->debug('Executing streaming remote curl (@os): @cmd', [
      '@os' => $this->getRemoteOS(),
      '@cmd' => substr($curlCmd, 0, 500),
    ]);

    // Buffer for accumulating partial lines.
    $buffer = '';
    $statusCode = 0;

    try {
      // Use phpseclib3's callback mode for exec() which invokes the callback
      // as data arrives from the remote command, enabling true streaming.
      $ssh->exec($curlCmd, function ($data) use ($callback, &$buffer, &$statusCode) {
        $buffer .= $data;

        // Process complete lines from the buffer.
        while (($pos = strpos($buffer, "\n")) !== FALSE) {
          $line = substr($buffer, 0, $pos);
          $buffer = substr($buffer, $pos + 1);

          // The last line will be the HTTP status code.
          // We detect it by checking if it's a 3-digit number only.
          if (preg_match('/^\d{3}$/', trim($line))) {
            $statusCode = (int) trim($line);
          }
          else {
            // Pass the data chunk to the callback.
            $callback($line);
          }
        }
      });

      // Process any remaining data in buffer.
      if (!empty($buffer)) {
        $trimmed = trim($buffer);
        if (preg_match('/^\d{3}$/', $trimmed)) {
          $statusCode = (int) $trimmed;
        }
        else {
          $callback($buffer);
        }
      }

      $this->updateLastActivity();
      $this->incrementCommandCount();

      // Clean up temp file.
      if ($tempFile !== NULL) {
        $this->deleteRemoteTempFile($tempFile);
      }

      return $statusCode;
    }
    catch (\Exception $e) {
      // Clean up temp file on error.
      if ($tempFile !== NULL) {
        try {
          $this->deleteRemoteTempFile($tempFile);
        }
        catch (\Exception $cleanupException) {
          // Ignore cleanup errors.
        }
      }

      $this->setLastError('http_request_streaming', $e->getMessage(), [
        'url' => $url,
        'method' => $method,
      ]);

      throw new SSHCommandException(
        'Streaming HTTP request via SSH failed: ' . $e->getMessage(),
        'curl ' . $url,
        NULL,
        '',
        $e
      );
    }
  }

  /**
   * Build a streaming curl command appropriate for the remote OS.
   *
   * Similar to buildCurlCommand but includes -N flag to disable buffering.
   *
   * @param string $method
   *   HTTP method.
   * @param string $url
   *   The URL to request.
   * @param array $headers
   *   Request headers.
   * @param string|null $body
   *   Request body.
   * @param int $timeout
   *   Timeout in seconds.
   *
   * @return array
   *   Array with 'command' (the curl command) and 'temp_file' (path or NULL).
   */
  protected function buildStreamingCurlCommand(
    string $method,
    string $url,
    array $headers = [],
    ?string $body = NULL,
    int $timeout = 30
  ): array {
    $isWindows = $this->isRemoteWindows();
    $tempFile = NULL;

    if ($isWindows) {
      // Windows: Use PowerShell-compatible syntax with no-buffer.
      $curlCmd = 'curl.exe -s -N -w "`n%{http_code}" -X ' . $method;
      $curlCmd .= ' --max-time ' . (int) $timeout;

      foreach ($headers as $key => $value) {
        $headerValue = str_replace('"', '\"', "$key: $value");
        $curlCmd .= ' -H "' . $headerValue . '"';
      }

      if ($body !== NULL) {
        $tempFile = '%TEMP%\\drupal_curl_stream_' . uniqid() . '.txt';
        $curlCmd .= ' -d "@' . $tempFile . '"';
      }

      $curlCmd .= ' "' . str_replace('"', '\"', $url) . '"';
    }
    else {
      // Linux/POSIX: Use standard shell syntax with no-buffer.
      $curlCmd = 'curl -s -N -w "\n%{http_code}" -X ' . escapeshellarg($method);
      $curlCmd .= ' --max-time ' . (int) $timeout;

      foreach ($headers as $key => $value) {
        $curlCmd .= ' -H ' . escapeshellarg("$key: $value");
      }

      if ($body !== NULL) {
        $tempFile = '/tmp/drupal_curl_stream_' . uniqid();
        $curlCmd .= ' -d @' . $tempFile;
      }

      $curlCmd .= ' ' . escapeshellarg($url);
    }

    return [
      'command' => $curlCmd,
      'temp_file' => $tempFile,
      'body' => $body,
    ];
  }

  /**
   * Make HTTP request through SSH tunnel using curl.
   *
   * This method executes curl commands on the remote SSH target to access
   * localhost services. The command syntax is adjusted based on the remote
   * OS setting (ssh.remote_os).
   *
   * @param string $method
   *   HTTP method.
   * @param string $url
   *   The URL to request.
   * @param array $headers
   *   Request headers.
   * @param string|null $body
   *   Request body.
   * @param int $timeout
   *   Timeout in seconds.
   *
   * @return array
   *   Array with 'status', 'headers', 'body' keys.
   *
   * @throws \Drupal\congressional_query\Exception\SSHCommandException
   *   If request fails.
   * @throws \Drupal\congressional_query\Exception\SSHConnectionException
   *   If connection fails.
   */
  public function makeHttpRequest(
    string $method,
    string $url,
    array $headers = [],
    ?string $body = NULL,
    int $timeout = 0
  ): array {
    $this->refreshConnection();
    $ssh = $this->sshConnection;

    $timeout = $timeout ?: $this->getCommandTimeout();

    // Build OS-appropriate curl command.
    $curlData = $this->buildCurlCommand($method, $url, $headers, $body, $timeout);
    $curlCmd = $curlData['command'];
    $tempFile = $curlData['temp_file'];

    // Write body to temp file if needed.
    if ($tempFile !== NULL && $body !== NULL) {
      $this->writeRemoteTempFile($tempFile, $body);
    }

    $this->logger->debug('Executing remote curl (@os): @cmd', [
      '@os' => $this->getRemoteOS(),
      '@cmd' => substr($curlCmd, 0, 500),
    ]);

    try {
      $output = $ssh->exec($curlCmd);
      $this->updateLastActivity();
      $this->incrementCommandCount();

      // Clean up temp file.
      if ($tempFile !== NULL) {
        $this->deleteRemoteTempFile($tempFile);
      }

      if ($output === FALSE || $output === '') {
        throw new SSHCommandException(
          'SSH curl command returned empty response',
          'curl ' . $url
        );
      }

      // Parse response - last line is status code.
      $lines = explode("\n", trim($output));
      $statusCode = (int) array_pop($lines);
      $responseBody = implode("\n", $lines);

      return [
        'status' => $statusCode,
        'headers' => [],
        'body' => $responseBody,
      ];
    }
    catch (SSHCommandException $e) {
      // Clean up temp file on error.
      if ($tempFile !== NULL) {
        try {
          $this->deleteRemoteTempFile($tempFile);
        }
        catch (\Exception $cleanupException) {
          // Ignore cleanup errors.
        }
      }
      throw $e;
    }
    catch (\Exception $e) {
      // Clean up temp file on error.
      if ($tempFile !== NULL) {
        try {
          $this->deleteRemoteTempFile($tempFile);
        }
        catch (\Exception $cleanupException) {
          // Ignore cleanup errors.
        }
      }

      $this->setLastError('http_request', $e->getMessage(), [
        'url' => $url,
        'method' => $method,
      ]);

      throw new SSHCommandException(
        'HTTP request via SSH failed: ' . $e->getMessage(),
        'curl ' . $url,
        NULL,
        '',
        $e
      );
    }
  }

  // ===========================================================================
  // Health Monitoring (Step 3)
  // ===========================================================================

  /**
   * Check tunnel health including all services.
   *
   * @return array
   *   Health status array.
   */
  public function checkTunnelHealth(): array {
    $startTime = microtime(TRUE);
    $services = [];

    // Check SSH connection.
    $sshHealth = $this->checkServiceHealth('ssh');
    $services['ssh'] = $sshHealth;

    // Only check other services if SSH is healthy.
    if ($sshHealth['status'] === 'ok') {
      $services['ollama'] = $this->checkServiceHealth('ollama');
      $services['weaviate'] = $this->checkServiceHealth('weaviate');
    }
    else {
      $services['ollama'] = [
        'status' => 'unknown',
        'message' => 'Cannot check - SSH not connected',
        'response_time_ms' => 0,
      ];
      $services['weaviate'] = [
        'status' => 'unknown',
        'message' => 'Cannot check - SSH not connected',
        'response_time_ms' => 0,
      ];
    }

    // Determine overall status.
    $overallStatus = 'ok';
    $hasError = FALSE;
    $hasWarning = FALSE;

    foreach ($services as $service) {
      if ($service['status'] === 'error') {
        $hasError = TRUE;
      }
      elseif ($service['status'] === 'warning' || $service['status'] === 'unknown') {
        $hasWarning = TRUE;
      }
    }

    if ($hasError) {
      $overallStatus = 'error';
    }
    elseif ($hasWarning) {
      $overallStatus = 'warning';
    }

    $totalTime = (int) ((microtime(TRUE) - $startTime) * 1000);

    $result = [
      'status' => $overallStatus,
      'message' => $this->getHealthMessage($overallStatus),
      'services' => $services,
      'total_response_time_ms' => $totalTime,
      'timestamp' => time(),
      'details' => [
        'host' => $this->getSSHHost(),
        'connected' => $this->isConnected(),
        'auth_method' => $this->state->get('congressional_query.ssh_auth_method'),
      ],
    ];

    // Cache health check result.
    $this->state->set('congressional_query.last_health_check', time());
    $this->state->set('congressional_query.last_health_result', $result);

    return $result;
  }

  /**
   * Check health of a specific service.
   *
   * @param string $service
   *   Service name: 'ssh', 'ollama', or 'weaviate'.
   *
   * @return array
   *   Health status for the service.
   */
  public function checkServiceHealth(string $service): array {
    $startTime = microtime(TRUE);

    try {
      switch ($service) {
        case 'ssh':
          return $this->checkSSHHealth($startTime);

        case 'ollama':
          return $this->checkOllamaHealth($startTime);

        case 'weaviate':
          return $this->checkWeaviateHealth($startTime);

        default:
          return [
            'status' => 'error',
            'message' => 'Unknown service: ' . $service,
            'response_time_ms' => 0,
          ];
      }
    }
    catch (\Exception $e) {
      return [
        'status' => 'error',
        'message' => $e->getMessage(),
        'response_time_ms' => (int) ((microtime(TRUE) - $startTime) * 1000),
      ];
    }
  }

  /**
   * Check SSH connection health.
   *
   * Uses phpseclib's built-in state methods for initial checks, then performs
   * a single command execution for deep verification. This avoids redundant
   * echo calls from isConnected() by directly executing our health check command.
   */
  protected function checkSSHHealth(float $startTime): array {
    try {
      // First, check if we have a connection object.
      if ($this->sshConnection === NULL) {
        $this->connect();
      }

      // Use phpseclib's built-in state checks (lightweight, no command exec).
      if (!$this->sshConnection->isConnected() || !$this->sshConnection->isAuthenticated()) {
        // Connection lost, try to reconnect.
        $this->disconnect();
        $this->connect();
      }

      // Now perform single command execution for deep health check.
      // This is the only echo command in the health check flow.
      $result = $this->sshConnection->exec('echo "health_check_ok"');
      $responseTime = (int) ((microtime(TRUE) - $startTime) * 1000);

      if (trim($result) === 'health_check_ok') {
        return [
          'status' => 'ok',
          'message' => 'SSH connection healthy',
          'response_time_ms' => $responseTime,
          'details' => [
            'host' => $this->getSSHHost(),
            'port' => $this->getSSHPort(),
            'remote_os' => $this->getRemoteOS(),
          ],
        ];
      }

      return [
        'status' => 'warning',
        'message' => 'SSH responded but with unexpected output',
        'response_time_ms' => $responseTime,
        'details' => ['response' => substr($result, 0, 100)],
      ];
    }
    catch (\Exception $e) {
      $this->state->set('congressional_query.ssh_connected', FALSE);
      return [
        'status' => 'error',
        'message' => $e->getMessage(),
        'response_time_ms' => (int) ((microtime(TRUE) - $startTime) * 1000),
      ];
    }
  }

  /**
   * Check Ollama service health.
   */
  protected function checkOllamaHealth(float $startTime): array {
    $ollamaUrl = rtrim($this->getOllamaEndpoint(), '/') . '/api/tags';

    try {
      $response = $this->makeHttpRequest('GET', $ollamaUrl, [], NULL, 10);
      $responseTime = (int) ((microtime(TRUE) - $startTime) * 1000);

      if ($response['status'] === 200) {
        $data = json_decode($response['body'], TRUE);
        $models = [];
        if (isset($data['models'])) {
          foreach ($data['models'] as $model) {
            $models[] = $model['name'] ?? 'unknown';
          }
        }

        return [
          'status' => 'ok',
          'message' => 'Ollama connected',
          'response_time_ms' => $responseTime,
          'details' => [
            'model_count' => count($models),
            'models' => array_slice($models, 0, 5),
          ],
        ];
      }

      return [
        'status' => 'error',
        'message' => 'Ollama returned HTTP ' . $response['status'],
        'response_time_ms' => $responseTime,
      ];
    }
    catch (\Exception $e) {
      return [
        'status' => 'error',
        'message' => 'Ollama unreachable: ' . $e->getMessage(),
        'response_time_ms' => (int) ((microtime(TRUE) - $startTime) * 1000),
      ];
    }
  }

  /**
   * Check Weaviate service health.
   */
  protected function checkWeaviateHealth(float $startTime): array {
    $weaviateUrl = rtrim($this->getWeaviateUrl(), '/') . '/v1/meta';

    try {
      $response = $this->makeHttpRequest('GET', $weaviateUrl, [], NULL, 10);
      $responseTime = (int) ((microtime(TRUE) - $startTime) * 1000);

      if ($response['status'] === 200) {
        $data = json_decode($response['body'], TRUE);

        return [
          'status' => 'ok',
          'message' => 'Weaviate connected',
          'response_time_ms' => $responseTime,
          'details' => [
            'version' => $data['version'] ?? 'unknown',
            'hostname' => $data['hostname'] ?? 'unknown',
          ],
        ];
      }

      return [
        'status' => 'error',
        'message' => 'Weaviate returned HTTP ' . $response['status'],
        'response_time_ms' => $responseTime,
      ];
    }
    catch (\Exception $e) {
      return [
        'status' => 'error',
        'message' => 'Weaviate unreachable: ' . $e->getMessage(),
        'response_time_ms' => (int) ((microtime(TRUE) - $startTime) * 1000),
      ];
    }
  }

  /**
   * Get cached health check result.
   *
   * Uses the configurable health_check_interval setting to determine
   * cache validity, ensuring the cached result freshness aligns with
   * the admin-configured interval.
   *
   * @return array|null
   *   Cached health result or NULL if expired.
   */
  public function getLastHealthCheck(): ?array {
    $result = $this->state->get('congressional_query.last_health_result');
    $timestamp = $this->state->get('congressional_query.last_health_check', 0);

    // Check if cache is still valid using configurable interval.
    $cacheInterval = $this->getHealthCheckInterval();
    if ($result && (time() - $timestamp) < $cacheInterval) {
      return $result;
    }

    return NULL;
  }

  /**
   * Quick health status check.
   *
   * @return bool
   *   TRUE if healthy.
   */
  public function isHealthy(): bool {
    $cached = $this->getLastHealthCheck();
    if ($cached) {
      return $cached['status'] === 'ok';
    }

    $health = $this->checkTunnelHealth();
    return $health['status'] === 'ok';
  }

  /**
   * Get human-readable health message.
   */
  protected function getHealthMessage(string $status): string {
    switch ($status) {
      case 'ok':
        return 'All services healthy';
      case 'warning':
        return 'Some services degraded';
      case 'error':
        return 'Service connectivity issues';
      default:
        return 'Unknown status';
    }
  }

  // ===========================================================================
  // Status and Error Tracking (Step 6)
  // ===========================================================================

  /**
   * Get connection status for display.
   *
   * @return array
   *   Comprehensive status array.
   */
  public function getStatus(): array {
    $connectedAt = $this->state->get('congressional_query.ssh_connected_at');

    return [
      'connected' => $this->state->get('congressional_query.ssh_connected', FALSE),
      'host' => $this->getSSHHost(),
      'port' => $this->getSSHPort(),
      'username' => $this->getSSHUsername(),
      'auth_method' => $this->state->get('congressional_query.ssh_auth_method'),
      'connected_at' => $connectedAt,
      'uptime_seconds' => $connectedAt ? (time() - $connectedAt) : 0,
      'last_activity' => $this->state->get('congressional_query.ssh_last_activity'),
      'last_health_check' => $this->state->get('congressional_query.last_health_check'),
      'connection_attempts' => $this->getConnectionAttempts(),
      'last_failure' => $this->state->get('congressional_query.ssh_last_failure'),
      'commands_executed' => $this->state->get('congressional_query.ssh_command_count', 0),
      'last_error' => $this->lastError,
      'config_valid' => $this->validateConfig(),
      'config_errors' => $this->configErrors,
    ];
  }

  /**
   * Get status formatted for block display.
   *
   * @return array
   *   Formatted status for UI display.
   */
  public function getStatusForBlock(): array {
    $status = $this->getStatus();
    $health = $this->getLastHealthCheck() ?? $this->checkTunnelHealth();

    // Format timestamps.
    $connectedAt = $status['connected_at'];
    $lastActivity = $status['last_activity'];
    $lastHealthCheck = $status['last_health_check'];

    return [
      'connection' => [
        'status' => $status['connected'] ? 'connected' : 'disconnected',
        'status_class' => $status['connected'] ? 'status-ok' : 'status-error',
        'host' => $status['host'] ?: 'Not configured',
        'auth_method' => $status['auth_method'] ?: 'None',
        'uptime' => $status['uptime_seconds'] > 0 ? $this->formatDuration($status['uptime_seconds']) : 'N/A',
        'connected_at' => $connectedAt ? date('Y-m-d H:i:s', $connectedAt) : 'Never',
        'last_activity' => $lastActivity ? date('H:i:s', $lastActivity) : 'N/A',
      ],
      'services' => $health['services'] ?? [],
      'overall_status' => $health['status'] ?? 'unknown',
      'overall_message' => $health['message'] ?? 'Status unknown',
      'last_check' => $lastHealthCheck ? date('H:i:s', $lastHealthCheck) : 'Never',
      'stats' => [
        'commands_executed' => $status['commands_executed'],
        'connection_attempts' => $status['connection_attempts'],
      ],
    ];
  }

  /**
   * Get connection uptime in seconds.
   *
   * @return int
   *   Uptime in seconds.
   */
  public function getConnectionUptime(): int {
    $connectedAt = $this->state->get('congressional_query.ssh_connected_at', 0);
    if (!$connectedAt || !$this->state->get('congressional_query.ssh_connected', FALSE)) {
      return 0;
    }
    return time() - $connectedAt;
  }

  /**
   * Get connection statistics.
   *
   * @return array
   *   Statistics array.
   */
  public function getConnectionStats(): array {
    return [
      'total_commands' => $this->state->get('congressional_query.ssh_command_count', 0),
      'connection_attempts' => $this->getConnectionAttempts(),
      'uptime_seconds' => $this->getConnectionUptime(),
      'last_failure' => $this->state->get('congressional_query.ssh_last_failure'),
      'failures_today' => $this->state->get('congressional_query.ssh_failures_today', 0),
    ];
  }

  /**
   * Increment command execution count.
   */
  protected function incrementCommandCount(): void {
    $count = $this->state->get('congressional_query.ssh_command_count', 0);
    $this->state->set('congressional_query.ssh_command_count', $count + 1);
  }

  /**
   * Set last error details.
   *
   * @param string $type
   *   Error type.
   * @param string $message
   *   Error message.
   * @param array $context
   *   Additional context.
   */
  protected function setLastError(string $type, string $message, array $context = []): void {
    $this->lastError = [
      'type' => $type,
      'message' => $message,
      'context' => $context,
      'timestamp' => time(),
    ];
    $this->state->set('congressional_query.ssh_last_error', $this->lastError);
  }

  /**
   * Get last error details.
   *
   * @return array|null
   *   Error details or NULL.
   */
  public function getLastError(): ?array {
    return $this->lastError ?? $this->state->get('congressional_query.ssh_last_error');
  }

  /**
   * Sanitize text for logging (mask passwords).
   *
   * @param string $text
   *   Text to sanitize.
   *
   * @return string
   *   Sanitized text.
   */
  protected function sanitizeForLog(string $text): string {
    // Mask anything that looks like a password.
    $sanitized = preg_replace('/password["\']?\s*[:=]\s*["\']?[^"\'\s]+["\']?/i', 'password=***', $text);
    $sanitized = preg_replace('/-p\s*["\']?[^"\'\s]+/', '-p ***', $sanitized);
    return $sanitized;
  }

  /**
   * Format duration in human-readable form.
   *
   * @param int $seconds
   *   Duration in seconds.
   *
   * @return string
   *   Formatted duration.
   */
  protected function formatDuration(int $seconds): string {
    if ($seconds < 60) {
      return $seconds . 's';
    }
    if ($seconds < 3600) {
      return floor($seconds / 60) . 'm ' . ($seconds % 60) . 's';
    }
    $hours = floor($seconds / 3600);
    $minutes = floor(($seconds % 3600) / 60);
    return $hours . 'h ' . $minutes . 'm';
  }

  /**
   * Destructor - don't disconnect to allow connection reuse.
   */
  public function __destruct() {
    // Intentionally not disconnecting to allow connection pooling.
    // Connection will be cleaned up when PHP process ends.
  }

}
