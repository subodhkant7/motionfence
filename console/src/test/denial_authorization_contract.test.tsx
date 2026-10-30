import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import {
  DemoDirector,
  deriveExecutionOutcome,
} from '../components/Director/DemoDirector'
import { DecisionTwinStage } from '../components/Stage/DecisionTwinStage'
import {
  derivePresentationTimeline,
  displayedStageStatus,
} from '../services/frameDerivation'
import { api } from '../services/api'
import { ScenarioData } from '../types'
import safe from '../data/scenario_live_safe.json'
import denied from '../data/scenario_live_denied.json'
import toctou from '../data/scenario_live_toctou.json'

const { plantRender } = vi.hoisted(() => ({ plantRender: vi.fn() }))
vi.mock('../components/DigitalTwin/WebGLIndustrialPlant', () => ({
  WebGLIndustrialPlant: (props: unknown) => {
    plantRender(props)
    return <div />
  },
}))
const clone = (value: unknown): any => structuredClone(value)
const timeline = (value: unknown) =>
  derivePresentationTimeline('safe', value as ScenarioData)
const jump = (key: string) =>
  fireEvent.click(screen.getByTestId(`stage-item-${key}`))
const proposalId = (record: any) =>
  (record.proposal ?? record.decision_record.action_proposal).id
const issuedTicket = (record: any) => ({
  ...clone(safe.ticket),
  proposal_id: proposalId(record),
})
const grant = (proposalId: string) => ({
  event_type: 'ENCLAVE_AUTHORIZATION_GRANTED',
  payload: { proposal_id: proposalId, ticket_id: 'recorded-issued-ticket' },
})
const contradictoryCases = [
  {
    name: 'issued ticket',
    mutate: (r: any) => {
      r.ticket = issuedTicket(r)
    },
  },
  {
    name: 'minimal ticket issuance record',
    mutate: (r: any) => {
      r.ticket = { ticket_id: 'issued-but-incomplete' }
    },
  },
  {
    name: 'initial ticket despite null primary ticket',
    mutate: (r: any) => {
      r.initial_ticket = issuedTicket(r)
    },
  },
  {
    name: 'authorization ticket alias',
    mutate: (r: any) => {
      r.authorization_ticket = issuedTicket(r)
    },
  },
  {
    name: 'correlated grant without ticket object',
    mutate: (r: any) => {
      r.events.push(grant(proposalId(r)))
    },
  },
  {
    name: 'canonical current-action issuance ID',
    mutate: (r: any) => {
      r.decision_record.authorization_ticket_id = 'canonical-issued-ticket'
    },
  },
]

