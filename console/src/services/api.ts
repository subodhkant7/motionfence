import {
  AssuranceReport,
  BenchmarkReportData,
  DynamicTrajectoryData,
  ExecutionMode,
  FirewallReport,
  PhysicalBackend,
  RepairProposal,
  SafetyLabExecutionResultData,
  SafetyLabScenarioData,
  ScenarioData,
  ScenarioMeta,
} from '../types'

// Bundled static fixtures for 100% offline deterministic replay
import assuranceFixture from '../data/assurance_properties.json'
import firewallFixture from '../data/firewall_report.json'
import repairsFixture from '../data/repair_proposals.json'
import scenarioAFixture from '../data/scenario_live_safe.json'
import scenarioBFixture from '../data/scenario_live_denied.json'
import scenarioCFixture from '../data/scenario_live_toctou.json'
import scenarioDFixture from '../data/scenario_live_recovery.json'
import scenarioTelemetryFixture from '../data/scenario_telemetry.json'
import scenarioEvidenceFixture from '../data/scenario_live_evidence.json'
import trajectoriesFixture from '../data/trajectories.json'

const API_BASE = '/api'

export interface DemoExecutionStatus {
  execution_id: string
  scenario_id: string
  execution_mode: string
  physical_backend: string
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'REPLAY_AVAILABLE' | string
  stage_outcome?: 'NOMINAL' | 'DENIED' | 'BLOCKED' | 'VERIFICATION_FAILED' | 'RECOVERED' | string
  created_at: number
  started_at?: number
  completed_at?: number
  duration_ms?: number
  events?: Array<{ timestamp: number; stage: string; message: string; details?: any }>
  error_message?: string | null
  error_details?: Record<string, any> | null
  token_usage?: {
    prompt_tokens?: number
    completion_tokens?: number
    total_tokens?: number
    [key: string]: any
  }
  record?: ScenarioData
  scenario_data?: ScenarioData
  poll_url?: string
}

class MotionFenceApiClient {
  private liveBackendAvailable: boolean | null = null

  async getHealth(): Promise<{
    status: string
    application: string
    safety_runtime: string
    live_model: string
    telemetry: string
    evidence_provider: string
    isaac_runtime: string
    mock_backend: string
    execution_modes: string[]
    model_provider: string
    model: string
    telemetry_provider: string
  }> {
    try {
      const res = await fetch('/health', { signal: AbortSignal.timeout(3000) })
      if (res.ok) {
        return await res.json()
      }
    } catch {
      // Fallback
    }
    return {
      status: 'healthy',
      application: 'motionfence',
      safety_runtime: 'deterministic',
      live_model: 'configured',
      telemetry: 'configured',
      evidence_provider: 'offline_fixture',
      isaac_runtime: 'unavailable',
      mock_backend: 'available',
      execution_modes: ['LIVE', 'REPLAY', 'OFFLINE_TEST'],
      model_provider: 'nebius',
      model: 'nvidia/nemotron-3-super-120b-a12b',
      telemetry_provider: 'usgs',
    }
  }

  async checkBackendStatus(): Promise<{ isLive: boolean; message: string; executionMode?: string }> {
    try {
      const res = await fetch(`${API_BASE}/status`, { signal: AbortSignal.timeout(1000) })
      if (res.ok) {
        const data = await res.json()
        this.liveBackendAvailable = true
        return {
          isLive: true,
          message: 'Connected to Live Python Read-Only Adapter',
          executionMode: data.execution_mode || 'LIVE',
        }
      }
    } catch {
      // Backend not running; fallback to local offline replay
    }
    this.liveBackendAvailable = false
    return {
      isLive: false,
      message: 'Operating in 100% Offline Deterministic Replay Mode',
      executionMode: 'REPLAY',
    }
  }

  isLive(): boolean {
    return this.liveBackendAvailable === true
  }

