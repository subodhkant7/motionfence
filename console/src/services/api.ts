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
import scenarioAFixture from '../data/scenario_a.json'
import scenarioBFixture from '../data/scenario_b.json'
import scenarioCFixture from '../data/scenario_c.json'
import trajectoriesFixture from '../data/trajectories.json'

const API_BASE = '/api'

class MotionFenceApiClient {
  private liveBackendAvailable: boolean | null = null

  async checkBackendStatus(): Promise<{ isLive: boolean; message: string }> {
    try {
      const res = await fetch(`${API_BASE}/status`, { signal: AbortSignal.timeout(1000) })
      if (res.ok) {
        this.liveBackendAvailable = true
        return { isLive: true, message: 'Connected to Live Python Read-Only Adapter' }
      }
    } catch {
      // Backend not running; fallback to local offline replay
    }
    this.liveBackendAvailable = false
    return { isLive: false, message: 'Operating in 100% Offline Deterministic Replay Mode' }
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
        title: 'A. Safe Execution (Nominal)',
        subtitle: 'Agent proposes an allowed action; verified through complete safety lifecycle',
        flow: 'PROPOSE -> POLICY ALLOW -> AUTHORIZE -> REVALIDATE (PASS) -> EXECUTE -> VERIFIED',
        category: 'NOMINAL',
      },
      {
        id: 'scenario_b',
        title: 'B. TOCTOU Revalidation Block',
        subtitle: 'Human enters hazardous zone after authorization; ticket invalidated before execution',
        flow: 'PROPOSE -> POLICY ALLOW -> AUTHORIZE -> WORLD CHANGE -> REVALIDATE (BLOCKED) -> ABORT',
        category: 'TOCTOU_DEFENSE',
      },
      {
        id: 'scenario_c',
        title: 'C. Actuator Failure & Autonomous Recovery',
        subtitle: 'Actuator stroke fails; verification mismatch triggers quarantine, fresh auth, and recovery',
        flow: 'AUTH -> EXECUTE -> VERIF FAILED -> INVALIDATE -> CONTAIN/QUARANTINE -> FRESH AUTH -> VERIFIED',
        category: 'FAULT_RECOVERY',
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

    if (id === 'scenario_a' || id.includes('safe_execution')) {
      return scenarioAFixture as unknown as ScenarioData
    }
    if (id === 'scenario_b' || id.includes('toctou')) {
      return scenarioBFixture as unknown as ScenarioData
    }
    if (id === 'scenario_c' || id.includes('recovery')) {
      return scenarioCFixture as unknown as ScenarioData
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
