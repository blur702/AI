import fs from "fs";
import path from "path";

export function generateRandomString(length: number): string {
  const chars =
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  let result = "";
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

export async function waitForCondition(
  condition: () => Promise<boolean> | boolean,
  timeoutMs = 10_000,
  intervalMs = 500,
): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await condition()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("Condition not met within timeout");
}

export async function retryOperation<T>(
  operation: () => Promise<T>,
  maxRetries = 3,
  delayMs = 500,
): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      if (attempt === maxRetries) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  throw lastError;
}

export async function loadTestData<T = any>(filename: string): Promise<T> {
  const filePath = path.resolve(process.cwd(), "tests", "test-data", filename);
  const content = await fs.promises.readFile(filePath, "utf-8");
  return JSON.parse(content) as T;
}

export async function saveTestResults(
  filename: string,
  data: any,
): Promise<void> {
  const dir = path.resolve(process.cwd(), "tests", "test-results");
  await fs.promises.mkdir(dir, { recursive: true });
  const filePath = path.join(dir, filename);
  await fs.promises.writeFile(filePath, JSON.stringify(data, null, 2), "utf-8");
}