  async getScenarios(): Promise<ScenarioMeta[]> {
    try {
      const res = await fetch(`${API_BASE}/scenarios`, { signal: AbortSignal.timeout(1000) })
      if (res.ok) {
        return await res.json()
      }
    } catch {
      // Fallback
    }

    return [
      {
        id: 'scenario_a',
        title: 'A. Safe Execution (Nominal — Live Nemotron)',
        subtitle: 'Live Nemotron proposes safe valve isolation -> Policy ALLOW -> Ticket minted -> Mock Hardware actuates -> Verified',
        flow: 'NEMOTRON -> POLICY ALLOW -> TICKET -> HARDWARE ACTUATE -> VERIFIED',
        category: 'NOMINAL',
        execution_mode: 'LIVE',
        model: 'nvidia/nemotron-3-super-120b-a12b',
      },
      {
        id: 'scenario_b',
        title: 'B. Unsafe Proposal Denial (Live Nemotron)',
        subtitle: 'Technician in hazard zone -> Live Nemotron proposes -> Policy strictly DENIES -> Zero Ticket -> Hardware LOCKED',
        flow: 'NEMOTRON -> POLICY DENY -> NO TICKET -> HARDWARE LOCKED -> ZERO MUTATION',
        category: 'POLICY_DENIAL',
        execution_mode: 'LIVE',
        model: 'nvidia/nemotron-3-super-120b-a12b',
      },
      {
        id: 'scenario_c',
        title: 'C. TOCTOU Revalidation Block (Live Nemotron)',
        subtitle: 'Human enters hazardous zone after authorization -> Ticket invalidated before execution -> Hardware LOCKED',
        flow: 'NEMOTRON -> TICKET (v3) -> WORLD CHANGE (v4) -> REVALIDATION BLOCKED -> HARDWARE LOCKED',
        category: 'TOCTOU_DEFENSE',
        execution_mode: 'LIVE',
        model: 'nvidia/nemotron-3-super-120b-a12b',
      },
      {
        id: 'scenario_d',
        title: 'D. Actuator Failure & Recovery (Live Nemotron)',
        subtitle: 'Actuator mechanical stroke fails -> Verification mismatch -> Containment -> Quarantine -> Autonomous Recovery',
        flow: 'NEMOTRON -> TICKET -> HARDWARE FAULT -> VERIF FAILED -> QUARANTINE -> RECOVERED',
        category: 'FAULT_RECOVERY',
        execution_mode: 'LIVE',
        model: 'nvidia/nemotron-3-super-120b-a12b',
      },
      {
        id: 'scenario_telemetry',
        title: 'E. Real-World Public Telemetry (Live USGS + Nemotron)',
        subtitle: 'USGS OGC API real river observation -> Evidence & Freshness -> Live Nemotron -> Deterministic Policy -> Zero direct actuation',
        flow: 'USGS TELEMETRY -> EVIDENCE / PROVENANCE -> NEMOTRON -> POLICY GATE -> ZERO DIRECT ACTUATION',
        category: 'PUBLIC_TELEMETRY',
        execution_mode: 'LIVE',
        model: 'nvidia/nemotron-3-120b-instruct',
      },
      {
        id: 'scenario_evidence',
        title: 'F. Operational Evidence Retrieval (Live Tavily + Nemotron)',
        subtitle: 'Live Tavily operational search -> Trust classification & grounding -> Candidate constraints -> Nemotron proposal -> Policy gate -> Verified',
        flow: 'TAVILY EVIDENCE -> TRUST GROUNDING -> NEMOTRON -> POLICY GATE -> MOCK EXECUTE -> VERIFIED',
        category: 'EVIDENCE_GROUNDING',
        execution_mode: 'LIVE',
        model: 'nvidia/nemotron-3-super-120b-a12b',
      },
    ]
  }

  async getScenarioData(id: string): Promise<ScenarioData> {
    try {
      const res = await fetch(`${API_BASE}/scenarios/${id}`, { signal: AbortSignal.timeout(1000) })
      if (res.ok) {
        return await res.json()
      }
    } catch {
      // Fallback
    }

    if (id === 'scenario_a' || id.includes('safe')) {
      return scenarioAFixture as unknown as ScenarioData
    }
    if (id === 'scenario_b' || id.includes('denied')) {
      return scenarioBFixture as unknown as ScenarioData
    }
    if (id === 'scenario_c' || id.includes('toctou')) {
      return scenarioCFixture as unknown as ScenarioData
    }
    if (id === 'scenario_d' || id.includes('recovery')) {
      return scenarioDFixture as unknown as ScenarioData
    }
    if (id === 'scenario_telemetry' || id.includes('telemetry')) {
      return scenarioTelemetryFixture as unknown as ScenarioData
    }
    if (id === 'scenario_evidence' || id.includes('evidence')) {
      return scenarioEvidenceFixture as unknown as ScenarioData
    }

    return scenarioAFixture as unknown as ScenarioData
  }

