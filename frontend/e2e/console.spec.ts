import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

// UI-05 (comparison), UI-06 (accessibility, keyboard) and the PRD 22.3 wording rules, checked in a
// real browser. Fixtures come from e2e/make_fixtures.py: TEST FIXTURES, never benchmark results.
const fixture = (name: string) => JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), 'utf8'))
const run = fixture('run.json')
const ci30 = fixture('benchmark-ci-30.json')
const ci5 = fixture('benchmark-ci-5.json')
const results = fixture('benchmark-results.json')
const project = fixture('project.json')
const protocol = fixture('protocol.json')

type Api = Partial<Record<'runs' | 'run' | 'example' | 'project' | 'results' | 'ci' | 'protocol', unknown | number>>

async function mockApi(page: Page, api: Api) {
  const reply = (body: unknown | number | undefined) => (route: Parameters<Parameters<Page['route']>[1]>[0]) =>
    typeof body === 'number' || body === undefined
      ? route.fulfill({ status: typeof body === 'number' ? body : 404, json: { detail: 'not available' } })
      : route.fulfill({ json: body })
  await page.route('**/api/runs', reply(api.runs ?? []))
  await page.route('**/api/runs/*', reply(api.run))
  await page.route('**/api/example', reply(api.example))
  await page.route('**/api/project', reply(api.project ?? project))
  await page.route('**/api/benchmark-results.csv', reply(api.results))
  await page.route('**/api/benchmark-confidence-intervals.json', reply(api.ci))
  await page.route('**/api/benchmark-protocol', reply(api.protocol ?? protocol))
}

const withRun: Api = { runs: [{ run_id: run.run_id, policy_id: run.policy_id, scenario_id: run.scenario_id, family: run.family, seed: run.seed }], run }

async function openComparison(page: Page, api: Api) {
  await mockApi(page, api)
  await page.goto('/')
  await expect(page.locator('main')).not.toContainText('Reading run archive')
  await page.keyboard.press('6')
}

const row = (page: Page, family: string, a: string, b: string, metric: string) =>
  page.getByRole('row').filter({ hasText: family }).filter({ hasText: `${a} − ${b}` }).filter({ hasText: metric.replaceAll('_', ' ') })

test('planner shows actual checker record, forecast cause and absent runtime honestly', async ({ page }) => {
  const replay = structuredClone(run)
  replay.plans[0].runtime_s = null
  replay.plans[0].cause = 'forecast_revision'
  replay.events = [{ event_id: 'forecast-event', event_type: 'FORECAST_REVISED',
    event_time_sim_utc: '2026-01-01T06:00:00+00:00', payload: { injected: true } }]
  await mockApi(page, { ...withRun, run: replay })
  await page.goto('/')
  await expect(page.locator('main')).not.toContainText('Reading run archive')
  await page.keyboard.press('5')
  await expect(page.locator('main')).toContainText('Not recorded')
  await expect(page.locator('main')).toContainText('0 violations')
  await expect(page.locator('main')).toContainText('forecast_revision')
  await page.getByText('Recorded forecast events (1)').click()
  await expect(page.getByRole('table', { name: 'Recorded forecast revisions' })).toContainText('2026-01-01 06:00:00Z')
  await expect(page.getByRole('table', { name: 'Recorded forecast revisions' })).not.toContainText('+00:00Z')
})

test('paired intervals are read with the recorded direction', async ({ page }) => {
  await openComparison(page, { ...withRun, results, ci: ci30 })
  const main = page.locator('main')
  await expect(main).toContainText('PRELIMINARY · UNLOCKED DEVELOPMENT PROTOCOL')
  await expect(main).toContainText('Tuning-seed results; not a pre-registered test.')
  await expect(main).toContainText('30 seeds')
  await expect(main).toContainText('Success criterion met')
  await expect(row(page, 'm0_well_specified', 'adaptive_eig', 'largest_first', 'brier_active_state')).toContainText('FAVOURS adaptive_eig')
  await expect(row(page, 'm2_pod_optimistic', 'adaptive_eig', 'largest_first', 'brier_active_state')).toContainText('INTERVAL INCLUDES 0')
  // A loss is shown like a win, not hidden (protocol: report every family).
  await expect(row(page, 'r1_resource_scarce', 'adaptive_eig', 'largest_first', 'brier_active_state')).toContainText('FAVOURS largest_first')
  await expect(row(page, 'm1_persistence_wrong', 'adaptive_eig', 'largest_first', 'brier_active_state')).toContainText('counted win')
  await expect(row(page, 'm2_pod_optimistic', 'adaptive_eig', 'largest_first', 'brier_active_state')).toContainText('not a counted win')
  await expect(row(page, 'm0_well_specified', 'adaptive_eig', 'largest_first', 'brier_active_state')).toContainText('30')
  await expect(main.getByText('lower is better').first()).toBeVisible()
  await expect(main.getByText('higher is better').first()).toBeVisible()
  await expect(main.getByRole('table', { name: /aggregate/i })).toContainText('N SEEDS')
})

