import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { Header } from '../components/Header'
import { DecisionReplay } from '../components/DecisionReplay/DecisionReplay'
import { EvidenceInspector } from '../components/DecisionReplay/EvidenceInspector'
import { PolicyDecisionPanel } from '../components/DecisionReplay/PolicyDecisionPanel'
import { AuthorizationTicketCard } from '../components/DecisionReplay/AuthorizationTicketCard'
import { RevalidationBarriers } from '../components/DecisionReplay/RevalidationBarriers'
import { VerificationPanel } from '../components/DecisionReplay/VerificationPanel'
import { RecoveryPanel } from '../components/DecisionReplay/RecoveryPanel'
import { PolicyFirewall } from '../components/PolicyFirewall/PolicyFirewall'
import { TrajectoryViewer } from '../components/Trajectories/TrajectoryViewer'
import { AssurancePanel } from '../components/Assurance/AssurancePanel'

import scenarioAFixture from '../data/scenario_a.json'
import scenarioBFixture from '../data/scenario_b.json'
import scenarioCFixture from '../data/scenario_c.json'
import firewallFixture from '../data/firewall_report.json'
import repairsFixture from '../data/repair_proposals.json'
import trajectoriesFixture from '../data/trajectories.json'
import assuranceFixture from '../data/assurance_properties.json'
import { ScenarioData, ScenarioMeta } from '../types'

const mockScenarios: ScenarioMeta[] = [
  { id: 'scenario_a', title: 'A. Safe Execution (Nominal)', subtitle: 'Normal flow', flow: 'ALLOW', category: 'NOMINAL' },
  { id: 'scenario_b', title: 'B. TOCTOU Revalidation Block', subtitle: 'Human zone race', flow: 'BLOCKED', category: 'TOCTOU_DEFENSE' },
  { id: 'scenario_c', title: 'C. Actuator Failure & Recovery', subtitle: 'Stroke mismatch', flow: 'RECOVERED', category: 'FAULT_RECOVERY' },
]

describe('1. Header & Navigation', () => {
  it('renders MotionFence branding and zero-authority security badge', () => {
    const onToggle = vi.fn()
    const onViewChange = vi.fn()
    render(
      <Header
        currentView="replay"
        onViewChange={onViewChange}
        isLive={false}
        reducedMotion={false}
        onToggleReducedMotion={onToggle}
      />
    )

    expect(screen.getByText('MotionFence Judge Console')).toBeInTheDocument()
    expect(screen.getByText(/READ-ONLY \/ ZERO AUTHORITY/i)).toBeInTheDocument()
    expect(screen.getByText(/OFFLINE DETERMINISTIC REPLAY/i)).toBeInTheDocument()
  })

  it('handles navigation tab changes and reduced motion toggle', () => {
    const onToggle = vi.fn()
    const onViewChange = vi.fn()
    render(
      <Header
        currentView="replay"
        onViewChange={onViewChange}
        isLive={true}
        reducedMotion={false}
        onToggleReducedMotion={onToggle}
      />
    )

    fireEvent.click(screen.getByText('Policy Firewall'))
    expect(onViewChange).toHaveBeenCalledWith('firewall')

    fireEvent.click(screen.getByText(/Motion: Standard/i))
    expect(onToggle).toHaveBeenCalled()
  })
})

describe('2. Decision Replay Lifecycle & Stages', () => {
  it('renders all 10 chronological stages in timeline for Scenario A', () => {
    render(
      <DecisionReplay
        scenarios={mockScenarios}
        selectedScenarioId="scenario_a"
        onSelectScenario={vi.fn()}
        scenarioData={scenarioAFixture as unknown as ScenarioData}
        reducedMotion={true}
      />
    )

    expect(screen.getByText('1. OBSERVE')).toBeInTheDocument()
    expect(screen.getByText('2. EVIDENCE')).toBeInTheDocument()
    expect(screen.getByText('3. PROPOSAL')).toBeInTheDocument()
    expect(screen.getByText('4. POLICY')).toBeInTheDocument()
    expect(screen.getByText('5. AUTHORIZE')).toBeInTheDocument()
    expect(screen.getByText('6. WORLD CHANGE')).toBeInTheDocument()
    expect(screen.getByText('7. REVALIDATE')).toBeInTheDocument()
    expect(screen.getByText('8. EXECUTE')).toBeInTheDocument()
    expect(screen.getByText('9. VERIFY')).toBeInTheDocument()
    expect(screen.getByText('10. RECOVER')).toBeInTheDocument()
  })

  it('navigates through steps using step forward and backward controls', () => {
    render(
      <DecisionReplay
        scenarios={mockScenarios}
        selectedScenarioId="scenario_a"
        onSelectScenario={vi.fn()}
        scenarioData={scenarioAFixture as unknown as ScenarioData}
        reducedMotion={true}
      />
    )

    expect(screen.getByText('Stage 1 of 10')).toBeInTheDocument()
    const forwardBtn = screen.getByTitle('Step Forward')
    fireEvent.click(forwardBtn)
    expect(screen.getByText('Stage 2 of 10')).toBeInTheDocument()
  })
})