  async triggerControlledDemo(
    scenario: string,
    mode: ExecutionMode = 'LIVE',
    backend: PhysicalBackend = 'mock'
  ): Promise<{
    execution_id: string
    scenario_id: string
    execution_mode: string
    physical_backend: string
    status: string
    poll_url: string
  }> {
    // Canonical scenario ID mapping
    let canonical = scenario.toLowerCase()
    if (canonical.includes('safe') || canonical === 'scenario_a') canonical = 'safe'
    else if (canonical.includes('denied') || canonical === 'scenario_b') canonical = 'denied'
    else if (canonical.includes('toctou') || canonical === 'scenario_c') canonical = 'toctou'
    else if (canonical.includes('recovery') || canonical === 'scenario_d') canonical = 'recovery'
    else if (canonical.includes('telemetry')) canonical = 'telemetry'
    else if (canonical.includes('evidence')) canonical = 'evidence'

    try {
      const res = await fetch(`${API_BASE}/demo/${canonical}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: canonical, mode, backend }),
        signal: AbortSignal.timeout(8000),
      })
      if (res.ok) {
        return await res.json()
      }
    } catch {
      // Offline fallback
    }

    return {
      execution_id: `exec_offline_${Date.now()}`,
      scenario_id: canonical,
      execution_mode: mode,
      physical_backend: backend,
      status: 'COMPLETED',
      poll_url: `/api/demo/executions/offline`,
    }
  }

  async getDemoExecution(executionId: string): Promise<DemoExecutionStatus | null> {
    if (executionId.startsWith('exec_offline_')) {
      return null
    }
    try {
      const res = await fetch(`${API_BASE}/demo/executions/${executionId}`, {
        signal: AbortSignal.timeout(4000),
      })
      if (res.ok) {
        const data = await res.json()
        if (data && !data.record && data.scenario_data) {
          data.record = data.scenario_data
        }
        return data
      }
    } catch {
      // Fallback
    }
    return null
  }

  async getFirewallReport(): Promise<FirewallReport> {
    try {
      const res = await fetch(`${API_BASE}/mutations`, { signal: AbortSignal.timeout(1000) })
      if (res.ok) {
        return await res.json()
      }
    } catch {
      // Fallback
    }
    return firewallFixture as unknown as FirewallReport
  }

  async getRepairs(): Promise<RepairProposal[]> {
    try {
      const res = await fetch(`${API_BASE}/repairs`, { signal: AbortSignal.timeout(1000) })
      if (res.ok) {
        return await res.json()
      }
    } catch {
      // Fallback
    }
    return repairsFixture as unknown as RepairProposal[]
  }

  async getTrajectories(): Promise<DynamicTrajectoryData[]> {
    try {
      const res = await fetch(`${API_BASE}/trajectories`, { signal: AbortSignal.timeout(1000) })
      if (res.ok) {
        return await res.json()
      }
    } catch {
      // Fallback
    }
    return trajectoriesFixture as unknown as DynamicTrajectoryData[]
  }

  async getAssuranceReport(): Promise<AssuranceReport> {
    try {
      const res = await fetch(`${API_BASE}/assurance`, { signal: AbortSignal.timeout(1000) })
      if (res.ok) {
        return await res.json()
      }
    } catch {
      // Fallback
    }
    return assuranceFixture as unknown as AssuranceReport
  }

  // Phase 5 & 6: Public Safety Lab & Quantitative Benchmark API
  async getSafetyLabScenarios(): Promise<SafetyLabScenarioData[]> {
    try {
      const res = await fetch(`${API_BASE}/safety-lab/scenarios`, { signal: AbortSignal.timeout(3000) })
      if (res.ok) {
        return await res.json()
      }
    } catch {
      // Fallback
    }
    return []
  }

  async runSafetyLabScenario(
    scenarioId: string,
    mode: string = 'DETERMINISTIC_REPLAY',
    seed: number = 42,
  ): Promise<{ execution_id: string; status: string; poll_url: string }> {
    const res = await fetch(`${API_BASE}/safety-lab/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario_id: scenarioId, mode, seed }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: 'DISPATCH_FAILED' }))
      throw new Error(err.message || err.error || `HTTP ${res.status}`)
    }
    return await res.json()
  }

  async runSafetyLabBenchmark(
    mode: string = 'DETERMINISTIC_REPLAY',
    seed: number = 42,
    suite: string = 'expanded',
  ): Promise<{ execution_id: string; status: string; poll_url: string }> {
    const res = await fetch(`${API_BASE}/safety-lab/benchmark`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode, seed, suite }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: 'BENCHMARK_DISPATCH_FAILED' }))
      throw new Error(err.message || err.error || `HTTP ${res.status}`)
    }
    return await res.json()
  }

  async pollSafetyLabExecution(execId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/safety-lab/executions/${execId}`)
    if (!res.ok) {
      throw new Error(`Execution ${execId} not found`)
    }
    return await res.json()
  }

  async getSafetyLabEvidence(execId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/safety-lab/evidence/${execId}`)
    if (!res.ok) {
      throw new Error(`Evidence for ${execId} not found`)
    }
    return await res.json()
  }

  async verifyEvidence(evidenceData: any): Promise<{
    is_valid: boolean
    reported_hash: string
    computed_hash: string
    message: string
    schema_valid?: boolean
    hash_scope_disclosure?: any
  }> {
    const res = await fetch(`${API_BASE}/safety-lab/verify-evidence`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(evidenceData),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      if (err.error === 'MALFORMED_EVIDENCE_SCHEMA') {
        return {
          is_valid: false,
          schema_valid: false,
          reported_hash: '',
          computed_hash: '',
          message: err.message || 'Evidence artifact schema is malformed.',
          hash_scope_disclosure: err.hash_scope_disclosure,
        }
      }
      throw new Error('Evidence verification endpoint returned error')
    }
    return await res.json()
  }

  async getLatestBenchmarkReport(suite?: string): Promise<BenchmarkReportData | null> {
    try {
      const url = suite ? `${API_BASE}/safety-lab/benchmark/report?suite=${suite}` : `${API_BASE}/safety-lab/benchmark/report`
      const res = await fetch(url, { signal: AbortSignal.timeout(4000) })
      if (res.ok) {
        return await res.json()
      }
    } catch {
      // Fallback
    }
    return null
  }
}

export const api = new MotionFenceApiClient()