test('fewer than 10 seeds: insufficient samples, no reading, no verdict', async ({ page }) => {
  await openComparison(page, { ...withRun, results, ci: ci5 })
  const main = page.locator('main')
  await expect(main.getByText('INSUFFICIENT SAMPLES').first()).toBeVisible()
  await expect(main).not.toContainText('FAVOURS')
  await expect(main).not.toContainText('Success criterion met')
  await expect(main).toContainText('NO PROTOCOL VERDICT')
})

test('aggregates without the interval report: no comparison is read', async ({ page }) => {
  await openComparison(page, { ...withRun, results, ci: 404 })
  const main = page.locator('main')
  await expect(main).toContainText('Paired intervals unavailable')
  await expect(main).toContainText('Means alone are not comparisons')
  await expect(main).not.toContainText('FAVOURS')
})

test('interval report without aggregates, and an invalid report', async ({ page }) => {
  await openComparison(page, { ...withRun, ci: ci30 })
  await expect(page.locator('main')).toContainText('AGGREGATES UNAVAILABLE')
  await page.unrouteAll()
  await openComparison(page, { ...withRun, results, ci: 422 })
  await expect(page.locator('main')).toContainText('Paired intervals unavailable')
})

test('project mode shows evaluator output when it exists', async ({ page }) => {
  await openComparison(page, { ci: ci30, results })
  await expect(page.locator('main')).toContainText('FAVOURS adaptive_eig')
  await page.unrouteAll()
  await openComparison(page, {})
  await expect(page.locator('main')).toContainText('NO BENCHMARK RESULTS')
})

for (const [mode, api] of [['run', { ...withRun, results, ci: ci30 }], ['project', { results, ci: ci30 }]] as const) {
  test(`axe: zero serious or critical violations on every screen (${mode} mode)`, async ({ page }) => {
    await mockApi(page, api)
    await page.goto('/')
    await expect(page.locator('main')).not.toContainText('Reading run archive')
    for (const key of ['1', '2', '3', '4', '5', '6', '7']) {
      await page.keyboard.press(key)
      const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()
      const bad = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
      expect(bad.map((v) => `${key}: ${v.id} (${v.nodes.length}) ${v.nodes[0]?.target}`)).toEqual([])
    }
  })
}

test('keyboard: skip link, number keys and focusable navigation', async ({ page }) => {
  await mockApi(page, { ...withRun, results, ci: ci30 })
  await page.goto('/')
  await expect(page.locator('main')).not.toContainText('Reading run archive')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#main-content/)
  for (const [key, name] of [['3', 'Windows'], ['6', 'Comparison'], ['7', 'Method']]) {
    await page.keyboard.press(key)
    await expect(page.getByRole('button', { name: new RegExp(name) })).toHaveAttribute('aria-current', 'page')
  }
  const nav = page.getByRole('navigation').getByRole('button').first()
  await nav.focus()
  await page.keyboard.press('Enter')
  await expect(nav).toHaveAttribute('aria-current', 'page')
})

// PRD 22.3, AGENTS rule 13, Parameter_2 UX-COPY-003: banned wording on any rendered screen.
const BANNED = [/NASA tasking/i, /detected leak/i, /verified reduction/i, /% better/i, /\blive\b/i, /leak fixed/i,
  /violator/i, /confirmed emitter/i, /AI-powered/i, /seamless/i, /\bunlock\b/i, /harness/i, /revolutioni[sz]e/i,
  /cutting-edge/i, /next-gen/i, /game-changer/i, /supercharge/i, /effortless/i, /\bmagic\b/i, /\bproved\b/i]

