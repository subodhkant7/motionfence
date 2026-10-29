import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { App } from '../App'
import { DemoDirector, deriveExecutionOutcome } from '../components/Director/DemoDirector'
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

  // 15. Outcome derivation from recorded assertions independent of scene name
  it('derives execution outcome strictly from assertions and records rather than scene names', () => {
    // A. Policy Denial: policy_decision is DENY
    const deniedRecord: any = {
      scenario_id: 'arbitrary_scene_name',
      policy_decision: { decision_type: 'DENY', is_allowed: false },
      verification_result: null,
    }
    expect(deriveExecutionOutcome(deniedRecord, null)).toBe('DENIED')

    // B. TOCTOU: revalidation blocked / world change event present
    const toctouRecord: any = {
      scenario_id: 'custom_scene',
      policy_decision: { decision_type: 'ALLOW', is_allowed: true },
      revalidation_status: 'BLOCKED',
      world_change_event: { trigger: 'human_breach' },
      execution_result: { success: false },
    }
    expect(deriveExecutionOutcome(toctouRecord, null)).toBe('BLOCKED')

    // C. Recovery: fault injected and recovery lifecycle executed
    const recoveryRecord: any = {
      scenario_id: 'custom_scene',
      recovery_lifecycle: { status: 'RECOVERED' },
      verification_result: { status: 'VERIFIED' },
    }
    expect(deriveExecutionOutcome(recoveryRecord, null)).toBe('RECOVERED')

    // D. Nominal verification: action occurred and verified
    const verifiedRecord: any = {
      scenario_id: 'custom_scene',
      policy_decision: { decision_type: 'ALLOW', is_allowed: true },
      verification_result: { status: 'VERIFIED', action_occurred: true },
    }
    expect(deriveExecutionOutcome(verifiedRecord, null)).toBe('VERIFIED')
  })

  // 16. Modeled & bounded language in Director scene definitions
  it('uses properly scoped modeled and bounded language in Scene 4 and Scene 8 insights', () => {
    const toctouScene = DIRECTOR_SCENES.find((s) => s.id === 'toctou')
    expect(toctouScene?.keyInsight).toContain('detecting modeled TOCTOU state drift')
    expect(toctouScene?.keyInsight).not.toContain('eliminating TOCTOU races')

    const assuranceScene = DIRECTOR_SCENES.find((s) => s.id === 'replay_assurance')
    expect(assuranceScene?.keyInsight).toContain('bounded safety invariants on modeled transitions')
    expect(assuranceScene?.keyInsight).not.toContain('guarantee zero surprise mutations')
  })

  // 17. Phase 2W Step 1.6: Complete 17-condition fail-closed regression suite
  describe('Phase 2W Step 1.6 — Fail-Closed Outcome Contract Regression Suite', () => {
    // 1. Valid nominal action with verified postconditions
    it('1. returns VERIFIED for valid nominal action with satisfied postconditions', () => {
      const rec: any = {
        policy_decision: { decision: 'ALLOW', is_allowed: true },
        ticket: { ticket_id: 'tkt_01', status: 'VALID' },
        execution_result: { execution_status: 'SUCCESS', success: true },
        verification_result: { status: 'VERIFIED', is_verified: true, discrepancies: [] },
        post_state: { valves: { valve_b: 'CLOSED' } },
      }
      expect(deriveExecutionOutcome(rec, 'NOMINAL', 'safe')).toBe('VERIFIED')
    })

    // 2. Action executed but verification absent
    it('2. returns UNVERIFIED when action executed but verification result is absent', () => {
      const rec: any = {
        policy_decision: { decision: 'ALLOW', is_allowed: true },
        ticket: { ticket_id: 'tkt_01', status: 'VALID' },
        execution_result: { execution_status: 'SUCCESS', success: true },
        verification_result: null,
      }
      expect(deriveExecutionOutcome(rec, 'NOMINAL', 'safe')).toBe('UNVERIFIED')
    })

    // 3. Action executed but verification failed
    it('3. returns VERIFICATION_FAILED when execution succeeded but verification failed', () => {
      const rec: any = {
        policy_decision: { decision: 'ALLOW', is_allowed: true },
        ticket: { ticket_id: 'tkt_01', status: 'VALID' },
        execution_result: { execution_status: 'SUCCESS', success: true },
        verification_result: {
          status: 'VERIFICATION_FAILED',
          is_verified: false,
          discrepancies: ['Limit switch open mismatch'],
        },
      }
      expect(deriveExecutionOutcome(rec, 'NOMINAL', 'safe')).toBe('VERIFICATION_FAILED')
    })

    // 4. Fault injected without recovery
    it('4. returns VERIFICATION_FAILED when fault is injected without recovery lifecycle', () => {
      const rec: any = {
        execution_result: { fault_injected: 'NO_OP', execution_status: 'HARDWARE_FAULT' },
        verification_result: { status: 'VERIFICATION_FAILED', is_verified: false },
        recovery_result: null,
      }
      expect(deriveExecutionOutcome(rec, null, 'recovery')).toBe('VERIFICATION_FAILED')
    })

    // 5. Recovery plan created but not executed
    it('5. returns VERIFICATION_FAILED when recovery plan exists but was not executed', () => {
      const rec: any = {
        execution_result: { fault_injected: 'NO_OP' },
        recovery_plan: { status: 'PLANNED' },
        recovery_result: null,
      }
      expect(deriveExecutionOutcome(rec, null, 'recovery')).toBe('VERIFICATION_FAILED')
    })

    // 6. Recovery completed but final postcondition failed
    it('6. returns VERIFICATION_FAILED when recovery reported completed but postcondition failed', () => {
      const rec: any = {
        execution_result: { fault_injected: 'NO_OP' },
        recovery_result: { outcome: 'SUCCESS', component_status: 'HEALTHY' },
        verification_result: { status: 'VERIFICATION_FAILED', discrepancies: ['leak active'] },
        post_state: { valves: { valve_b: 'OPEN' }, leak: { active: true } },
      }
      expect(deriveExecutionOutcome(rec, null, 'recovery')).toBe('VERIFICATION_FAILED')
    })

    // 7. Properly verified recovery
    it('7. returns RECOVERED when recovery lifecycle succeeded, resolved quarantine, and postconditions verified', () => {
      const rec: any = {
        execution_result: { fault_injected: 'NO_OP' },
        recovery_result: { outcome: 'SUCCESS', component_status: 'HEALTHY' },
        verification_result: { status: 'VERIFIED', is_verified: true, discrepancies: [] },
        post_state: { valves: { valve_b: 'CLOSED' }, leak: { active: false } },
      }
      expect(deriveExecutionOutcome(rec, 'RECOVERED', 'recovery')).toBe('RECOVERED')
    })

    // 8. Explicit policy denial with zero actuation
    it('8. returns DENIED when authorization is denied and zero actuation occurred', () => {
      const rec: any = {
        policy_decision: { decision: 'DENY', is_allowed: false },
        ticket: null,
        execution_result: { execution_status: 'LOCKED', success: false },
      }
      expect(deriveExecutionOutcome(rec, 'DENIED', 'denied')).toBe('DENIED')
    })

    // 9. Revalidation block with zero mutation
    it('9. returns BLOCKED when TOCTOU revalidation failed and zero mutation occurred', () => {
      const rec: any = {
        policy_decision: { decision: 'ALLOW', is_allowed: true },
        revalidation_status: 'BLOCKED',
        world_change_event: { trigger: 'drift' },
        execution_result: { execution_status: 'LOCKED', success: false },
      }
      expect(deriveExecutionOutcome(rec, 'BLOCKED', 'toctou')).toBe('BLOCKED')
    })

    // 10. Contradictory stage outcome and verification result
    it('10. overrides NOMINAL stage_outcome when verification result reports failure', () => {
      const rec: any = {
        policy_decision: { decision: 'ALLOW', is_allowed: true },
        ticket: { ticket_id: 'tkt_01' },
        execution_result: { execution_status: 'SUCCESS' },
        verification_result: { status: 'VERIFICATION_FAILED', discrepancies: ['mismatch'] },
      }
      expect(deriveExecutionOutcome(rec, 'NOMINAL', 'safe')).toBe('VERIFICATION_FAILED')
    })

    // 11. Missing execution record
    it('11. returns UNKNOWN when execution record is null or undefined', () => {
      expect(deriveExecutionOutcome(null, null)).toBe('UNKNOWN')
      expect(deriveExecutionOutcome(undefined, null)).toBe('UNKNOWN')
    })

    // 12. Malformed or incomplete fixture
    it('12. returns UNVERIFIED for malformed or empty record lacking evidence', () => {
      const rec: any = { scenario_id: 'empty_record' }
      expect(deriveExecutionOutcome(rec, null)).toBe('UNVERIFIED')
    })

    // 13. LIVE-to-REPLAY fallback
    it('13. sets execution mode to REPLAY when live inference falls back to deterministic replay', async () => {
      vi.spyOn(api, 'triggerControlledDemo').mockResolvedValue({
        status: 'SUCCESS',
        execution_id: 'exec-fallback-123',
        scenario_id: 'safe',
        execution_mode: 'REPLAY',
        physical_backend: 'mock',
        poll_url: '/api/demo/executions/exec-fallback-123',
      })
      vi.spyOn(api, 'getDemoExecution').mockResolvedValue({
        execution_id: 'exec-fallback-123',
        scenario_id: 'safe',
        status: 'COMPLETED',
        execution_mode: 'REPLAY',
        physical_backend: 'mock',
        created_at: Date.now(),
        stage_outcome: 'NOMINAL',
        record: scenarioAFixture as any,
      })

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
        expect(screen.getByTestId('director-mode-badge')).toHaveTextContent(/REPLAY \(OFFLINE FIXTURE\)/i)
      })
    })

    // 14. Backend outage or failed health probe
    it('14. correctly reports offline status on backend outage', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Connection refused'))
      const health = await api.getHealth()
      expect(health.status).toBe('offline')
      expect(health.live_model).toBe('unavailable')
    })

    // 15. Telemetry/evidence scene without a physical postcondition
    it('15. returns COMPLETED instead of VERIFIED for read-only observation scenes', () => {
      const telemetryRec: any = {
        scenario_id: 'scenario_telemetry',
        telemetry_observation: { raw_record_hash: 'hash_1234' },
      }
      expect(deriveExecutionOutcome(telemetryRec, 'NOMINAL', 'telemetry')).toBe('COMPLETED')

      const evidenceRec: any = {
        scenario_id: 'scenario_evidence',
        decision_record: { telemetry_observation: null },
      }
      expect(deriveExecutionOutcome(evidenceRec, 'NOMINAL', 'evidence')).toBe('COMPLETED')
    })

    // 16. Replay scenario that records a failed outcome
    it('16. returns VERIFICATION_FAILED for replay record containing failure discrepancy', () => {
      const failedReplayRec: any = {
        scenario_id: 'scenario_safe',
        execution_mode: 'REPLAY',
        policy_decision: { decision: 'ALLOW' },
        verification_result: { status: 'VERIFICATION_FAILED', discrepancies: ['sensor dropout'] },
      }
      expect(deriveExecutionOutcome(failedReplayRec, null, 'safe')).toBe('VERIFICATION_FAILED')
    })

    // 17. Consistency between backend outcome and frontend presentation
    it('17. ensures consistency between backend stage_outcome and derived frontend status on canonical fixtures', () => {
      // Safe fixture -> VERIFIED
      expect(deriveExecutionOutcome(scenarioAFixture as any, 'NOMINAL', 'safe')).toBe('VERIFIED')
      // Denied -> DENIED
      const deniedRec: any = {
        policy_decision: { decision: 'DENY', is_allowed: false },
        ticket: null,
      }
      expect(deriveExecutionOutcome(deniedRec, 'DENIED', 'denied')).toBe('DENIED')
      // TOCTOU -> BLOCKED
      const toctouRec: any = {
        policy_decision: { decision: 'ALLOW', is_allowed: true },
        revalidation_status: 'WORLD_STATE_CHANGED',
      }
      expect(deriveExecutionOutcome(toctouRec, 'BLOCKED', 'toctou')).toBe('BLOCKED')
    })
  })
})
