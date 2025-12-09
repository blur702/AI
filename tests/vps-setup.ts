/**
 * Playwright Global Setup for VPS Environment
 *
 * This file is referenced by playwright.config.ts when running in VPS mode.
 * It handles:
 * - Service orchestration (starting required services)
 * - VRAM management (preserving embedding models)
 * - Environment validation
 */

import { FullConfig } from '@playwright/test';
import { DashboardAPIClient } from './api-clients/DashboardAPIClient';
import { ServiceOrchestrator } from './utils/service-orchestrator';
import {
  getVPSConfig,
  logVPSEnvironment,
  isVPSEnvironment,
  ServiceIds
} from './utils/vps-helpers';

async function globalSetup(config: FullConfig): Promise<void> {
  if (!isVPSEnvironment()) {
    console.log('[VPS Setup] Not in VPS environment, skipping setup');
    return;
  }

  console.log('\n========================================');
  console.log('       VPS Global Setup Starting        ');
  console.log('========================================\n');

  logVPSEnvironment();

  const vpsConfig = getVPSConfig();
  const dashboardClient = new DashboardAPIClient(vpsConfig.dashboardApiUrl, {
    allowInsecureConnections: vpsConfig.allowInsecureConnections
  });
  const orchestrator = new ServiceOrchestrator(dashboardClient, {
    startTimeout: vpsConfig.serviceStartTimeout,
    healthInterval: vpsConfig.serviceHealthInterval,
    maxRetries: vpsConfig.maxServiceRetries,
    preserveEmbeddingModels: vpsConfig.preserveEmbeddingModels,
    gpuIntensiveServices: vpsConfig.gpuIntensiveServices
  });

  try {
    // 1. Verify dashboard connectivity
    console.log('[VPS Setup] Verifying dashboard connectivity...');
    const servicesResponse = await dashboardClient.getServices();

    // Validate response structure
    if (!servicesResponse || typeof servicesResponse !== 'object') {
      console.error('[VPS Setup] Dashboard returned invalid response (not an object)');
      throw new Error('Dashboard API returned invalid response structure');
    }

    const services = servicesResponse.services;
    if (!services || typeof services !== 'object') {
      console.error('[VPS Setup] Dashboard response missing "services" field or invalid type');
      throw new Error('Dashboard API response missing "services" field');
    }

    const serviceCount = Object.keys(services).length;
    console.log(`[VPS Setup] Dashboard connected - ${serviceCount} services registered`);

    // 2. Manage VRAM - preserve embedding models
    console.log('[VPS Setup] Managing VRAM (preserving embedding models)...');
    await orchestrator.manageVRAM(true);

    // 3. Ensure core services are running
    const coreServices = [ServiceIds.DASHBOARD, ServiceIds.GATEWAY, ServiceIds.OLLAMA];
    console.log(`[VPS Setup] Ensuring core services: ${coreServices.join(', ')}`);

    for (const serviceId of coreServices) {
      try {
        await orchestrator.ensureServiceRunning(serviceId);
      } catch (error: any) {
        console.warn(`[VPS Setup] Could not start ${serviceId}: ${error.message}`);
        // Continue - some services might not be defined
      }
    }

    // 4. Log VRAM status
    try {
      const vramStatus = await dashboardClient.getVRAMStatus();
      if (vramStatus?.gpu) {
        const usedMb = vramStatus.gpu.used_mb ?? 'unknown';
        const totalMb = vramStatus.gpu.total_mb ?? 'unknown';
        console.log(`[VPS Setup] VRAM: ${usedMb}MB / ${totalMb}MB used`);
      } else {
        console.warn('[VPS Setup] VRAM status returned unexpected structure, skipping VRAM log');
      }
    } catch (vramError: any) {
      console.warn(`[VPS Setup] Could not fetch VRAM status: ${vramError.message}`);
    }

    console.log('\n[VPS Setup] Global setup complete');
    console.log('========================================\n');
  } catch (error: any) {
    console.error(`\n[VPS Setup] Setup failed: ${error.message}`);
    console.error('[VPS Setup] Tests may fail due to service unavailability');
    console.error('========================================\n');
    // Don't throw - let tests handle service availability
  }
}

export default globalSetup;
