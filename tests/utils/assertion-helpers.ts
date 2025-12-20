import { expect, Page } from "@playwright/test";
import { UnifiedResponse, JobInfo } from "../api-clients/GatewayAPIClient";

export function assertAPIResponse<T = any>(
  response: UnifiedResponse<T>,
  expectedStatus: "success" | "error",
): void {
  const isSuccess = expectedStatus === "success";
  expect(response.success).toBe(isSuccess);
  if (isSuccess) {
    expect(response.data).toBeTruthy();
  } else {
    expect(response.error).toBeTruthy();
  }
}

export function assertJobStatus(
  job: JobInfo,
  expectedStatus: JobInfo["status"],
): void {
  expect(job.status).toBe(expectedStatus);
}

export async function assertElementVisible(
  page: Page,
  selector: string,
  message?: string,
): Promise<void> {
  try {
    await expect(page.locator(selector)).toBeVisible();
  } catch (error) {
    if (message) {
      throw new Error(message);
    }
    throw error;
  }
}

export function assertVRAMUsage(
  vramData: { gpu: { used_mb: number } },
  expectedRange: { min: number; max: number },
): void {
  const used = vramData.gpu.used_mb;
  expect(used).toBeGreaterThanOrEqual(expectedRange.min);
  expect(used).toBeLessThanOrEqual(expectedRange.max);
}
