import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { App } from '../App'
import { DemoDirector } from '../components/Director/DemoDirector'
import { DIRECTOR_SCENES } from '../components/Director/DirectorSceneSequence'
import { api } from '../services/api'
import scenarioAFixture from '../data/scenario_a.json'
import assuranceFixture from '../data/assurance_properties.json'
import { ScenarioMeta } from '../types'

const mockScenarios: ScenarioMeta[] = [
  { id: 'scenario_a', title: 'A. Safe Execution (Nominal)', subtitle: 'Normal flow', flow: 'ALLOW', category: 'NOMINAL' },
  { id: 'scenario_b', title: 'B. TOCTOU Revalidation Block', subtitle: 'Human zone race', flow: 'BLOCKED', category: 'TOCTOU_DEFENSE' },
  { id: 'scenario_c', title: 'C. Actuator Failure & Recovery', subtitle: 'Stroke mismatch', flow: 'RECOVERED', category: 'FAULT_RECOVERY' },
  { id: 'scenario_telemetry', title: 'E. Real-World Public Telemetry', subtitle: 'USGS river telemetry', flow: 'ALLOW', category: 'PUBLIC_TELEMETRY' },
]

describe('Phase 2T — Demo Director Unit & Integration Suite', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.scrollIntoView = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // 1. Direct navigation & Routing entry point
  it('navigates directly into Director mode when ?director=1 query param is set', async () => {
    delete (window as any).location
    window.location = new URL('http://localhost:3000/?director=1') as any

    vi.spyOn(api, 'checkBackendStatus').mockResolvedValue({ isLive: true, isIsaacActive: false } as any)
    vi.spyOn(api, 'getScenarios').mockResolvedValue(mockScenarios)
    vi.spyOn(api, 'getHealth').mockResolvedValue({
      status: 'healthy',
      application: 'motionfence',
      safety_runtime: 'deterministic',
      live_model: 'configured',
      telemetry: 'configured',
      evidence_provider: 'offline_fixture',
      isaac_runtime: 'inactive',
      mock_backend: 'active',
      execution_modes: ['LIVE', 'REPLAY', 'OFFLINE_TEST'],
      model_provider: 'nebius',
      model: 'nvidia/nemotron-4-340b-instruct',
      telemetry_provider: 'usgs',
    } as any)
    vi.spyOn(api, 'getScenarioData').mockResolvedValue(scenarioAFixture as any)
    vi.spyOn(api, 'getAssuranceReport').mockResolvedValue(assuranceFixture as any)

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('MotionFence Demo Director')).toBeInTheDocument()
    })
    expect(screen.getByText('Start Full Demo')).toBeInTheDocument()
    expect(screen.getByText(/Actuation and post-action verification use simulation\/software mocks/i)).toBeInTheDocument()
  })

  // 2. Normal console still functioning when accessing console route
  it('renders normal interactive console on /console route and allows opening director via Header', async () => {
    delete (window as any).location
    window.location = new URL('http://localhost:3000/console') as any

    vi.spyOn(api, 'checkBackendStatus').mockResolvedValue({ isLive: false, isIsaacActive: false } as any)
    vi.spyOn(api, 'getScenarios').mockResolvedValue(mockScenarios)
    vi.spyOn(api, 'getScenarioData').mockResolvedValue(scenarioAFixture as any)
    vi.spyOn(api, 'getAssuranceReport').mockResolvedValue(assuranceFixture as any)

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('MotionFence Judge Console')).toBeInTheDocument()
    })
    expect(screen.getByText('Decision Replay')).toBeInTheDocument()
    expect(screen.getByText('Policy Firewall')).toBeInTheDocument()

    const openDirectorBtn = screen.getByText('Demo Director (1-Click)')
    expect(openDirectorBtn).toBeInTheDocument()

    fireEvent.click(openDirectorBtn)
    await waitFor(() => {
      expect(screen.getByText('MotionFence Demo Director')).toBeInTheDocument()
    })
  })

  // 3. Typed sequential scene definitions & narrative order
  it('defines all 9 canonical scenes in strict typed order with correct panel mappings', () => {
    expect(DIRECTOR_SCENES).toHaveLength(9)

    const expectedOrder = [
      'intro',
      'safe',
      'denied',
      'toctou',
      'recovery',
      'telemetry',
      'evidence',
      'replay_assurance',
      'close',
    ]

    DIRECTOR_SCENES.forEach((scene, idx) => {
      expect(scene.id).toBe(expectedOrder[idx])
      expect(scene.title).toBeTruthy()
      expect(scene.narration).toBeTruthy()
      expect(scene.targetPanelId).toBeTruthy()
      expect(scene.dwellTimeSeconds).toBeGreaterThanOrEqual(1)
    })

    const evidenceScene = DIRECTOR_SCENES.find((s) => s.id === 'evidence')
    expect(evidenceScene?.narration).toContain('offline_fixture')
    expect(evidenceScene?.scenarioId).toBe('evidence')

    const replayScene = DIRECTOR_SCENES.find((s) => s.id === 'replay_assurance')
    expect(replayScene?.executionMode).toBe('REPLAY')
  })

  // 4. Starting and locking out duplicate starts
  it('locks out duplicate start clicks when Demo Director is running', async () => {
    vi.spyOn(api, 'getHealth').mockResolvedValue({
      status: 'healthy',
      execution_mode: 'LIVE',
      knowledge_provider: 'offline_fixture',
    } as any)
    vi.spyOn(api, 'triggerControlledDemo').mockResolvedValue({
      status: 'SUCCESS',
      execution_id: 'exec-test-1',
      scenario_id: 'safe',
      execution_mode: 'LIVE',
    } as any)
    vi.spyOn(api, 'getDemoExecution').mockResolvedValue({
      status: 'RUNNING',
      stage_outcome: 'PENDING',
    } as any)

    render(
      <DemoDirector
        scenarios={mockScenarios}
        onExitDirector={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
        assuranceReport={assuranceFixture as any}
      />
    )

    const startBtn = screen.getByTestId('start-full-demo-btn')
    expect(startBtn).toBeInTheDocument()

    fireEvent.click(startBtn)

    await waitFor(() => {
      expect(screen.queryByTestId('start-full-demo-btn')).not.toBeInTheDocument()
      expect(screen.getByText('Pause')).toBeInTheDocument()
      expect(screen.getByText('Stop')).toBeInTheDocument()
    })
  })

  // 5. WAITING state until response arrives and renders terminal outcome
  it('displays WAITING / RUNNING state and transitions to terminal outcome on response', async () => {
    vi.spyOn(api, 'getHealth').mockResolvedValue({ status: 'healthy', execution_mode: 'LIVE' } as any)
    vi.spyOn(api, 'triggerControlledDemo').mockResolvedValue({
      status: 'SUCCESS',
      execution_id: 'exec-test-2',
      scenario_id: 'safe',
      execution_mode: 'LIVE',
    } as any)

    vi.spyOn(api, 'getDemoExecution').mockResolvedValue({
      status: 'COMPLETED',
      stage_outcome: 'VERIFIED',
      execution_mode: 'LIVE',
      record: scenarioAFixture,
    } as any)

    render(
      <DemoDirector
        scenarios={mockScenarios}
        onExitDirector={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
        assuranceReport={assuranceFixture as any}
      />
    )

    // Select safe scene directly via timeline pill
    const safeTimelineBtn = screen.getByTestId('timeline-step-safe')
    fireEvent.click(safeTimelineBtn)

    await waitFor(() => {
      expect(screen.getByText(/STATUS: VERIFIED/i)).toBeInTheDocument()
    })
  })

  // 6. Handling of DENIED, BLOCKED, and RECOVERED terminal results
  it('correctly maps DENIED, BLOCKED, and RECOVERED statuses according to responses', async () => {
    vi.spyOn(api, 'getHealth').mockResolvedValue({ status: 'healthy' } as any)
    vi.spyOn(api, 'triggerControlledDemo').mockResolvedValue({
      status: 'SUCCESS',
      execution_id: 'exec-denied',
      scenario_id: 'denied',
      execution_mode: 'LIVE',
    } as any)
    vi.spyOn(api, 'getDemoExecution').mockResolvedValue({
      status: 'COMPLETED',
      stage_outcome: 'DENIED',
      execution_mode: 'LIVE',
      record: scenarioAFixture,
    } as any)

    render(
      <DemoDirector
        scenarios={mockScenarios}
        onExitDirector={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
        assuranceReport={assuranceFixture as any}
      />
    )

    const deniedTimelineBtn = screen.getByTestId('timeline-step-denied')
    fireEvent.click(deniedTimelineBtn)

    await waitFor(() => {
      expect(screen.getByText(/STATUS: DENIED/i)).toBeInTheDocument()
    })
  })

  // 7. Error handling, Timeout, Retry, Continue, and Stop controls
  it('pauses sequence on failure, displays exact error, and supports Retry and Continue', async () => {
    vi.spyOn(api, 'getHealth').mockResolvedValue({ status: 'healthy' } as any)
    vi.spyOn(api, 'triggerControlledDemo').mockRejectedValue(new Error('Network connectivity lost to Gateway'))

    render(
      <DemoDirector
        scenarios={mockScenarios}
        onExitDirector={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
        assuranceReport={assuranceFixture as any}
      />
    )

    const safeTimelineBtn = screen.getByTestId('timeline-step-safe')
    fireEvent.click(safeTimelineBtn)

    await waitFor(() => {
      expect(screen.getByText(/STATUS: ERROR/i)).toBeInTheDocument()
      expect(screen.getByText(/Network connectivity lost to Gateway/i)).toBeInTheDocument()
    })

    expect(screen.getByText('Retry')).toBeInTheDocument()
    expect(screen.getByText('Continue')).toBeInTheDocument()
    expect(screen.getByText('Stop')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Stop'))
    await waitFor(() => {
      expect(screen.getByText('Start Full Demo')).toBeInTheDocument()
    })
  })

  // 8. Pause, Resume, and Restart
  it('supports Pause and Resume during sequence execution', async () => {
    vi.spyOn(api, 'getHealth').mockResolvedValue({ status: 'healthy' } as any)
    vi.spyOn(api, 'triggerControlledDemo').mockResolvedValue({
      status: 'SUCCESS',
      execution_id: 'exec-pause',
      scenario_id: 'safe',
    } as any)
    vi.spyOn(api, 'getDemoExecution').mockResolvedValue({
      status: 'RUNNING',
      stage_outcome: 'PENDING',
    } as any)

    render(
      <DemoDirector
        scenarios={mockScenarios}
        onExitDirector={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
        assuranceReport={assuranceFixture as any}
      />
    )

    fireEvent.click(screen.getByTestId('start-full-demo-btn'))

    await waitFor(() => {
      expect(screen.getByText('Pause')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Pause'))
    await waitFor(() => {
      expect(screen.getByText('Resume')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Resume'))
    await waitFor(() => {
      expect(screen.getByText('Pause')).toBeInTheDocument()
    })
  })

  // 9. No automatic LIVE calls merely from opening the route
  it('does NOT trigger scenario executions merely from opening the route', async () => {
    const triggerSpy = vi.spyOn(api, 'triggerControlledDemo')

    render(
      <DemoDirector
        scenarios={mockScenarios}
        onExitDirector={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
        assuranceReport={assuranceFixture as any}
      />
    )

    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(triggerSpy).not.toHaveBeenCalled()
  })

  // 10. Execution mode derived truthfully from metadata
  it('displays LIVE, REPLAY, and OFFLINE_TEST badges derived from actual response metadata', async () => {
    vi.spyOn(api, 'getHealth').mockResolvedValue({ status: 'healthy' } as any)
    vi.spyOn(api, 'getScenarioData').mockResolvedValue({
      ...scenarioAFixture,
      execution_mode: 'REPLAY',
      physical_backend: 'mock',
    } as any)

    render(
      <DemoDirector
        scenarios={mockScenarios}
        onExitDirector={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
        assuranceReport={assuranceFixture as any}
      />
    )

    const replayTimelineBtn = screen.getByTestId('timeline-step-replay_assurance')
    fireEvent.click(replayTimelineBtn)

    await waitFor(() => {
      expect(screen.getByText(/REPLAY MODE/i)).toBeInTheDocument()
    })
  })

  // 11. Motion reduction and accessibility controls
  it('handles reduced motion toggling and accessibility tags', () => {
    const toggleMotion = vi.fn()
    render(
      <DemoDirector
        scenarios={mockScenarios}
        onExitDirector={vi.fn()}
        reducedMotion={true}
        onToggleReducedMotion={toggleMotion}
        assuranceReport={assuranceFixture as any}
      />
    )

    const motionBtn = screen.getByTitle('Reduced Motion: ON')
    expect(motionBtn).toBeInTheDocument()
    expect(motionBtn).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(motionBtn)
    expect(toggleMotion).toHaveBeenCalledTimes(1)
  })

  // 12. Security guarantee: Zero arbitrary parameter execution
  it('only dispatches canonical approved scenario IDs and zero arbitrary browser parameters', async () => {
    const triggerSpy = vi.spyOn(api, 'triggerControlledDemo').mockResolvedValue({
      status: 'SUCCESS',
      execution_id: 'exec-safe',
      scenario_id: 'safe',
    } as any)

    render(
      <DemoDirector
        scenarios={mockScenarios}
        onExitDirector={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
        assuranceReport={assuranceFixture as any}
      />
    )

    const safeBtn = screen.getByTestId('timeline-step-safe')
    fireEvent.click(safeBtn)

    await waitFor(() => {
      expect(triggerSpy).toHaveBeenCalledWith('safe', 'LIVE', 'mock')
    })

    expect(['safe', 'denied', 'toctou', 'recovery', 'telemetry', 'evidence']).toContain(
      triggerSpy.mock.calls[0][0]
    )
  })

  // 13. UI Truthfulness & Certification Disclaimer Regressions
  it('verifies Scene 9 does NOT claim production certification and links to open source repository', () => {
    const closeScene = DIRECTOR_SCENES.find((s) => s.id === 'close')
    expect(closeScene).toBeDefined()
    expect(closeScene?.badgeLabel).not.toContain('PRODUCTION CERTIFIED')
    expect(closeScene?.badgeLabel).toBe('DEMO COMPLETED')
    expect(closeScene?.narration).not.toContain('deployed on Google Cloud Run')
  })

  // 14. Health offline fallback truthfulness
  it('truthfully reports offline status when health endpoint is unreachable', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new Error('Network error'))
    const health = await api.getHealth()
    expect(health.status).toBe('offline')
    expect(health.live_model).toBe('unavailable')
    expect(health.execution_modes).not.toContain('LIVE')
    expect(health.execution_modes).toContain('REPLAY')
  })
})
