import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, within } from '@testing-library/react'
import { DecisionTwinStage } from '../components/Stage/DecisionTwinStage'
import { derivePresentationTimeline } from '../services/frameDerivation'
import { ScenarioData } from '../types'
import safe from '../data/scenario_live_safe.json'
import denied from '../data/scenario_live_denied.json'
import toctou from '../data/scenario_live_toctou.json'
import recovery from '../data/scenario_live_recovery.json'
import { withExecutionContext } from '../services/api'

const { plantRender } = vi.hoisted(() => ({ plantRender: vi.fn() }))
vi.mock('../components/DigitalTwin/WebGLIndustrialPlant', () => ({
  WebGLIndustrialPlant: (props: unknown) => { plantRender(props); return <div data-testid="supplied-model-state" /> },
}))
const clone = <T,>(value: T): T => structuredClone(value)
const data = (value: unknown) => value as ScenarioData
const timeline = (value: unknown, id = 'safe') => derivePresentationTimeline(id, data(value))
const jump = (key: string) => fireEvent.click(screen.getByTestId(`stage-item-${key}`))
const card = () => within(screen.getByTestId('stage-expanded-content'))
const lastPlant = () => plantRender.mock.lastCall?.[0].plantState
const model = (value: unknown, id = 'safe', extra = {}) => render(<DecisionTwinStage scenarioId={id} scenarioData={data(value)} {...extra} />)

