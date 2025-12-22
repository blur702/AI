import { test, expect } from "../../../fixtures/base.fixture";

test.describe("API Gateway health", () => {
test("health endpoint returns success", async ({ gatewayAPI }) => {
try {
const health = await gatewayAPI.getHealth();
expect(health.success).toBe(true);
expect(health).toHaveProperty("status");
expect(health.status).toMatch(/^(healthy|degraded)$/);
expect(health).toHaveProperty("services");
expect(health.services).toHaveProperty("database");
expect(health.services).toHaveProperty("gpu_ok");
expect(health).toHaveProperty("timestamp");
expect(health).toHaveProperty("status");
expect(health.status).toMatch(/^(healthy|degraded)$/);
expect(health).toHaveProperty("services");
expect(health.services).toHaveProperty("database");
expect(health.services).toHaveProperty("gpu_ok");
expect(health).toHaveProperty("timestamp");
const health = await gatewayAPI.getHealth();
expect(health.success).toBe(true);
expect(health).toHaveProperty("status");
expect(health.status).toMatch(/^(healthy|degraded)$/);
expect(health).toHaveProperty("services");
expect(health.services).toHaveProperty("database");
expect(health.services).toHaveProperty("gpu_ok");
expect(health).toHaveProperty("timestamp");
});
expect(health).toHaveProperty("status");
expect(health.status).toMatch(/^(healthy|degraded)$/);
expect(health).toHaveProperty("services");
expect(health.services).toHaveProperty("database");
expect(health.services).toHaveProperty("gpu_ok");
expect(health).toHaveProperty("timestamp");
});