for (const [mode, api] of [['run', { ...withRun, results, ci: ci30 }], ['project', { results, ci: ci30 }]] as const) {
  test(`wording: no banned claims on any screen (${mode} mode)`, async ({ page }) => {
    await mockApi(page, api)
    await page.goto('/')
    await expect(page.locator('main')).not.toContainText('Reading run archive')
    for (const key of ['1', '2', '3', '4', '5', '6', '7']) {
      await page.keyboard.press(key)
      const text = await page.locator('body').innerText()
      const hits = BANNED.flatMap((p) => [...text.matchAll(new RegExp(p.source, 'gi'))].map((m) => `${key}: …${text.slice(Math.max(0, m.index! - 40), m.index! + 40).replaceAll('\n', ' ')}…`))
      // "optimal" only as the recorded solver status (rule 13).
      hits.push(...[...text.matchAll(/optimal/gi)].filter((m) => m[0] !== 'OPTIMAL').map((m) => `${key}: ${m[0]}`))
      expect(hits).toEqual([])
    }
  })
}


test('belief chart uses elapsed UTC time for irregular snapshots', async ({ page }) => {
  const replay = structuredClone(run)
  const original = replay.beliefs[0]
  replay.beliefs = [0, 1, 6].map((hour) => ({ ...original,
    state_time_utc: `2026-01-01T0${hour}:00:00Z` }))
  await mockApi(page, { ...withRun, run: replay })
  await page.goto('/')
  await page.getByRole('navigation').getByRole('button', { name: /Beliefs/ }).click()
  await page.getByRole('combobox', { name: 'Select source', exact: true }).selectOption(original.source_id)
  const circles = page.locator('svg[aria-label^="Activity probability"] circle')
  await expect(circles).toHaveCount(3)
  const positions = await circles.evaluateAll((items) => items.map((item) => Number(item.getAttribute('cx'))))
  expect((positions[1] - positions[0]) / (positions[2] - positions[0])).toBeCloseTo(1 / 6, 8)
})


