import { expect } from '@playwright/test';

/** Wait until every finite CSS animation/transition inside `selector` has finished. */
export async function settle(page, selector) {
  const target = page.locator(selector).first();
  await expect(target).toBeVisible();
  await target.evaluate(async (element) => {
    if (typeof element.getAnimations !== 'function') return;
    const animations = element.getAnimations({ subtree: true });
    await Promise.all(animations.map((animation) => animation.finished.catch(() => undefined)));
  });
}

/** Wait for an overlay to reach its open state and stop moving. */
export async function settleOverlay(page) {
  const overlay = page.locator('.overlay').last();
  await expect(overlay).toHaveAttribute('data-state', 'open');
  await settle(page, '.overlay .overlay__panel > *');
}