describe('Phase 2Y-R1 evidence-authoritative presentation', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('1. safe scenario ID with recorded DENY renders denial and stationary source state', () => {
    model(denied, 'safe'); jump('policy')
    expect(card().getByText('DECISION: DENY')).toBeInTheDocument()
    expect(card().getAllByText(/Human detected in safety zone/)).toHaveLength(2)
    jump('execution')
    expect(card().getByText('LOCKED')).toBeInTheDocument()
    expect(lastPlant()).toBe(denied.digital_twin_snapshots[2])
    expect(lastPlant().valve_b_state).toBe('OPEN')
    expect(timeline(denied, 'safe').overallOutcome).toBe('DENIED')
  })

  it('2. denied scenario ID with recorded ALLOW renders actual approval and verified transition', () => {
    model(safe, 'denied'); jump('policy')
    expect(card().getByText('DECISION: ALLOW')).toBeInTheDocument()
    jump('verification')
    expect(card().getByText('VERIFIED')).toBeInTheDocument()
    expect(lastPlant()).toBe(safe.digital_twin_snapshots[3])
    expect(timeline(safe, 'denied').overallOutcome).toBe('NOMINAL')
  })

  it('3. TOCTOU name without recorded drift cannot invent a version/hash mismatch', () => {
    model(safe, 'toctou'); jump('world_change')
    expect(card().getByText(/No state drift event recorded/)).toBeInTheDocument()
    expect(lastPlant().world_version).toBe(3)
    expect(timeline(safe, 'toctou').frames[5].worldChange?.driftDetected).toBeUndefined()
    jump('revalidation')
    expect(card().queryByText('WORLD_STATE_CHANGED')).not.toBeInTheDocument()
  })

  it('4. absent authorization ticket cannot be reconstructed from a nominal name or nested ID', () => {
    const value = { ...safe, ticket: null, initial_ticket: null }
    model(value); jump('authorization')
    expect(card().getAllByText(/NOT_RECORDED/).length).toBeGreaterThan(0)
    expect(card().queryByText(safe.ticket.ticket_id)).not.toBeInTheDocument()
    expect(timeline(value).frames[4].stageStatus).toBe('UNVERIFIED')
    expect(timeline(value).overallOutcome).toBe('UNVERIFIED')
  })

  it('5. explicit missing verification does not resurrect a nested copy or show successful verification', () => {
    const value = { ...safe, verification_result: null }
    model(value); jump('verification')
    expect(screen.getByTestId('stage-item-verification')).toHaveTextContent('UNVERIFIED')
    expect(card().queryByText('VERIFIED')).not.toBeInTheDocument()
    expect(lastPlant().actuator_status).toBe('ACTUATED')
    expect(timeline(value).overallOutcome).toBe('UNVERIFIED')
  })

  it('6. mutation: changing only recorded verification failure changes the rendered result at the same ID', () => {
    const value = { ...clone(safe), verification_result: { ...safe.verification_result, status: 'VERIFICATION_FAILED', discrepancies: ['sensor contradiction'] } }
    const { rerender } = model(safe); jump('verification')
    expect(card().getByText('VERIFIED')).toBeInTheDocument()
    rerender(<DecisionTwinStage scenarioId="safe" scenarioData={data(value)} />)
    jump('verification')
    expect(card().getByText('VERIFICATION_FAILED')).toBeInTheDocument()
    expect(screen.getByTestId('stage-item-verification')).toHaveTextContent('FAILED')
    expect(timeline(value).overallOutcome).toBe('VERIFICATION_FAILED')
  })

  it('7. a recovery result absent from a fault record cannot become recovery success', () => {
    const value = { ...recovery, recovery_result: null }
    model(value, 'recovery'); jump('recovery')
    expect(card().getByText('NOT_RECORDED')).toBeInTheDocument()
    expect(lastPlant().valve_b_state).toBe('OPEN')
    expect(timeline(value).overallOutcome).toBe('VERIFICATION_FAILED')
  })

  it('8. reported recovery success without final verification remains explicitly UNVERIFIED', () => {
    model(recovery, 'recovery'); jump('execution')
    expect(lastPlant().valve_b_state).toBe('OPEN')
    expect(card().getByText('NO_OP')).toBeInTheDocument()
    jump('verification'); expect(card().getByText('OPEN')).toBeInTheDocument()
    jump('recovery')
    expect(card().getByText('UNVERIFIED')).toBeInTheDocument()
    expect(card().getByText(/FINAL INDEPENDENT VERIFICATION NOT RECORDED/)).toBeInTheDocument()
    expect(lastPlant()).toBe(recovery.digital_twin_snapshots[3])
    expect(timeline(recovery).overallOutcome).toBe('UNVERIFIED')
  })

  it('9. failed recovery with a closed final valve stays FAILED; physical position is not a verifier', () => {
    const value = { ...recovery, recovery_result: { ...recovery.recovery_result, outcome: 'FAILED' } }
    model(value); jump('recovery')
    expect(card().getByText('FAILED')).toBeInTheDocument()
    expect(lastPlant().valve_b_state).toBe('CLOSED')
    expect(timeline(value).overallOutcome).toBe('VERIFICATION_FAILED')
  })

  it.each(['telemetry', 'evidence'])('10. %s retrieval without hardware records cannot borrow nominal actuation snapshots', id => {
    const value = { ...safe, ticket: null, initial_ticket: null, execution_result: null, verification_result: null }
    model(value, id); jump('execution')
    expect(lastPlant().valve_b_state).toBe('OPEN')
    expect(lastPlant().world_version).toBe(3)
    expect(card().queryByText('ACTUATED')).not.toBeInTheDocument()
    expect(timeline(value, id).frames.every(f => f.plantState.valve_b_state === 'OPEN')).toBe(true)
  })

  it.each([null, {}, { decision_record: 42, events: [null, 42], digital_twin_snapshots: ['bad'] }, { pre_state: { bogus: true } }])('11. malformed source %j produces no fabricated stage success', value => {
    const tl = timeline(value)
    expect(tl.frames).toHaveLength(10)
    expect(tl.frames.every(f => f.stageStatus !== 'PASSED')).toBe(true)
    expect(tl.frames.every(f => f.plantState.valve_b_state === 'NOT_RECORDED')).toBe(true)
    model(value); jump('proposal')
    expect(card().getAllByText(/NOT_RECORDED/).length).toBeGreaterThan(0)
    expect(card().queryByText('CLOSE_VALVE')).not.toBeInTheDocument()
  })

  it('12. historical LIVE metadata remains historical while current session is REPLAY', () => {
    const value = withExecutionContext(data(safe))
    model(value)
    expect(screen.getByText('REPLAY (OFFLINE FIXTURE)')).toBeInTheDocument()
    expect(screen.getByTestId('plant-source')).toHaveTextContent('RECORDED NEMOTRON INFERENCE')
    expect(screen.getByTestId('plant-source')).toHaveTextContent('LIVE_MODEL_RESPONSE')
    expect(screen.queryByText('LIVE SESSION')).not.toBeInTheDocument()
    expect(value.execution_mode).toBe('LIVE')
    expect(timeline(value).frames[0].provenanceMode).toBe('REPLAY')
    expect(derivePresentationTimeline('safe', value, 'LIVE').frames[0].provenanceMode).toBe('LIVE')
  })

  it('13. rewind/scrub selects exact recorded states in both directions', () => {
    model(toctou)
    expect(lastPlant()).toBe(toctou.digital_twin_snapshots[0])
    jump('world_change'); expect(lastPlant()).toBe(toctou.digital_twin_snapshots[2])
    jump('authorization'); expect(lastPlant()).toBe(toctou.digital_twin_snapshots[1])
    expect(lastPlant().human_zone).toBe('CLEAR')
    jump('revalidation'); expect(lastPlant()).toBe(toctou.digital_twin_snapshots[3])
    expect(lastPlant().valve_b_state).toBe('OPEN')
  })

  it('14. switching scenarios synchronously resets cursor and supplied model state', () => {
    const { rerender } = model(safe); jump('verification')
    expect(lastPlant().valve_b_state).toBe('CLOSED')
    rerender(<DecisionTwinStage scenarioId="denied" scenarioData={data(denied)} />)
    expect(screen.getByTestId('active-step-counter')).toHaveTextContent('1')
    expect(lastPlant()).toBe(denied.digital_twin_snapshots[0])
    expect(screen.getByTestId('stage-item-verification')).toHaveTextContent('PENDING')
  })

  it('15. future stages and overall success stay pending/unverified until playback reaches evidence', () => {
    model(safe, 'safe', { autoPlay: true })
    expect(screen.getByTestId('stage-item-policy')).toHaveTextContent('PENDING')
    expect(screen.queryByText('NOMINAL')).not.toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1900 * 3))
    expect(screen.getByTestId('stage-item-policy')).toHaveTextContent('PASSED')
    expect(screen.getByTestId('stage-item-verification')).toHaveTextContent('PENDING')
    act(() => vi.advanceTimersByTime(1900 * 5))
    expect(screen.getByText('NOMINAL')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Reset'))
    expect(screen.getByTestId('stage-item-verification')).toHaveTextContent('PENDING')
    expect(screen.queryByText('NOMINAL')).not.toBeInTheDocument()
  })

  it('16. renderer and left evidence rail share the exact actual source snapshot and path', () => {
    model(safe); jump('execution')
    const frame = timeline(safe).frames[7]
    expect(lastPlant()).toBe(safe.digital_twin_snapshots[2])
    expect(lastPlant()).toBe(frame.plantState)
    expect(card().getByText(/Source:/)).toHaveTextContent(frame.sourceSnapshotPath)
    expect(screen.getByTestId('plant-source')).toHaveTextContent('Valve B: CLOSED')
    expect(card().getByText('ACTUATED')).toBeInTheDocument()
  })

  it('mutation: changes policy and rationale at a fixed scenario ID without route-derived safety claims', () => {
    const value = { ...denied, policy_decision: { decision: 'ALLOW', reasons: ['recorded alternate policy'] }, ticket: null }
    model(value, 'denied'); jump('policy')
    expect(card().getByText('DECISION: ALLOW')).toBeInTheDocument()
    expect(card().getByText('recorded alternate policy')).toBeInTheDocument()
    expect(timeline(value, 'denied').overallOutcome).not.toBe('DENIED')
  })

  it('mutation: sensor and state values come from the actual selected snapshot', () => {
    const value = clone(safe); value.digital_twin_snapshots[0].pressure_psi = 73.25
    model(value)
    expect(lastPlant().pressure_psi).toBe(73.25)
    expect(lastPlant().valve_b_angle_deg).toBeUndefined()
    expect(timeline(value).frames[2].proposal?.confidence).toBe(safe.decision_record.action_proposal.model_confidence)
    expect(timeline(value).frames[2].proposal?.rawProposalHash).toBeUndefined()
  })

  it('rejects self-contradictory VERIFIED reports and expired execution tickets', () => {
    const value = clone(safe)
    value.verification_result.observed_postconditions['valves.valve_b'] = 'OPEN'
    expect(timeline(value).frames[8].stageStatus).toBe('FAILED')
    const expired = clone(safe); expired.ticket.expires_at = expired.ticket.issued_at
    expect(timeline(expired).overallOutcome).toBe('UNVERIFIED')
  })

  it('mutation: contradictory policy and physical snapshots cannot produce a successful display', () => {
    const value = clone(safe)
    value.policy_decision.reasons[0].status = 'failed'
    expect(timeline(value).overallOutcome).toBe('UNVERIFIED')
    const broken = clone(safe)
    broken.digital_twin_snapshots[2].valve_b_state = 'OPEN'
    model(broken); jump('verification')
    expect(timeline(broken).overallOutcome).toBe('UNVERIFIED')
    expect(lastPlant().actuator_status).not.toBe('VERIFIED')
    expect(card().getByRole('alert')).toHaveTextContent('Physical snapshot')
  })

  it('mutation: uncorrelated or premature verification cannot produce success', () => {
    const value = clone(safe)
    value.verification_result.timestamp = value.execution_result.timestamp - 1
    expect(timeline(value).overallOutcome).toBe('UNVERIFIED')
    value.verification_result.timestamp = safe.verification_result.timestamp
    value.verification_result.action_id = 'different-action'
    expect(timeline(value).overallOutcome).toBe('UNVERIFIED')
  })

  it('playback controls have no network or actuator authority', () => {
    const fetch = vi.spyOn(globalThis, 'fetch')
    model(safe); jump('execution'); fireEvent.click(screen.getByLabelText('Previous Stage')); fireEvent.click(screen.getByLabelText('Reset'))
    expect(fetch).not.toHaveBeenCalled()
  })
})