test('historical context preserves null flux, unknown uncertainty and source lineage', async ({ page }) => {
  const replay = structuredClone(run)
  replay.sources[0].seeded_from_plume_id = 'NASA:historical-test'
  await mockApi(page, { ...withRun, run: replay })
  await page.route('**/api/runs/*/historical-context', (route) => route.fulfill({ json: {
    status: 'pinned',
    input_dataset: { dataset_id: 'TEST ONLY', manifest_path: 'data/manifests/test.json', manifest_sha256: 'a'.repeat(64),
      normalized_sha256: 'b'.repeat(64), record_count: 1, in_region_count: 1, seeded_source_count: 1, uniform_fill_count: 1 },
    manifest: { citation_text: 'TEST ONLY', retrieval: { status: 'UNAVAILABLE', retrieved_at_utc: null } },
    observations: [{ id: 'NASA:historical-test', native_id: 'historical-test', provider: 'NASA LP DAAC', dataset_version: '002',
      provenance_class: 'REAL_OBSERVATION', acquisition_time_utc: '2023-01-01T00:00:00Z', lon: -103, lat: 32,
      emission_rate_kg_h: null, emission_rate_uncertainty_kg_h: 20, missing_rate_reason: 'CRITERIA_NOT_MET',
      uncertainty_kind: 'UNKNOWN', quality_flags: [], source: { provider: 'NASA LP DAAC', url: 'https://example.invalid/granule.json',
        sha256: 'c'.repeat(64) } }],
  } }))
  await page.goto('/')
  await page.getByRole('navigation').getByRole('button', { name: /Sources/ }).click()
  await expect(page.getByRole('table', { name: 'Source hypothesis coordinates' })).toContainText('Seeded from historical plume: NASA:historical-test')
  await expect(page.getByRole('table', { name: 'Source hypothesis coordinates' })).toContainText('Uniform simulated fill')
  const evidence = page.getByRole('region', { name: 'Historical plume evidence' }).getByRole('table')
  await expect(evidence).toContainText('Not estimated (CRITERIA_NOT_MET)')
  await expect(evidence).toContainText('2023-01-01T00:00:00Z')
  await expect(evidence).toContainText('Meaning: unknown; no interval or standard deviation is inferred')
  await expect(page.locator('main')).toContainText('uniform synthetic fill: 1')
  await page.getByText('Dataset citation, retrieval evidence and input lineage').click()
  await expect(page.locator('main')).toContainText('UNAVAILABLE')
  const audit = await new AxeBuilder({ page }).include('main').analyze()
  expect(audit.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([])
})

test('project EMIT context is separate from the synthetic parser fixture', async ({ page }) => {
  await mockApi(page, {})
  await page.route('**/api/project/historical-context', (route) => route.fulfill({ json: {
    status: 'pinned',
    input_dataset: { dataset_id: 'TEST ONLY', manifest_path: 'data/manifests/test.json', manifest_sha256: 'a'.repeat(64),
      normalized_sha256: 'b'.repeat(64), record_count: 1 },
    manifest: { provider: 'NASA LP DAAC', dataset: 'EMITL2BCH4PLM', version: '002',
      retrieval: { status: 'UNAVAILABLE', retrieved_at_utc: null, evidence: 'TEST ONLY' } },
    observations: [{ id: 'NASA:project-test', native_id: 'project-test', provider: 'NASA LP DAAC', dataset_version: '002',
      provenance_class: 'REAL_OBSERVATION', acquisition_time_utc: '2023-02-01T12:30:00Z', lon: -103, lat: 32,
      emission_rate_kg_h: 1200, emission_rate_uncertainty_kg_h: null, missing_rate_reason: null,
      uncertainty_kind: 'UNKNOWN', quality_flags: [], source: { provider: 'NASA LP DAAC', url: 'https://example.invalid/source.json',
        sha256: 'c'.repeat(64) } }],
  } }))
  await page.goto('/')
  await expect(page.locator('main')).toContainText('PROJECT DATA')
  await page.keyboard.press('2')
  const main = page.locator('main')
  await expect(main).toContainText('REAL_OBSERVATION')
  await expect(main).toContainText('2023-02-01T12:30:00Z')
  await expect(main).toContainText('1,200 kg/h')
  await expect(main).toContainText('Unavailable')
  await expect(main).toContainText('SYNTHETIC FIXTURE')
  await expect(main).toContainText('EXAMPLE ONLY · NOT SOURCE VERIFIED')
})

test('comparison shows recorded whole-run timing separately from solver runtime', async ({ page }) => {
  await mockApi(page, { ...withRun, results, ci: ci5 })
  await page.route('**/api/development-timing.json', (route) => route.fulfill({ json: {
    complete_comparison_elapsed_s: 12.75, runs: [{ run_id: run.run_id, complete_run_elapsed_s: 12.5 }],
  } }))
  await page.goto('/')
  await page.getByRole('navigation').getByRole('button', { name: /Comparison/ }).click()
  await expect(page.getByRole('table', { name: 'Measured development timing' })).toContainText('12.5')
  await expect(page.locator('main')).toContainText('Complete comparison: 12.75 s')
  await expect(page.locator('main')).toContainText('Solver runtime is unavailable here')
})

test('method shows archived manifest, and historical API failures remain explicit', async ({ page }) => {
  await mockApi(page, withRun)
  await page.route(/\/api\/runs\/[^/]+\/manifest\.json$/, (route) => route.fulfill({ json: {
    input_sha256: { 'data/old-selected.json': 'c'.repeat(64) }, package_versions: { aether: 'TEST ONLY' },
  } }))
  await page.route('**/api/runs/*/historical-context', (route) => route.fulfill({ status: 422, json: { detail: 'invalid' } }))
  await page.goto('/')
  await page.getByRole('navigation').getByRole('button', { name: /Sources/ }).click()
  await expect(page.locator('main')).toContainText('Artifact could not be validated or read')
  await page.getByRole('navigation').getByRole('button', { name: /Method/ }).click()
  await page.getByText('Inspect input hashes, package versions, and dataset identity').click()
  await expect(page.locator('main')).toContainText('data/old-selected.json')
  await expect(page.locator('main')).toContainText('c'.repeat(64))
})
