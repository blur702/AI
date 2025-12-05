import axios from 'axios';
import { Page } from '@playwright/test';
import { BaseAPIClient } from '../api-clients/BaseAPIClient';

export async function waitForServiceReady(url: string, timeoutMs = 30_000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await axios.get(url, { timeout: 5000 });
      if (response.status < 500) {
        return;
      }
    } catch {
      // ignore and retry
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`Service at ${url} did not become ready within ${timeoutMs}ms`);
}

export async function waitForElementWithRetry(
  page: Page,
  selector: string,
  timeoutMs = 10_000
): Promise<void> {
  await page.waitForSelector(selector, { timeout: timeoutMs });
}

export async function waitForTextContent(
  page: Page,
  selector: string,
  text: string | RegExp,
  timeoutMs = 10_000
): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const content = await page.textContent(selector);
    if (content && (typeof text === 'string' ? content.includes(text) : text.test(content))) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Text "${text}" not found in selector ${selector} within timeout`);
}

/**
 * Poll an API until a specific error status is observed.
 *
 * This helper is intended for scenarios where an API initially succeeds
 * or returns a different error, and tests need to wait until a particular
 * error status code is produced (for example, when a resource eventually
 * becomes unavailable). Successful responses return immediately regardless
 * of status code; only error responses are matched against
 * `expectedErrorStatus`.
 */
export async function waitForAPIResponse(
  apiClient: BaseAPIClient,
  endpoint: string,
  expectedErrorStatus: number,
  timeoutMs = 30_000
): Promise<any> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await apiClient.get<any>(endpoint);
      // If the call succeeds, return the response immediately.
      return response;
    } catch (error: any) {
      if (error.status && error.status === expectedErrorStatus) {
        return error.data;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`API ${endpoint} did not return expected error status within timeout`);
}