describe('3. Evidence Inspector Distinction Principle', () => {
  it('displays the core 4-level distinction chain', () => {
    render(<EvidenceInspector evidenceList={[]} />)

    expect(screen.getByText('SOURCE EXISTS')).toBeInTheDocument()
    expect(screen.getByText('SOURCE TRUSTWORTHY')).toBeInTheDocument()
    expect(screen.getByText('CLAIM SUPPORTED')).toBeInTheDocument()
    expect(screen.getByText('AUTHORIZATION SUFFICIENT')).toBeInTheDocument()
  })
})

describe('4. Policy Decision Panel', () => {
  it('renders deterministic policy factors without external execution', () => {
    const sc = scenarioAFixture as unknown as ScenarioData
    render(
      <PolicyDecisionPanel
        decisionRecord={sc.decision_record}
        worldState={sc.decision_record.world_state_snapshot}
      />
    )

    expect(screen.getAllByText('ALLOW').length).toBeGreaterThan(0)
    expect(screen.getByText('Human Safety Zone')).toBeInTheDocument()
    expect(screen.getByText('Cooling Invariant')).toBeInTheDocument()
    expect(screen.getByText('Confidence Floor')).toBeInTheDocument()
  })
})

describe('5. Authorization Ticket Card & Invalidation', () => {
  it('renders ticket details and invalidation state', () => {
    const ticket = {
      ticket_id: 'AT_7b19a08e1c4b',
      action_type: 'CLOSE_VALVE',
      target: 'valve_b',
      issued_at: 1000,
      expires_at: 1010,
      world_state_version: 1,
      world_state_hash: '9f83ac027b14d89a26ce4018274a1c5d9843bf029e',
      policy_version: '1.0.0',
      constraint_set_hash: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e464',
      evidence_context_hash: '7c4091a1820b411d95447a06c28f11b238e9a263d',
      nonce: 'n_a07b81c2',
    }

    const { rerender } = render(
      <AuthorizationTicketCard
        ticket={ticket}
        isInvalidated={false}
        currentStage={4}
        reducedMotion={true}
      />
    )

    expect(screen.getByText('AT_7b19a08e1c4b')).toBeInTheDocument()
    expect(screen.getByText('VALID (SINGLE-USE)')).toBeInTheDocument()

    // Test transition to INVALIDATED
    rerender(
      <AuthorizationTicketCard
        ticket={ticket}
        isInvalidated={true}
        invalidationReason="World State Version Drift"
        currentStage={6}
        reducedMotion={true}
      />
    )

    expect(screen.getByText('INVALIDATED')).toBeInTheDocument()
    expect(screen.getByText(/World State Version Drift/i)).toBeInTheDocument()
  })
})

describe('6. Revalidation TOCTOU Defense (Scenario B)', () => {
  it('shows all 9 barriers passed for nominal and blocked for drift', () => {
    const { rerender } = render(
      <RevalidationBarriers isBlocked={false} failedBarrier="" status="VALID" />
    )
    expect(screen.getByText('ALL BARRIERS PASSED')).toBeInTheDocument()

    rerender(
      <RevalidationBarriers isBlocked={true} failedBarrier="world version" status="WORLD_STATE_CHANGED" />
    )
    expect(screen.getByText('BLOCKED BEFORE EXECUTION')).toBeInTheDocument()
    expect(screen.getByText(/Actuator was NEVER reached/i)).toBeInTheDocument()
  })
})

