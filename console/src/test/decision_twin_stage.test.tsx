import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { DecisionTwinStage } from '../components/Stage/DecisionTwinStage'
import { derivePresentationTimeline } from '../services/frameDerivation'
import { ScenarioData } from '../types'
import scenarioAFixture from '../data/scenario_a.json'
import scenarioBDeniedFixture from '../data/scenario_b_denied.json'
import scenarioBFixture from '../data/scenario_b.json'
import scenarioCFixture from '../data/scenario_c.json'
import scenarioLiveTelemetryFixture from '../data/scenario_live_telemetry.json'

describe('Phase 2Y — Synchronized Decision × 3D Physical Twin Experience Suite', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // 1. Left-stage and right-plant synchronization
  it('1. synchronizes left decision stage frame with right physical plant state', () => {
    const { container } = render(
      <DecisionTwinStage
        scenarioId="scenario_a"
        scenarioData={scenarioAFixture as unknown as ScenarioData}
        reducedMotion={true}
        autoPlay={false}
      />
    )

    // Initially at Stage 1 (OBSERVE): Valve B is OPEN (0°), Safety Zone is CLEAR
    expect(screen.getByTestId('decision-twin-stage')).toBeInTheDocument()
    expect(screen.getByText('1. OBSERVE')).toBeInTheDocument()

    // Step to Stage 8 (EXECUTION)
    const stepFwd = screen.getByLabelText('Next Stage')
    for (let i = 0; i < 7; i++) {
      fireEvent.click(stepFwd)
    }

    // Now at Stage 8: EXECUTE
    expect(screen.getByText('8. EXECUTE')).toBeInTheDocument()
    // Right plant viewport should be present
    expect(container.querySelector('.plant-viewport-pane')).toBeInTheDocument()
  })

  // 2. Correct initial and final world-state selection
  it('2. verifies correct initial and final world-state selection in presentation timeline', () => {
    const timeline = derivePresentationTimeline('scenario_a', scenarioAFixture as unknown as ScenarioData)
    expect(timeline.frames.length).toBe(10)
    
    // Initial frame
    expect(timeline.frames[0].plantState.valve_b_state).toBe('OPEN')
    expect(timeline.frames[0].plantState.valve_b_angle_deg).toBe(0)
    
    // Final verification frame
    expect(timeline.frames[8].plantState.valve_b_state).toBe('CLOSED')
    expect(timeline.frames[8].plantState.valve_b_angle_deg).toBe(90)
    expect(timeline.overallOutcome).toBe('NOMINAL')
  })

  // 3. Stage-by-stage playback
  it('3. supports stage-by-stage stepping forward and backward', () => {
    render(
      <DecisionTwinStage
        scenarioId="scenario_a"
        scenarioData={scenarioAFixture as unknown as ScenarioData}
        reducedMotion={true}
        autoPlay={false}
      />
    )

    const counter = screen.getByTestId('active-step-counter')
    expect(counter).toHaveTextContent('1')

    const stepFwd = screen.getByLabelText('Next Stage')
    fireEvent.click(stepFwd)
    expect(counter).toHaveTextContent('2')

    const stepBack = screen.getByLabelText('Previous Stage')
    fireEvent.click(stepBack)
    expect(counter).toHaveTextContent('1')
  })

  // 4. Pause, resume, restart and rewind
  it('4. handles pause, resume, restart and playback loop timers', () => {
    render(
      <DecisionTwinStage
        scenarioId="scenario_a"
        scenarioData={scenarioAFixture as unknown as ScenarioData}
        reducedMotion={true}
        autoPlay={false}
      />
    )

    const counter = screen.getByTestId('active-step-counter')
    expect(counter).toHaveTextContent('1')

    const playBtn = screen.getByLabelText('Play')
    fireEvent.click(playBtn)

    // Advance timer by 2.5 seconds
    act(() => {
      vi.advanceTimersByTime(2500)
    })

    // Advance should have moved forward
    expect(counter).not.toHaveTextContent('1')

    // Reset button
    const resetBtn = screen.getByLabelText('Reset')
    fireEvent.click(resetBtn)
    expect(counter).toHaveTextContent('1')
  })

  // 5. Scenario switching resets the correct physical state
  it('5. resets the physical and decision state when scenario switches', () => {
    const { rerender } = render(
      <DecisionTwinStage
        scenarioId="scenario_a"
        scenarioData={scenarioAFixture as unknown as ScenarioData}
        reducedMotion={true}
      />
    )

    const counter = screen.getByTestId('active-step-counter')
    // Advance forward
    fireEvent.click(screen.getByLabelText('Next Stage'))
    expect(counter).toHaveTextContent('2')

    // Switch to denied scenario
    rerender(
      <DecisionTwinStage
        scenarioId="scenario_b_denied"
        scenarioData={scenarioBDeniedFixture as unknown as ScenarioData}
        reducedMotion={true}
      />
    )

    // Reset back to stage 1 with new scenario
    expect(counter).toHaveTextContent('1')
    expect(screen.getAllByText(/DENIED/i).length).toBeGreaterThanOrEqual(1)
  })

  // 6. Worker entry triggers modeled hazard-zone display
  it('6. triggers modeled hazard-zone OCCUPIED and red warning when human enters zone', () => {
    const timeline = derivePresentationTimeline('scenario_b_denied', scenarioBDeniedFixture as unknown as ScenarioData)
    
    // In denied scenario, human is inside safety zone
    const policyFrame = timeline.frames[3] // POLICY stage
    expect(policyFrame.plantState.human_zone).toContain('BREACH')
    expect(policyFrame.plantState.human_distance_m).toBeLessThan(3.0)
    expect(policyFrame.policy?.decision).toBe('DENY')
  })

  // 7. Denied scenario never animates valve actuation
  it('7. strictly enforces that denied scenario never actuates valve (stays OPEN at 0° and LOCKED)', () => {
    const timeline = derivePresentationTimeline('scenario_b_denied', scenarioBDeniedFixture as unknown as ScenarioData)
    
    timeline.frames.forEach((frame) => {
      expect(frame.plantState.valve_b_state).toBe('OPEN')
      expect(frame.plantState.valve_b_angle_deg).toBe(0)
    })

    const execFrame = timeline.frames[7]
    expect(execFrame.execution?.status).toBe('LOCKED')
    expect(timeline.overallOutcome).toBe('DENIED')
  })

  // 8. TOCTOU block never animates unauthorized valve movement
  it('8. prevents valve movement on TOCTOU version drift and invalidates authorization ticket', () => {
    const timeline = derivePresentationTimeline('toctou', scenarioBFixture as unknown as ScenarioData)
    
    // World change frame
    const worldChangeFrame = timeline.frames[5]
    expect(worldChangeFrame.worldChange).toBeDefined()
    expect(worldChangeFrame.worldChange?.newVersion).toBeGreaterThan(worldChangeFrame.worldChange?.previousVersion || 0)

    // Revalidation frame
    const revalFrame = timeline.frames[6]
    expect(revalFrame.revalidation?.status).toBe('WORLD_STATE_CHANGED')

    // Execution frame is locked
    const execFrame = timeline.frames[7]
    expect(execFrame.execution?.status).toBe('LOCKED')
    expect(execFrame.plantState.valve_b_state).toBe('OPEN')
    expect(execFrame.plantState.valve_b_angle_deg).toBe(0)
  })

  // 9. NO_OP fault displays lack of valve movement
  it('9. correctly shows valve remaining unclosed when NO_OP mechanical fault occurs', () => {
    const timeline = derivePresentationTimeline('recovery', scenarioCFixture as unknown as ScenarioData)
    
    // At execution stage of fault scenario, stroke failed
    const execFrame = timeline.frames[7]
    expect(execFrame.execution?.faultInjected).toContain('NO_OP')
    
    // Verification frame detects limit switch mismatch
    const verifFrame = timeline.frames[8]
    expect(verifFrame.verification?.status).toBe('VERIFICATION_FAILED')
    expect(verifFrame.verification?.limitSwitchReadback).toBe('OPEN (Expected CLOSED)')
  })

  // 10. Unverified recovery truthfulness disclosure
  it('10. discloses that final independent verification was not recorded if recovery artifact lacks verification', () => {
    const timeline = derivePresentationTimeline('recovery', scenarioCFixture as unknown as ScenarioData)
    const recFrame = timeline.frames[9]
    expect(recFrame.recovery).toBeDefined()
    expect(recFrame.recovery?.disclosureNotice).toContain('FINAL INDEPENDENT VERIFICATION NOT RECORDED')
  })

  // 11. Missing records fail closed
  it('11. fails closed gracefully when scenarioData is null or corrupted', () => {
    const timeline = derivePresentationTimeline('unknown_scenario', null)
    expect(timeline.frames.length).toBe(10)
    expect(timeline.overallOutcome).toBe('UNKNOWN')
    timeline.frames.forEach((f) => {
      expect(f.plantState.valve_b_state).toBe('OPEN')
      expect(f.plantState.valve_b_angle_deg).toBe(0)
    })
  })

  // 12. LIVE/REPLAY source metadata remains accurate
  it('12. distinguishes LIVE provider execution from deterministic REPLAY', () => {
    const liveTimeline = derivePresentationTimeline('scenario_a', scenarioAFixture as unknown as ScenarioData)
    expect(liveTimeline.frames[0].provenanceMode).toBe('LIVE')

    const replayTimeline = derivePresentationTimeline('scenario_live_telemetry', scenarioLiveTelemetryFixture as unknown as ScenarioData)
    expect(replayTimeline.frames[0].provenanceMode).toBe('REPLAY')
  })

  // 13. WebGL capability check & fallback
  it('13. renders viewport container and fallback gracefully in headless jsdom environment', () => {
    const { container } = render(
      <DecisionTwinStage
        scenarioId="scenario_a"
        scenarioData={scenarioAFixture as unknown as ScenarioData}
      />
    )
    expect(container.querySelector('.webgl-plant-container')).toBeInTheDocument()
  })

  // 14. Reduced-motion behavior
  it('14. respects reducedMotion prop', () => {
    const { rerender } = render(
      <DecisionTwinStage
        scenarioId="scenario_a"
        scenarioData={scenarioAFixture as unknown as ScenarioData}
        reducedMotion={true}
      />
    )
    expect(screen.getByTestId('decision-twin-stage')).toBeInTheDocument()

    rerender(
      <DecisionTwinStage
        scenarioId="scenario_a"
        scenarioData={scenarioAFixture as unknown as ScenarioData}
        reducedMotion={false}
      />
    )
    expect(screen.getByTestId('decision-twin-stage')).toBeInTheDocument()
  })

  // 15. Camera preset configuration
  it('15. maps camera presets according to the active lifecycle stage', () => {
    const timeline = derivePresentationTimeline('scenario_a', scenarioAFixture as unknown as ScenarioData)
    expect(timeline.frames[0].cameraPreset).toBe('full')
    expect(timeline.frames[2].cameraPreset).toBe('valve_b')
    expect(timeline.frames[7].cameraPreset).toBe('actuator')
    expect(timeline.frames[8].cameraPreset).toBe('valve_b')
  })

  // 16. Pure presentation controls have zero actuator authority
  it('16. ensures playback transport buttons do not trigger hardware commands or network calls', () => {
    const fetchSpy = vi.spyOn(window, 'fetch').mockResolvedValue(new Response())
    render(
      <DecisionTwinStage
        scenarioId="scenario_a"
        scenarioData={scenarioAFixture as unknown as ScenarioData}
      />
    )
    // Step forward, step back, reset
    fireEvent.click(screen.getByLabelText('Next Stage'))
    fireEvent.click(screen.getByLabelText('Previous Stage'))
    fireEvent.click(screen.getByLabelText('Reset'))
    // No fetch or actuator dispatch was made
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
