import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

// UI-11 console acceptance in a real browser. API responses are mocked from e2e/fixtures/ (TEST
// FIXTURES, never results). The real-data bundle is the built /globe/globe-data.json unless a
// test replaces it.
const fixture = (name: string) => JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), 'utf8'))
const run = fixture('run.json')
const project = fixture('project.json')
const protocol = fixture('protocol.json')
const ci = fixture('benchmark-ci-5.json')
const results = fixture('benchmark-results.json')
const bundle = JSON.parse(readFileSync(new URL('../public/globe/globe-data.json', import.meta.url), 'utf8'))

type Api = Partial<Record<'runs' | 'run' | 'project' | 'results' | 'ci' | 'protocol', unknown | number>>

async function mockApi(page: Page, api: Api = {}) {
  const reply = (body: unknown) => (route: Parameters<Parameters<Page['route']>[1]>[0]) =>
    typeof body === 'number' ? route.fulfill({ status: body, json: { detail: 'not available' } }) : route.fulfill({ json: body })
  await page.route('**/api/runs', reply(api.runs ?? [{ run_id: run.run_id, policy_id: run.policy_id, scenario_id: run.scenario_id, family: run.family, seed: run.seed }]))
  await page.route('**/api/runs/*', reply(api.run ?? run))
  await page.route('**/api/project', reply(api.project ?? project))
  await page.route('**/api/benchmark-results.csv', reply(api.results ?? results))
  await page.route('**/api/benchmark-confidence-intervals.json', reply(api.ci ?? ci))
  await page.route('**/api/benchmark-protocol', reply(api.protocol ?? protocol))
}

const pages = [
  ['overview', 'Observation planning for the Permian Basin', 'REAL DATA'],
  ['observations', 'Real observations', 'REAL DATA'],
  ['passes', 'Real satellite passes', 'REAL DATA'],
  ['planner', 'Planner', 'SIMULATION'],
  ['beliefs', 'Beliefs', 'SIMULATION'],
  ['comparison', 'Policy test', 'SIMULATION'],
  ['setup', 'Setup', 'SIMULATION'],
  ['evidence', 'Evidence & exports', 'SIMULATION'],
] as const

// PRD 22.3 / AGENTS.md rule 13.
const FORBIDDEN = [/NASA tasking/i, /detected leak/i, /verified reduction/i, /% better/i, /live telemetry feed/i, /real[- ]time methane/i]

for (const [view, heading, kind] of pages) {
  test(`${view}: renders, is labelled ${kind}, honest wording, no serious accessibility issues`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', e => errors.push(e.message))
    await mockApi(page)
    await page.goto(`/?view=${view}`)
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
    await expect(page.locator('.cx-strip .cx-tag')).toHaveText(kind)
    await expect(page.locator('main')).not.toContainText('Loading the recorded simulation')
    const text = await page.locator('body').innerText()
    for (const rule of FORBIDDEN) expect(text, `forbidden wording ${rule}`).not.toMatch(rule)
    const axe = await new AxeBuilder({ page }).include('main').analyze()
    const serious = axe.violations.filter(v => v.impact === 'serious' || v.impact === 'critical')
    expect(serious.map(v => ({ id: v.id, nodes: v.nodes.map(node => ({ target: node.target, failureSummary: node.failureSummary })) }))).toEqual([])
    expect(errors).toEqual([])
  })
}

test('old view URLs redirect to their replacement pages', async ({ page }) => {
  await mockApi(page)
  for (const [old, heading] of [['live', 'Real satellite passes'], ['sources', 'Real observations'], ['windows', 'Real satellite passes'], ['configuration', 'Setup']]) {
    await page.goto(`/?view=${old}`)
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
  }
})

test('sidebar navigation updates the URL and survives a reload', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Planner' }).click()
  await expect(page).toHaveURL(/view=planner/)
  await page.reload()
  await expect(page.getByRole('heading', { level: 1, name: 'Planner' })).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('heading', { level: 1, name: 'Observation planning for the Permian Basin' })).toBeVisible()
  await expect(page.locator('.cx-globe-link')).toHaveAttribute('href', '/?view=globe')
})

