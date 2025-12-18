/**
 * Atomic React Theme Tests
 *
 * Tests for the Drupal Atomic React theme deployed at kevinalthaus.com.
 * Verifies theme is active, accessibility features work, and WCAG AA compliance.
 *
 * Note: The site has password protection for anonymous users. Tests check
 * for theme elements that should be present even on the password page,
 * or require authentication.
 */

import { test, expect, Page } from '@playwright/test';

const DRUPAL_BASE_URL = 'https://kevinalthaus.com';

// Drupal credentials from environment
const DRUPAL_USER = process.env.DRUPAL_USER || '';
const DRUPAL_PASS = process.env.DRUPAL_PASS || '';

/**
 * Helper to login to Drupal
 */
async function drupalLogin(page: Page): Promise<boolean> {
  if (!DRUPAL_USER || !DRUPAL_PASS) {
    console.log('Drupal credentials not provided, skipping login');
    return false;
  }

  await page.goto(`${DRUPAL_BASE_URL}/user/login`);
  await page.fill('input[name="name"]', DRUPAL_USER);
  await page.fill('input[name="pass"]', DRUPAL_PASS);
  await page.click('input[type="submit"][value="Log in"]');
  await page.waitForLoadState('networkidle');

  const url = page.url();
  const success = !url.includes('/user/login');
  console.log(success ? 'Drupal login successful' : 'Drupal login failed');
  return success;
}

/**
 * Check if page is password protected
 */
async function isPasswordProtected(page: Page): Promise<boolean> {
  const content = await page.content();
  return content.includes('page-password-protect') ||
         content.includes('password-form') ||
         content.includes('Enter Password');
}

test.describe('Atomic React Theme - Basic Loading (Anonymous)', () => {
  test('Homepage loads without server error', async ({ page }) => {
    const response = await page.goto(DRUPAL_BASE_URL);

    // Page should load (200 or password page)
    expect(response?.status()).toBeLessThan(500);
    await page.waitForLoadState('domcontentloaded');

    // Check for skip link (should be present on any page using the theme)
    const skipLink = page.locator('a[href="#main-content"]');
    const hasSkipLink = await skipLink.count() > 0;

    console.log(`Skip link present: ${hasSkipLink}`);
    console.log(`Page may be password protected: ${await isPasswordProtected(page)}`);
  });

  test('Page structure is valid HTML', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('domcontentloaded');

    // Check basic HTML structure
    const hasHtml = await page.locator('html').count() > 0;
    const hasBody = await page.locator('body').count() > 0;
    const hasHead = await page.locator('head').count() > 0;

    expect(hasHtml).toBe(true);
    expect(hasBody).toBe(true);
    expect(hasHead).toBe(true);
    console.log('Valid HTML structure confirmed');
  });
});

test.describe('Atomic React Theme - Authenticated', () => {
  test.skip(!DRUPAL_USER || !DRUPAL_PASS, 'Drupal credentials not configured');

  test.beforeEach(async ({ page }) => {
    const loggedIn = await drupalLogin(page);
    expect(loggedIn).toBe(true);
  });

  test('Homepage loads with full theme elements', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('domcontentloaded');

    // Check for theme-specific elements
    const skipLink = page.locator('.skip-link');
    await expect(skipLink).toBeAttached();

    // Check for site header
    const siteHeader = page.locator('.site-header');
    await expect(siteHeader).toBeVisible();

    // Check for theme toggle button
    const themeToggle = page.locator('#theme-toggle');
    await expect(themeToggle).toBeAttached();

    // Check for back-to-top button
    const backToTop = page.locator('#back-to-top');
    await expect(backToTop).toBeAttached();

    console.log('Atomic React theme loaded successfully');
  });

  test('Theme CSS variables are defined', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('networkidle');

    const primaryColor = await page.evaluate(() => {
      return getComputedStyle(document.documentElement).getPropertyValue('--color-primary');
    });

    expect(primaryColor.trim()).not.toBe('');
    console.log(`Primary color CSS variable: ${primaryColor.trim()}`);
  });

  test('Theme JavaScript behaviors are attached', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('networkidle');

    const hasBehaviors = await page.evaluate(() => {
      return typeof (window as any).Drupal !== 'undefined' &&
             typeof (window as any).Drupal.behaviors !== 'undefined' &&
             typeof (window as any).Drupal.behaviors.atomicReactThemeToggle !== 'undefined';
    });

    expect(hasBehaviors).toBe(true);
    console.log('Theme behaviors loaded');
  });
});

