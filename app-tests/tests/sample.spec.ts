import { test, expect } from '@playwright/test';

// Placeholder so the pipeline has something to run before any generated
// tests land here. Delete once real app tests exist.
test('placeholder', async ({ page }) => {
  await page.goto('https://www.lambdatest.com');
  await expect(page).toHaveTitle(/LambdaTest/);
});