test('each view only requests the data it needs', async ({ page }) => {
  const requested: string[] = []
  page.on('request', request => requested.push(new URL(request.url()).pathname))
  await mockApi(page)
  await page.goto('/?view=setup')
  await expect(page.getByRole('heading', { level: 1, name: 'Setup' })).toBeVisible()
  expect(requested).toContain('/api/project')
  expect(requested).toContain('/api/runs')
  expect(requested).not.toContain('/globe/globe-data.json')
  expect(requested).not.toContain('/api/benchmark-results.csv')
  expect(requested).not.toContain('/api/benchmark-confidence-intervals.json')
  expect(requested).not.toContain('/api/benchmark-protocol')

  requested.length = 0
  await page.getByRole('button', { name: 'Real observations' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Real observations' })).toBeVisible()
  expect(requested).toContain('/globe/globe-data.json')
  expect(requested).not.toContain('/api/runs')
})

test('narrow layout keeps navigation, setup and observation tables usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockApi(page)
  await page.goto('/?view=overview')
  const menu = page.getByRole('button', { name: 'Toggle navigation' })
  await menu.focus()
  await page.keyboard.press('Enter')
  await expect(menu).toHaveAttribute('aria-expanded', 'true')
  await page.getByRole('button', { name: 'Setup', exact: true }).click()
  await expect(menu).toHaveAttribute('aria-expanded', 'false')
  await page.getByRole('spinbutton', { name: 'Random seed' }).fill('1234')
  await expect(page.locator('.cx-command')).toContainText('--seed 1234')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)

  await menu.click()
  await page.getByRole('button', { name: 'Real observations', exact: true }).click()
  const records = page.getByRole('region', { name: 'Pinned EMIT plume records' })
  await expect(records.getByRole('row')).toHaveCount(21)
  await records.focus()
  await expect(records).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('setup prepares a registered CLI run and opens an archived run in the planner', async ({ page }) => {
  await mockApi(page)
  await page.goto('/?view=setup')
  await expect(page.getByRole('heading', { name: 'Prepare a reproducible run' })).toBeVisible()
  await page.getByLabel('Scenario family').selectOption({ index: 1 })
  await page.getByLabel('Policy').selectOption('adaptive_eig')
  await page.getByLabel('Random seed').fill('1234')
  await expect(page.locator('.cx-command code')).toContainText('--seed 1234 --policies adaptive_eig')
  await expect(page.locator('.cx-command code')).toContainText('--family ../configs/scenarios/')
  await page.getByRole('button', { name: 'Open in planner' }).click()
  await expect(page).toHaveURL(/view=planner/)
  await expect(page.getByRole('heading', { level: 1, name: 'Planner' })).toBeVisible()
})

test('missing provider emission rates are shown as not quantified, never as zero', async ({ page }) => {
  await mockApi(page)
  await page.goto('/?view=observations')
  const missing = bundle.emit_records.filter((r: { emission_rate_kg_h: number | null }) => r.emission_rate_kg_h === null)
  expect(missing.length).toBeGreaterThan(0)
  await expect(page.getByText(/^Not quantified/)).toHaveCount(missing.length)
  await expect(page.locator('main')).not.toContainText(/(^|\s)0 kg\/h/)
})

test('expired pass predictions say so instead of claiming there is no pass', async ({ page }) => {
  await mockApi(page)
  const stale = structuredClone(bundle)
  // A real stale snapshot: built long ago, so every predicted pass is in the past too.
  stale.real_passes.from_utc = '2020-01-01T00:00:00+00:00'
  for (const p of stale.real_passes.passes) for (const k of ['start_utc', 'end_utc', 'closest_utc']) p[k] = p[k].replace(/^\d{4}/, '2020')
  await page.route('**/globe/globe-data.json', route => route.fulfill({ json: stale }))
  await page.goto('/?view=passes')
  await expect(page.getByRole('status')).toContainText('These pass predictions have expired')
  await page.goto('/?view=overview')
  await expect(page.locator('.cx-stats')).toContainText('Pass snapshot expired')
})

test('failed API requests produce explicit error states', async ({ page }) => {
  await mockApi(page, { project: 500, ci: 500, results: 500 })
  await page.goto('/?view=setup')
  await expect(page.getByRole('alert')).toContainText('could not be loaded')
  await page.goto('/?view=comparison')
  await expect(page.getByRole('alert')).toContainText('could not be loaded')
})

test('missing real-data bundle is reported while simulation pages keep working', async ({ page }) => {
  await mockApi(page)
  await page.route('**/globe/globe-data.json', route => route.fulfill({ status: 404, body: 'missing' }))
  await page.goto('/?view=observations')
  await expect(page.getByRole('alert')).toContainText('HTTP 404')
  await page.goto('/?view=planner')
  await expect(page.getByRole('heading', { level: 1, name: 'Planner' })).toBeVisible()
})

test('globe links back to the console, separates real from simulated, and names the fleet', async ({ page }) => {
  await page.goto('/?view=globe')
  await expect(page.getByRole('link', { name: 'Open the console' })).toHaveAttribute('href', '/?view=overview')
  await expect(page.getByRole('heading', { name: 'Real satellites' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Simulated mission' })).toBeVisible()
  await expect(page.getByText(/Not live telemetry/)).toBeVisible()
  for (const name of ['Pip', 'Wren', 'Juniper', 'Mochi']) await expect(page.locator('.globe-fleet')).toContainText(name)
  await expect(page.getByRole('button', { name: 'Play' })).toBeVisible()
  await expect(page.getByLabel('Replay speed')).toHaveValue('60')
  await page.getByRole('button', { name: 'Moon close-up', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Moon close-up', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('img', { name: /3D Earth and Moon at physical scale/ })).toBeVisible()
  await expect(page.getByText('Earth and Moon: physical scale · stars: decorative', { exact: true })).toBeVisible()
  const lunarClock = page.getByText(/^Lunar time:/)
  const before = await lunarClock.innerText()
  await page.getByRole('button', { name: 'Animate lunar orbit', exact: true }).click()
  await expect(lunarClock).not.toHaveText(before)
  await page.getByRole('button', { name: 'Pause lunar motion', exact: true }).click()
  await page.getByRole('button', { name: 'Earth–Moon view', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Earth–Moon view', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'Reset lunar time', exact: true }).click()
  await expect(lunarClock).toHaveText(before)
  await page.getByRole('button', { name: 'Play', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Pause', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Pause', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Play', exact: true })).toBeVisible()
})
