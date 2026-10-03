import {
  AssuranceReport,
  DynamicTrajectoryData,
  FirewallReport,
  RepairProposal,
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
import trajectoriesFixture from '../data/trajectories.json'

const API_BASE = '/api'

class MotionFenceApiClient {
  private liveBackendAvailable: boolean | null = null

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

    return scenarioAFixture as unknown as ScenarioData
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
}

export const api = new MotionFenceApiClient()
