import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import {
  DemoDirector,
  deriveExecutionOutcome,
} from '../components/Director/DemoDirector'
import { derivePresentationTimeline } from '../services/frameDerivation'
import { api } from '../services/api'
import { ScenarioData } from '../types'
import safe from '../data/scenario_live_safe.json'
import denied from '../data/scenario_live_denied.json'
import recovery from '../data/scenario_live_recovery.json'

vi.mock('../components/DigitalTwin/WebGLIndustrialPlant', () => ({
  WebGLIndustrialPlant: () => <div />,
}))
const clone = (value: unknown): any => structuredClone(value)
const timeline = (record: unknown) =>
  derivePresentationTimeline('safe', record as ScenarioData)
const cases = [
  {
    name: 'missing valve postcondition',
    mutate: (r: any) => {
      delete r.verification_result.expected_postconditions['valves.valve_b']
      delete r.verification_result.observed_postconditions['valves.valve_b']
    },
  },
  {
    name: 'cooling-only proof',
    mutate: (r: any) => {
      r.verification_result.expected_postconditions = { cooling: 'ACTIVE' }
      r.verification_result.observed_postconditions = { cooling: 'ACTIVE' }
    },
  },
  {
    name: 'unsupported null-only proof',
    mutate: (r: any) => {
      r.verification_result.expected_postconditions = { 'invented.field': null }
      r.verification_result.observed_postconditions = { 'invented.field': null }
    },
  },
  {
    name: 'unknown null path added to otherwise valid proof',
    mutate: (r: any) => {
      r.verification_result.expected_postconditions['invented.field'] = null
      r.verification_result.observed_postconditions['invented.field'] = null
    },
  },
  {
    name: 'wrong target',
    mutate: (r: any) => {
      r.verification_result.target = 'valve_a'
    },
  },
  {
    name: 'contradictory final world',
    mutate: (r: any) => {
      r.post_state.valves.valve_b = 'OPEN'
    },
  },
  {
    name: 'stale verification',
    mutate: (r: any) => {
      r.verification_result.timestamp = r.execution_result.timestamp - 1
    },
  },
  {
    name: 'missing chronology',
    mutate: (r: any) => {
      delete r.verification_result.timestamp
    },
  },
  {
    name: 'insufficient action evidence',
    mutate: (r: any) => {
      delete r.verification_result.action_occurred
    },
  },
  {
    name: 'missing observed valve',
    mutate: (r: any) => {
      delete r.verification_result.observed_postconditions['valves.valve_b']
    },
  },
  {
    name: 'missing cooling invariant',
    mutate: (r: any) => {
      delete r.verification_result.expected_postconditions.cooling
      delete r.verification_result.observed_postconditions.cooling
    },
  },
  {
    name: 'missing applicable leak invariant',
    mutate: (r: any) => {
      delete r.verification_result.expected_postconditions['leak.active']
      delete r.verification_result.observed_postconditions['leak.active']
    },
  },
]

