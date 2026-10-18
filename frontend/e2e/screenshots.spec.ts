import { expect, test } from '@playwright/test'

// Opt-in: capture PRD 22.1 release screenshots from the running production console and API.
// No route mocks. Run with AETHER_LIVE_SMOKE=1 AETHER_SCREENSHOT_DIR=<dir> against serve-demo.sh.
test('release screenshots from actual artifacts', async ({ page, request }) => {
  const dir = process.env.AETHER_SCREENSHOT_DIR
  test.skip(process.env.AETHER_LIVE_SMOKE !== '1' || !dir, 'Requires running artifact API and AETHER_SCREENSHOT_DIR')
  await page.setViewportSize({ width: 1440, height: 1000 })
  const index = await (await request.get('/api/runs')).json()
  const adaptive = index.find((item: { policy_id: string }) => item.policy_id === 'adaptive_eig')
  expect(adaptive).toBeTruthy()
  await page.goto('/')
  await page.getByLabel('Select archived run').selectOption(adaptive.run_id)
  await expect(page.locator('main')).not.toContainText('Reading run archive')
  const shots: [RegExp, string][] = [
    [/Sources/, 'real-data-provenance.png'],
    [/Windows/, 'orbital-windows.png'],
    [/Planner/, 'planner-before-after.png'],
    [/Beliefs/, 'belief-update.png'],
    [/Comparison/, 'baseline-comparison.png'],
  ]
  for (const [name, file] of shots) {
    await page.getByRole('navigation').getByRole('button', { name }).click()
    await expect(page.locator('main')).not.toContainText('Loading artifact')
    await page.screenshot({ path: `${dir}/${file}`, fullPage: true })
  }
})