describe('R2 policy DENY authorization invariant', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it.each(contradictoryCases)(
    'DENY with $name fails closed without moving the plant',
    ({ mutate }) => {
      const record = clone(denied)
      mutate(record)
      const result = timeline(record)
      expect(result.overallOutcome).toBe('ERROR')
      expect(deriveExecutionOutcome(record, 'DENIED', 'denied')).toBe('ERROR')
      expect(result.frames.slice(3).every((f) => f.outcome === 'ERROR')).toBe(
        true
      )
      expect(result.frames[4].stageStatus).toBe('FAILED')
      expect(result.frames[4].authorization?.status).toBe('ERROR')
      expect(result.frames[4].evidenceIssues).toContain(
        'Safety invariant violation: ticket issued despite policy DENY'
      )
      expect(displayedStageStatus(result.frames[4], 3)).toBe('PENDING')
      render(<DecisionTwinStage scenarioId="safe" scenarioData={record} />)
      jump('authorization')
      expect(
        screen
          .getByTestId('stage-item-authorization')
          .querySelector('.stage-pill')
      ).toHaveTextContent(/^FAILED$/)
      expect(
        screen
          .getByTestId('stage-expanded-content')
          .querySelector('.ticket-status-badge')
      ).toHaveTextContent(/^ERROR$/)
      expect(screen.getByRole('alert')).toHaveTextContent(
        'ticket issued despite policy DENY'
      )
      expect(
        screen.getByText('ERROR', { selector: '.outcome-chip' })
      ).toBeInTheDocument()
      expect(plantRender.mock.lastCall?.[0].plantState).toBe(
        record.digital_twin_snapshots[1]
      )
      jump('execution')
      expect(plantRender.mock.lastCall?.[0].plantState).toBe(
        record.digital_twin_snapshots[2]
      )
      expect(plantRender.mock.lastCall?.[0].plantState.valve_b_state).toBe(
        'OPEN'
      )
      jump('verification')
      expect(
        screen
          .getByTestId('stage-expanded-content')
          .querySelector('.verif-badge')
      ).not.toHaveTextContent(/^VERIFIED$/)
    }
  )

  it.each([
    'null ticket',
    'not invoked',
    'rejected ID',
    'historical grant',
    'unrelated canonical ID',
    'requested only',
  ])('valid denial with %s remains DENIED', (evidence) => {
    const record = clone(denied)
    if (evidence === 'not invoked') record.execution_result = null
    if (evidence === 'rejected ID')
      record.execution_result.ticket_id = 'rejected-untrusted-id'
    if (evidence === 'historical grant')
      record.events.push(grant('historical-proposal'))
    if (evidence === 'unrelated canonical ID') {
      record.proposal = clone(record.decision_record.action_proposal)
      record.decision_record.authorization_ticket_id = 'historical-ticket'
      record.decision_record.action_proposal.id = 'historical-proposal'
    }
    if (evidence === 'requested only')
      record.events.push({
        ...grant(proposalId(record)),
        event_type: 'ENCLAVE_AUTHORIZATION_REQUESTED',
      })
    expect(timeline(record).overallOutcome).toBe('DENIED')
    expect(timeline(record).frames[4].authorization?.status).toBe('NOT_ISSUED')
  })

  it.each(['actuated', 'valve mutation'])(
    'DENY with unauthorized %s becomes ERROR',
    (evidence) => {
      const record = clone(denied)
      if (evidence === 'actuated')
        record.execution_result.execution_status = 'ACTUATED'
      else record.post_state.valves.valve_b = 'CLOSED'
      expect(timeline(record).overallOutcome).toBe('ERROR')
      expect(timeline(record).frames[7].stageStatus).toBe('FAILED')
    }
  )

  it('keeps valid nominal and TOCTOU outcomes and missing authorization unverified', () => {
    expect(timeline(safe).overallOutcome).toBe('NOMINAL')
    expect(timeline(toctou).overallOutcome).toBe('BLOCKED')
    const missing = { ...clone(safe), ticket: null, initial_ticket: null }
    expect(timeline(missing).overallOutcome).toBe('UNVERIFIED')
    expect(timeline(missing).frames[8].verification?.isVerified).toBe(false)
  })

  it('gives contradictory issuance precedence over conflicting policy aliases', () => {
    const record = clone(denied)
    record.ticket = issuedTicket(record)
    record.policy_decision.is_allowed = true
    expect(timeline(record).overallOutcome).toBe('ERROR')
    record.policy_decision = { decision: 'ALLOW', is_allowed: true }
    // Canonical DENY remains authoritative despite the conflicting envelope.
    expect(timeline(record).overallOutcome).toBe('ERROR')
  })

  it('Director, active policy/authorization stages, card and issue disclosure agree', async () => {
    const record = clone(denied)
    record.ticket = issuedTicket(record)
    vi.spyOn(api, 'getHealth').mockResolvedValue({
      execution_modes: ['REPLAY'],
    } as any)
    vi.spyOn(api, 'triggerControlledDemo').mockResolvedValue({
      execution_id: 'r2-denied',
      execution_mode: 'REPLAY',
    } as any)
    vi.spyOn(api, 'getDemoExecution').mockResolvedValue({
      status: 'COMPLETED',
      execution_mode: 'REPLAY',
      stage_outcome: 'DENIED',
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
    fireEvent.click(screen.getByTestId('timeline-step-denied'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
    })
    jump('policy')
    expect(screen.getByTestId('director-status-badge')).toHaveTextContent(
      'STATUS: ERROR'
    )
    expect(
      screen.getByTestId('stage-item-policy').querySelector('.stage-pill')
    ).toHaveTextContent(/^FAILED$/)
    jump('authorization')
    expect(screen.getByTestId('director-status-badge')).toHaveTextContent(
      'STATUS: ERROR'
    )
    expect(
      screen
        .getByTestId('stage-expanded-content')
        .querySelector('.ticket-status-badge')
    ).toHaveTextContent(/^ERROR$/)
    expect(screen.getByTestId('narration-text')).toHaveTextContent(
      'ticket issued despite policy DENY'
    )
    expect(
      screen.queryByText('DENIED', { selector: '.outcome-chip' })
    ).not.toBeInTheDocument()
  })
})
