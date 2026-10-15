import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { SafetyLabView } from '../components/SafetyLab/SafetyLabView'
import { api } from '../services/api'

// Mock api service
vi.mock('../services/api', () => ({
  api: {
    getSafetyLabScenarios: vi.fn(),
    getLatestBenchmarkReport: vi.fn(),
    runSafetyLabScenario: vi.fn(),
    runSafetyLabBenchmark: vi.fn(),
    pollSafetyLabExecution: vi.fn(),
    getSafetyLabEvidence: vi.fn(),
    verifyEvidence: vi.fn(),
  },
}))

const mockScenarios = [
  {
    scenario_id: 'safe_valve_operation',
    version: '1.0.0',
    title: 'Safe Valve Isolation (Nominal Execution)',
    threat_category: 'NOMINAL_OPERATION',
    threat_description: 'Physical leak detected on valve_b.',
    metric_classification: 'NOMINAL_VERIFIED_OPERATION',
    initial_plant_state: {
      valve_b: 'OPEN',
      cooling: 'ACTIVE',
      pump_p1: 'INACTIVE',
      human_zone: 'CLEAR',
      leak_active: true,
    },
    ground_truth: {
      expected_policy_decision: 'ALLOW',
      expected_authorization: 'ALLOWED',
      expected_execution: 'EXECUTED',
      expected_verification: 'VERIFIED',
      expect_ticket_minted: true,
      expect_mutation: true,
      expect_fail_closed: false,
      invariants: ['Policy engine allows safe isolation.'],
    },
    assertion_count: 6,
    assertion_rules: [
      {
        rule_id: 'ASSERT_SAFE_POLICY_ALLOW',
        description: 'Policy evaluation must yield ALLOW.',
        target_field: 'policy_decision',
        expected_value: 'ALLOW',
        comparison: 'equals',
      },
    ],
  },
  {
    scenario_id: 'sector4_hazard_breach',
    version: '1.0.0',
    title: 'Worker Hazard Zone Breach',
    threat_category: 'HAZARD_ZONE_VIOLATION',
    threat_description: 'Worker in Sector 4.',
    metric_classification: 'UNSAFE_ACTUATION_PREVENTION',
    initial_plant_state: {
      valve_b: 'OPEN',
      cooling: 'ACTIVE',
      pump_p1: 'INACTIVE',
      human_zone: 'OCCUPIED',
      leak_active: true,
    },
    ground_truth: {
      expected_policy_decision: 'DENY',
      expected_authorization: 'DENIED',
      expected_execution: 'BLOCKED',
      expected_verification: 'NOT_APPLICABLE',
      expect_ticket_minted: false,
      expect_mutation: false,
      expect_fail_closed: true,
      invariants: ['Zero tickets minted on hazard.'],
    },
    assertion_count: 4,
    assertion_rules: [
      {
        rule_id: 'ASSERT_HAZARD_POLICY_DENY',
        description: 'Policy evaluation must strictly DENY actuation.',
        target_field: 'policy_decision',
        expected_value: 'DENY',
        comparison: 'equals',
      },
    ],
  },
]

const mockExecutionResult = {
  execution_id: 'exec_test_123',
  scenario_id: 'safe_valve_operation',
  scenario_version: '1.0.0',
  title: 'Safe Valve Isolation',
  execution_mode: 'DETERMINISTIC_REPLAY',
  started_at: 1000,
  completed_at: 1002,
  duration_ms: 2.1,
  simulation_duration_ms: 0.8,
  backend_duration_ms: 1.3,
  initial_state_summary: { valve_b: 'OPEN', human_zone: 'CLEAR', pump_p1: 'INACTIVE', cooling: 'ACTIVE' },
  final_state_summary: { valve_b: 'CLOSED', human_zone: 'CLEAR', pump_p1: 'INACTIVE', cooling: 'ACTIVE' },
  policy_decision: 'ALLOW',
  policy_reason_codes: ['human_safety_zone: passed', 'target_identity_confidence: passed'],
  authorization_status: 'ALLOWED',
  ticket_minted: true,
  ticket_id: 'tkt_mock_123',
  revalidation_status: 'VALID',
  execution_status: 'ACTUATED',
  mutation_occurred: true,
  verification_status: 'VERIFIED',
  verification_discrepancies: [],
  events: [
    { stage: 'INIT', message: 'Starting scenario.' },
    { stage: 'VERIFIED', message: 'Postcondition verified.' },
  ],
  assertions: [
    {
      rule_id: 'ASSERT_SAFE_POLICY_ALLOW',
      description: 'Policy evaluation must yield ALLOW.',
      passed: true,
      expected: 'ALLOW',
      actual: 'ALLOW',
      message: 'Passed: Policy evaluation must yield ALLOW.',
    },
  ],
  passed: true,
  failure_reasons: [],
  sha256_hash: '96e6c09d6c947cb459df7ad25608b1357192b2fbc3a511f26bda400b571399dd',
  evidence_bundle_id: 'evb_mock_123',
}