test.describe('Atomic React Theme - Accessibility (WCAG AA)', () => {
  test.skip(!DRUPAL_USER || !DRUPAL_PASS, 'Drupal credentials not configured');

  test.beforeEach(async ({ page }) => {
    await drupalLogin(page);
  });

  test('Skip link is functional', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('domcontentloaded');

    const skipLink = page.locator('.skip-link');

    // Skip link should be visually hidden initially
    const initialBoundingBox = await skipLink.boundingBox();
    // Skip link moves off-screen with top: -100%

    // Tab to reveal skip link
    await page.keyboard.press('Tab');

    // Skip link should now be visible (focused)
    await expect(skipLink).toBeFocused();

    // Click skip link
    await skipLink.click();

    // Main content should be focused
    const mainContent = page.locator('#main-content');
    await expect(mainContent).toBeFocused();

    console.log('Skip link functionality verified');
  });

  test('Focus is visible on interactive elements', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('domcontentloaded');

    // Tab through page and check focus visibility
    await page.keyboard.press('Tab'); // Skip link
    await page.keyboard.press('Tab'); // Next focusable element

    // Get currently focused element
    const focusedElement = page.locator(':focus');

    // Check that focus ring is visible (has outline)
    const outlineStyle = await focusedElement.evaluate((el) => {
      return getComputedStyle(el).outlineWidth;
    });

    // Should have visible focus ring
    expect(outlineStyle).not.toBe('0px');
    console.log('Focus visibility verified');
  });

  test('Touch targets meet 44px minimum', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('domcontentloaded');

    // Check theme toggle button size
    const themeToggle = page.locator('#theme-toggle');
    const toggleBox = await themeToggle.boundingBox();

    expect(toggleBox?.width).toBeGreaterThanOrEqual(44);
    expect(toggleBox?.height).toBeGreaterThanOrEqual(44);

    console.log(`Theme toggle size: ${toggleBox?.width}x${toggleBox?.height}px`);
  });

  test('Live region exists for announcements', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('domcontentloaded');

    const liveRegion = page.locator('#drupal-live-announce');
    await expect(liveRegion).toBeAttached();

    const ariaLive = await liveRegion.getAttribute('aria-live');
    expect(ariaLive).toBe('polite');

    console.log('Live region for screen reader announcements verified');
  });
});

test.describe('Atomic React Theme - Dark Mode', () => {
  test.skip(!DRUPAL_USER || !DRUPAL_PASS, 'Drupal credentials not configured');

  test.beforeEach(async ({ page }) => {
    await drupalLogin(page);
  });

  test('Theme toggle switches between light and dark mode', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('networkidle');

    const themeToggle = page.locator('#theme-toggle');
    const html = page.locator('html');

    // Get initial theme
    const initialTheme = await html.getAttribute('data-theme');
    console.log(`Initial theme: ${initialTheme || 'light (default)'}`);

    // Click toggle
    await themeToggle.click();
    await page.waitForTimeout(300); // Wait for transition

    // Theme should have changed
    const newTheme = await html.getAttribute('data-theme');
    console.log(`New theme: ${newTheme}`);

    // Toggle back
    await themeToggle.click();
    await page.waitForTimeout(300);

    const finalTheme = await html.getAttribute('data-theme');
    console.log(`Final theme: ${finalTheme}`);

    // Themes should be different after toggle
    expect(newTheme).not.toBe(initialTheme);
    console.log('Theme toggle functionality verified');
  });

  test('Theme preference persists in localStorage', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('networkidle');

    const themeToggle = page.locator('#theme-toggle');

    // Toggle to dark mode
    await themeToggle.click();
    await page.waitForTimeout(300);

    // Check localStorage
    const storedTheme = await page.evaluate(() => {
      return localStorage.getItem('atomic-react-theme');
    });

    expect(storedTheme).not.toBeNull();
    console.log(`Stored theme preference: ${storedTheme}`);
  });
});

