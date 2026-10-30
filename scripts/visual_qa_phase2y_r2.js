// From output/playwright/phase2y-r2, run:
// playwright-cli -s=motionfence-r2 run-code --filename=../../../scripts/visual_qa_phase2y_r2.js
// Uses a local production replay server. Only the browser response is mutated.
async page => {
  const base = page.url().split('/').slice(0, 3).join('/')
  const output = '.'
  const errors = []
  page.on('pageerror', error => errors.push(String(error)))
  const assert = (condition, message) => { if (!condition) throw new Error(message) }
  const fixtures = {}
  for (const scene of ['safe', 'denied', 'toctou']) {
    fixtures[scene] = await (await page.request.get(`${base}/api/scenarios/${scene}`)).json()
  }
  const checks = []
  async function select(scene) {
    await page.getByTestId(`timeline-step-${scene}`).click()
    await page.waitForFunction(() => document.querySelector('[data-testid="plant-source"]')?.textContent.includes('RECORDED NEMOTRON INFERENCE'))
    assert((await page.getByTestId('stage-item-verification').innerText()).includes('PENDING'), 'Future verification must remain pending')
  }
  async function check(scene, stage, status, valve, violation = false, screenshot = false) {
    await page.getByTestId(`stage-item-${stage}`).click()
    await page.waitForFunction(expected => document.querySelector('[data-testid="director-status-badge"]')?.textContent.includes(`STATUS: ${expected}`), status)
    const plant = page.locator('.webgl-plant-container')
    const source = JSON.parse(await plant.getAttribute('data-source-state'))
    const radians = valve === 'CLOSED' ? Math.PI / 2 : 0
    await page.waitForFunction(expected => Number(document.querySelector('.webgl-plant-container')?.dataset.renderedValveRadians) === expected, radians)
    const appliedRadians = Number(await plant.getAttribute('data-rendered-valve-radians'))
    assert(source.valve_b_state === valve, 'Wrong recorded valve state')
    assert(fixtures[scene].digital_twin_snapshots.some(s => JSON.stringify(s) === JSON.stringify(source)), 'Plant must receive an unchanged recorded snapshot')
    assert(await page.locator('.webgl-canvas').count() === 1, 'Real WebGL canvas required')
    assert((await page.locator('.outcome-chip').innerText()) === (status === 'VERIFIED' ? 'NOMINAL' : status), 'Stage and Director disagree')
    assert((await page.getByTestId('director-mode-badge').innerText()).includes('REPLAY'), 'Provenance must remain REPLAY')
    const card = page.getByTestId('stage-expanded-content')
    const stageBadge = await page.getByTestId(`stage-item-${stage}`).locator('.stage-pill').innerText()
    let cardStatus = null
    if (stage === 'authorization') {
      cardStatus = await card.locator('.ticket-status-badge').innerText()
      assert(cardStatus === (violation ? 'ERROR' : 'NOT_ISSUED'), 'Wrong authorization card status')
      assert(stageBadge === (violation ? 'FAILED' : 'N/A'), 'Wrong authorization stage status')
    }
    if (violation) {
      assert((await card.getByRole('alert').innerText()).includes('ticket issued despite policy DENY'), 'Missing explicit contradiction disclosure')
      assert(!(await page.locator('.outcome-chip').innerText()).includes('DENIED'), 'Contradiction must not appear as ordinary denial')
    }
    for (const selector of ['.stage-compact-header', '.webgl-plant-container', '.webgl-hud-overlay']) {
      const box = await page.locator(selector).boundingBox()
      assert(box && box.x >= 0 && box.y >= 0 && box.x + box.width <= 1920 && box.y + box.height <= 1080, `Out of viewport: ${selector}`)
    }
    if (screenshot) await page.screenshot({ path: `${output}/contradictory_${stage}_1920x1080.png` })
    checks.push({ scene, stage, injected_ticket: violation, status, stage_badge: stageBadge, card_status: cardStatus, source_snapshot: source, source_path: await page.getByTestId('plant-source').innerText(), applied_valve_radians: appliedRadians })
  }
  await select('denied')
  await check('denied', 'policy', 'DENIED', 'OPEN')
  await check('denied', 'authorization', 'DENIED', 'OPEN')
  await check('denied', 'execution', 'DENIED', 'OPEN')
  await select('safe')
  await check('safe', 'verification', 'VERIFIED', 'CLOSED')
  await select('toctou')
  await check('toctou', 'revalidation', 'BLOCKED', 'OPEN')
  await check('toctou', 'execution', 'BLOCKED', 'OPEN')
  await page.route('**/api/demo/executions/*', async route => {
    const response = await route.fetch()
    const body = await response.json()
    const record = body.scenario_data
    if (body.scenario_id === 'denied' && record) {
      record.ticket = { ...fixtures.safe.ticket, proposal_id: record.decision_record.action_proposal.id }
    }
    await route.fulfill({ response, json: body })
  })
  await select('denied')
  await check('denied', 'policy', 'ERROR', 'OPEN', true)
  await check('denied', 'authorization', 'ERROR', 'OPEN', true, true)
  await check('denied', 'execution', 'ERROR', 'OPEN', true, true)
  await check('denied', 'verification', 'ERROR', 'OPEN', true)
  assert((await page.getByTestId('stage-expanded-content').locator('.verif-badge').innerText()) !== 'VERIFIED', 'Contradiction cannot verify')
  await check('denied', 'authorization', 'ERROR', 'OPEN', true)
  await page.unroute('**/api/demo/executions/*')
  assert(errors.length === 0, `Page errors: ${errors.join('; ')}`)
  return { viewport: page.viewportSize(), browser: 'Chromium headless with SwiftShader WebGL', built_production_bundle: true, injected_record_scope: 'Browser GET response only; one ticket field added; fixture, policy, snapshots and server outcome unchanged', checks, page_errors: errors }
}