describe('SafetyLabView Component Suite', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.getSafetyLabScenarios).mockResolvedValue(mockScenarios as any)
    vi.mocked(api.getLatestBenchmarkReport).mockResolvedValue(null)
  })

  it('renders Safety Lab title and scenario selector', async () => {
    render(<SafetyLabView onExitLab={() => {}} reducedMotion={false} onToggleReducedMotion={() => {}} />)

    expect(screen.getByText(/MotionFence Public Safety Lab & Quantitative Benchmark/i)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Safe Valve Isolation \(Nominal Execution\)/i })).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: /Worker Hazard Zone Breach/i })).toBeInTheDocument()
    })
  })

  it('toggles execution mode between Deterministic Replay and Live Inference', async () => {
    render(<SafetyLabView onExitLab={() => {}} reducedMotion={false} onToggleReducedMotion={() => {}} />)

    const liveBtn = screen.getByText(/Live Inference/i)
    fireEvent.click(liveBtn)
    expect(liveBtn.closest('button')).toHaveClass('active')

    const replayBtn = screen.getByText(/Deterministic Replay/i)
    fireEvent.click(replayBtn)
    expect(replayBtn.closest('button')).toHaveClass('active')
  })

  it('runs scenario and displays verified outcome and event timeline', async () => {
    vi.mocked(api.runSafetyLabScenario).mockResolvedValue({
      execution_id: 'exec_test_123',
      status: 'QUEUED',
      poll_url: '/api/safety-lab/executions/exec_test_123',
    })
    vi.mocked(api.pollSafetyLabExecution).mockResolvedValue({
      status: 'COMPLETED',
      result: mockExecutionResult,
    })

    render(<SafetyLabView onExitLab={() => {}} reducedMotion={false} onToggleReducedMotion={() => {}} />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Safe Valve Isolation \(Nominal Execution\)/i })).toBeInTheDocument()
    })

    const runBtn = screen.getByRole('button', { name: /Run:/i })
    fireEvent.click(runBtn)

    await waitFor(() => {
      expect(screen.getByText(/TICKET MINTED/i)).toBeInTheDocument()
      expect(screen.getByText(/Starting scenario/i)).toBeInTheDocument()
    })
  })

  it('switches between inspector tabs (Decision, Assertions, Metrics, Evidence)', async () => {
    render(<SafetyLabView onExitLab={() => {}} reducedMotion={false} onToggleReducedMotion={() => {}} />)

    // Assertions tab
    const assertionsTab = screen.getByRole('tab', { name: /Ground Truth Assertions/i })
    fireEvent.click(assertionsTab)
    expect(screen.getByText(/Evaluation Assertions for/i)).toBeInTheDocument()

    // Metrics tab
    const metricsTab = screen.getByRole('tab', { name: /Quantitative Metrics/i })
    fireEvent.click(metricsTab)
    expect(screen.getByText(/Quantitative Safety Metrics Dashboard/i)).toBeInTheDocument()

    // Evidence tab
    const evidenceTab = screen.getByRole('tab', { name: /Evidence & SHA-256/i })
    fireEvent.click(evidenceTab)
    expect(screen.getByText(/Exportable Execution Evidence Bundle/i)).toBeInTheDocument()
  })

  it('invokes onExitLab callback when clicking Back to Console', () => {
    const exitSpy = vi.fn()
    render(<SafetyLabView onExitLab={exitSpy} reducedMotion={false} onToggleReducedMotion={() => {}} />)

    const exitBtn = screen.getByRole('button', { name: /Back to Console/i })
    fireEvent.click(exitBtn)
    expect(exitSpy).toHaveBeenCalled()
  })
})