test.describe('Atomic React Theme - Responsive Design', () => {
  test.skip(!DRUPAL_USER || !DRUPAL_PASS, 'Drupal credentials not configured');

  test.beforeEach(async ({ page }) => {
    await drupalLogin(page);
  });

  test('Mobile menu toggle appears on small screens', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });

    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('domcontentloaded');

    const menuToggle = page.locator('#mobile-menu-toggle');
    await expect(menuToggle).toBeVisible();

    console.log('Mobile menu toggle visible on small screen');
  });

  test('Mobile menu opens and closes', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });

    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('domcontentloaded');

    const menuToggle = page.locator('#mobile-menu-toggle');
    const mobileMenu = page.locator('#mobile-menu');

    // Menu should be hidden initially
    await expect(mobileMenu).toBeHidden();

    // Open menu
    await menuToggle.click();
    await page.waitForTimeout(300);

    // Menu should be visible
    await expect(mobileMenu).toBeVisible();

    // aria-expanded should be true
    const expanded = await menuToggle.getAttribute('aria-expanded');
    expect(expanded).toBe('true');

    // Close menu with Escape
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);

    // Menu should be hidden again
    await expect(mobileMenu).toBeHidden();

    console.log('Mobile menu open/close verified');
  });

  test('Desktop navigation is visible on large screens', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });

    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('domcontentloaded');

    const primaryNav = page.locator('.site-header__primary-nav');
    const menuToggle = page.locator('#mobile-menu-toggle');

    // Primary nav should be visible
    await expect(primaryNav).toBeVisible();

    // Mobile toggle should be hidden
    await expect(menuToggle).toBeHidden();

    console.log('Desktop navigation layout verified');
  });
});

test.describe('Atomic React Theme - Semantic Structure', () => {
  test.skip(!DRUPAL_USER || !DRUPAL_PASS, 'Drupal credentials not configured');

  test.beforeEach(async ({ page }) => {
    await drupalLogin(page);
  });

  test('Page has proper landmark roles', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('domcontentloaded');

    // Check for banner role (header)
    const header = page.locator('[role="banner"]');
    await expect(header).toBeAttached();

    // Check for main role
    const main = page.locator('[role="main"]');
    await expect(main).toBeAttached();

    // Check for contentinfo role (footer)
    const footer = page.locator('[role="contentinfo"]');
    await expect(footer).toBeAttached();

    // Check for navigation role
    const nav = page.locator('[role="navigation"]').first();
    await expect(nav).toBeAttached();

    console.log('All landmark roles present');
  });

  test('Navigation has proper aria-labels', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('domcontentloaded');

    const mainNav = page.locator('nav[aria-label]').first();
    const ariaLabel = await mainNav.getAttribute('aria-label');

    expect(ariaLabel).not.toBeNull();
    expect(ariaLabel?.length).toBeGreaterThan(0);

    console.log(`Navigation aria-label: ${ariaLabel}`);
  });
});

test.describe('Atomic React Theme - Back to Top', () => {
  test.skip(!DRUPAL_USER || !DRUPAL_PASS, 'Drupal credentials not configured');

  test.beforeEach(async ({ page }) => {
    await drupalLogin(page);
  });

  test('Back to top button appears on scroll', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('domcontentloaded');

    const backToTop = page.locator('#back-to-top');

    // Should not be visible initially
    const initiallyHidden = await backToTop.evaluate((el) => {
      return !el.classList.contains('back-to-top--visible');
    });
    expect(initiallyHidden).toBe(true);

    // Scroll down
    await page.evaluate(() => window.scrollTo(0, 500));
    await page.waitForTimeout(300);

    // Should now be visible
    const visibleAfterScroll = await backToTop.evaluate((el) => {
      return el.classList.contains('back-to-top--visible');
    });
    expect(visibleAfterScroll).toBe(true);

    console.log('Back to top button visibility verified');
  });

  test('Back to top button scrolls to top', async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState('domcontentloaded');

    // Scroll down
    await page.evaluate(() => window.scrollTo(0, 500));
    await page.waitForTimeout(300);

    const backToTop = page.locator('#back-to-top');
    await backToTop.click();

    // Wait for scroll animation
    await page.waitForTimeout(500);

    // Should be at top
    const scrollY = await page.evaluate(() => window.scrollY);
    expect(scrollY).toBeLessThan(50);

    console.log('Back to top scroll functionality verified');
  });
});