describe('P1 verification status and action-specific evidence contract', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(api, 'getHealth').mockResolvedValue({
      execution_modes: ['REPLAY'],
    } as any)
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  async function showVerification(record: any) {
    vi.spyOn(api, 'triggerControlledDemo').mockResolvedValue({
      execution_id: 'exec_p1',
      execution_mode: 'REPLAY',
    } as any)
    vi.spyOn(api, 'getDemoExecution').mockResolvedValue({
      status: 'COMPLETED',
      execution_mode: 'REPLAY',
      stage_outcome: 'NOMINAL',
      record,
    } as any)
    render(
      <DemoDirector
        scenarios={[]}
        onExitDirector={vi.fn()}
        reducedMotion
        onToggleReducedMotion={vi.fn()}
        assuranceReport={null}
      />
    )
    fireEvent.click(screen.getByTestId('timeline-step-safe'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
    })
    fireEvent.click(screen.getByTestId('stage-item-verification'))
  }

  it.each(cases)(
    'recorded VERIFIED with $name stays UNVERIFIED everywhere',
    async ({ mutate }) => {
      const record = clone(safe)
      mutate(record)
      expect(record.verification_result.status).toBe('VERIFIED')
      await showVerification(record)
      const frame = timeline(record).frames[8]
      expect(frame.stageStatus).toBe('UNVERIFIED')
      expect(frame.verification?.status).toBe('UNVERIFIED')
      expect(frame.verification?.isVerified).toBe(false)
      expect(frame.outcome).toBe('UNVERIFIED')
      expect(timeline(record).overallOutcome).toBe('UNVERIFIED')
      expect(deriveExecutionOutcome(record)).toBe('UNVERIFIED')
      expect(
        screen
          .getByTestId('stage-item-verification')
          .querySelector('.stage-pill')
      ).toHaveTextContent(/^UNVERIFIED$/)
      expect(
        screen
          .getByTestId('stage-expanded-content')
          .querySelector('.verif-badge')
      ).toHaveTextContent(/^UNVERIFIED$/)
      expect(screen.getByTestId('director-status-badge')).toHaveTextContent(
        'STATUS: UNVERIFIED'
      )
      expect(screen.getByTestId('narration-text')).toHaveTextContent(
        'Verification UNVERIFIED'
      )
      expect(screen.queryByText('NOMINAL')).not.toBeInTheDocument()
    }
  )

  it.each(['explicit failure', 'contradictory readback'])(
    '%s produces VERIFICATION_FAILED in the card and Director',
    async (kind) => {
      const record = clone(safe)
      if (kind === 'explicit failure')
        record.verification_result.status = 'VERIFICATION_FAILED'
      else
        record.verification_result.observed_postconditions['valves.valve_b'] =
          'OPEN'
      await showVerification(record)
      expect(timeline(record).frames[8].stageStatus).toBe('FAILED')
      expect(
        screen
          .getByTestId('stage-expanded-content')
          .querySelector('.verif-badge')
      ).toHaveTextContent(/^VERIFICATION_FAILED$/)
      expect(screen.getByTestId('director-status-badge')).toHaveTextContent(
        'STATUS: VERIFICATION_FAILED'
      )
      expect(screen.getByTestId('narration-text')).toHaveTextContent(
        'Verification VERIFICATION_FAILED'
      )
    }
  )

  it('fully correlated valve closure is VERIFIED on every surface', async () => {
    await showVerification(clone(safe))
    expect(timeline(safe).frames[8].verification?.status).toBe('VERIFIED')
    expect(
      screen.getByTestId('stage-item-verification').querySelector('.stage-pill')
    ).toHaveTextContent(/^PASSED$/)
    expect(
      screen.getByTestId('stage-expanded-content').querySelector('.verif-badge')
    ).toHaveTextContent(/^VERIFIED$/)
    expect(screen.getByTestId('director-status-badge')).toHaveTextContent(
      'STATUS: VERIFIED'
    )
    expect(timeline(safe).overallOutcome).toBe('NOMINAL')
  })

  it('distinguishes NOT_RECORDED after execution from NOT_REACHED after rejection', async () => {
    const record = { ...clone(safe), verification_result: null }
    await showVerification(record)
    expect(
      screen.getByTestId('stage-expanded-content').querySelector('.verif-badge')
    ).toHaveTextContent(/^NOT_RECORDED$/)
    expect(timeline(denied).frames[8].verification?.status).toBe('NOT_REACHED')
    expect(timeline(denied).frames[8].stageStatus).toBe('NOT_APPLICABLE')
  })

  it('validates additional custom paths, including structured values and a recorded null', () => {
    const record = clone(safe)
    record.post_state.external_observations.custom = {
      constructor: 'OEM',
      nullable: null,
      values: [1, true],
    }
    for (const [path, value] of Object.entries({
      'observations.pressure_main.reading.pressure_psi':
        record.post_state.observations.pressure_main.reading.pressure_psi,
      'external_observations.custom':
        record.post_state.external_observations.custom,
      'external_observations.custom.nullable': null,
      'external_observations.custom.constructor': 'OEM',
    })) {
      record.verification_result.expected_postconditions[path] = clone(value)
      record.verification_result.observed_postconditions[path] = clone(value)
    }
    expect(timeline(record).overallOutcome).toBe('NOMINAL')
    record.verification_result.observed_postconditions[
      'external_observations.custom'
    ] = { nullable: null, values: [2, true] }
    expect(timeline(record).overallOutcome).not.toBe('NOMINAL')
  })

  it('requires OPEN_VALVE to verify the actual target as OPEN', () => {
    const record = clone(safe)
    record.decision_record.action_proposal.action_type = 'OPEN_VALVE'
    record.ticket.action_type = 'OPEN_VALVE'
    record.execution_result.requested_action = 'OPEN_VALVE'
    record.pre_state.valves.valve_b = 'CLOSED'
    record.post_state.valves.valve_b = 'OPEN'
    record.execution_result.observed_state.valves.valve_b = 'OPEN'
    record.verification_result.expected_postconditions['valves.valve_b'] =
      'OPEN'
    record.verification_result.observed_postconditions['valves.valve_b'] =
      'OPEN'
    record.digital_twin_snapshots = []
    expect(timeline(record).overallOutcome).toBe('NOMINAL')
    record.verification_result.expected_postconditions['valves.valve_b'] =
      'CLOSED'
    record.verification_result.observed_postconditions['valves.valve_b'] =
      'CLOSED'
    expect(timeline(record).overallOutcome).not.toBe('NOMINAL')
  })

  it('recovery final verification cannot use an unrelated matching field', () => {
    const record = clone(recovery)
    record.recovery_result.fresh_ticket = {
      ...safe.ticket,
      issued_at: record.verification_result.timestamp + 0.1,
      expires_at: record.verification_result.timestamp + 30,
    }
    record.recovery_result.retry_execution_result = {
      ...safe.execution_result,
      timestamp: record.verification_result.timestamp + 0.2,
    }
    record.recovery_result.retry_verification_result = {
      ...clone(safe.verification_result),
      timestamp: record.verification_result.timestamp + 1,
    }
    expect(timeline(record).overallOutcome).toBe('RECOVERED')
    record.recovery_result.retry_verification_result.expected_postconditions = {
      cooling: 'ACTIVE',
    }
    record.recovery_result.retry_verification_result.observed_postconditions = {
      cooling: 'ACTIVE',
    }
    expect(timeline(record).overallOutcome).toBe('UNVERIFIED')
    expect(timeline(record).frames[9].recovery?.isPostRecoveryVerified).toBe(
      false
    )
    expect(deriveExecutionOutcome(record)).toBe('UNVERIFIED')
  })
  it('does not borrow a VERIFIED actuator label from an insufficient recovery snapshot', async () => {
    const record = clone(recovery)
    record.digital_twin_snapshots[3].actuator_status = 'VERIFIED'
    record.recovery_result.fresh_ticket = {
      ...safe.ticket,
      issued_at: record.verification_result.timestamp + 0.1,
      expires_at: record.verification_result.timestamp + 30,
    }
    record.recovery_result.retry_execution_result = {
      ...safe.execution_result,
      timestamp: record.verification_result.timestamp + 0.2,
    }
    record.recovery_result.retry_verification_result = {
      ...clone(safe.verification_result),
      timestamp: record.verification_result.timestamp + 1,
      expected_postconditions: { cooling: 'ACTIVE' },
      observed_postconditions: { cooling: 'ACTIVE' },
    }
    await showVerification(record)
    fireEvent.click(screen.getByTestId('stage-item-recovery'))
    const frame = timeline(record).frames[9]
    expect(frame.plantState.valve_b_state).toBe('CLOSED')
    expect(frame.plantState.actuator_status).not.toBe('VERIFIED')
    expect(frame.stageStatus).toBe('UNVERIFIED')
    expect(frame.recovery?.finalVerification).toBe('UNVERIFIED')
    expect(screen.getByTestId('director-status-badge')).toHaveTextContent(
      'STATUS: UNVERIFIED'
    )
  })
})