describe('7. Verification & Autonomous Recovery (Scenario C)', () => {
  it('displays commanded vs observed state mismatch on mechanical failure', () => {
    const sc = scenarioCFixture as any
    render(
      <VerificationPanel
        executionResult={sc.failed_execution || sc.execution_result}
        verificationResult={sc.failed_verification || sc.verification_result}
        isBlockedBeforeExecution={false}
      />
    )

    expect(screen.getByText('VALVE_B = CLOSED')).toBeInTheDocument()
    expect(screen.getByText('VALVE_B = OPEN')).toBeInTheDocument()
  })

  it('renders recovery sequence and proves fresh authorization is required', () => {
    const sc = scenarioCFixture as unknown as ScenarioData
    render(<RecoveryPanel scenarioData={sc} />)

    expect(screen.getByText(/Autonomous Fault Containment/i)).toBeInTheDocument()
    expect(screen.getByText('1. FAILURE')).toBeInTheDocument()
    expect(screen.getByText('3. CONTAIN')).toBeInTheDocument()
    expect(screen.getByText('5. REAUTHORIZE')).toBeInTheDocument()
    expect(screen.getByText(/NO STALE TOKEN REUSE/i)).toBeInTheDocument()
  })
})

describe('8. Policy Mutation Firewall & Categories (Phase 2J/2K)', () => {
  it('displays exact metric categories without collapsing into a single score', () => {
    render(
      <PolicyFirewall
        report={firewallFixture as any}
        repairs={repairsFixture as any}
        reducedMotion={true}
      />
    )

    expect(screen.getByText('Safety Mutations')).toBeInTheDocument()
    expect(screen.getByText('Compound Attacks')).toBeInTheDocument()
    expect(screen.getByText('Dynamic Trajectories')).toBeInTheDocument()
    expect(screen.getByText('Detected Regressions')).toBeInTheDocument()
    expect(screen.getByText('Repair Proposals')).toBeInTheDocument()
    expect(screen.getByText('Inconclusive (Fail-Closed)')).toBeInTheDocument()
  })

  it('opens mutation drill-down modal on click', () => {
    render(
      <PolicyFirewall
        report={firewallFixture as any}
        repairs={repairsFixture as any}
        reducedMotion={true}
      />
    )

    const drillDownBtns = screen.getAllByText('Drill-Down')
    fireEvent.click(drillDownBtns[0])

    expect(screen.getByText(/Policy Mutation Attack Drill-Down/i)).toBeInTheDocument()
    expect(screen.getByText(/BASELINE VALUE/i)).toBeInTheDocument()
    expect(screen.getByText(/MUTATED ATTACK VALUE/i)).toBeInTheDocument()
  })

  it('renders repair proposals as non-authoritative recommendations with fail-closed status', () => {
    render(
      <PolicyFirewall
        report={firewallFixture as any}
        repairs={repairsFixture as any}
        reducedMotion={true}
      />
    )

    expect(screen.getByText(/NON-AUTHORITATIVE \(PROPOSED ONLY\)/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Apply to Production/i })).not.toBeInTheDocument()
  })
})

describe('9. Trajectory Viewer & Dual State Distinction', () => {
  it('distinguishes observed telemetry state from hidden ground truth', () => {
    render(
      <TrajectoryViewer
        trajectories={trajectoriesFixture as any}
        reducedMotion={true}
      />
    )

    expect(screen.getByText(/1\. Observed State \(Runtime Telemetry Perception\)/i)).toBeInTheDocument()
    expect(screen.getByText(/2\. Hidden Ground Truth \(Physical Environment\)/i)).toBeInTheDocument()
  })
})

describe('10. Formal Bounded Assurance (44 Properties)', () => {
  it('displays all 44 properties and mandatory limitation disclaimer', () => {
    render(<AssurancePanel report={assuranceFixture as any} />)

    expect(screen.getByText(/Formal Assurance Scope Limitation/i)).toBeInTheDocument()
    expect(screen.getByText(/Formal results are bounded proofs over the modeled MotionFence state space/i)).toBeInTheDocument()
    expect(screen.getAllByText(/PROP_001/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/PROP_044/i).length).toBeGreaterThan(0)
  })
})
