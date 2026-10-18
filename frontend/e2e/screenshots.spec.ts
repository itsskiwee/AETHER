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
  const shots: [string, string][] = [
    ['globe', 'globe.png'],
    ['observations', 'real-data-provenance.png'],
    ['passes', 'real-satellite-passes.png'],
    ['planner', 'planner-timeline.png'],
    ['beliefs', 'belief-update.png'],
    ['comparison', 'policy-test.png'],
  ]
  for (const [view, file] of shots) {
    await page.goto(`/?view=${view}&run=${encodeURIComponent(adaptive.run_id)}`)
    await expect(page.locator('body')).not.toContainText('Loading the recorded simulation')
    await page.waitForTimeout(view === 'globe' ? 3000 : 300)
    await page.screenshot({ path: `${dir}/${file}`, fullPage: view !== 'globe' })
  }
})
