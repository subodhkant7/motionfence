import React, { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  RotateCcw,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  Info,
  Radio,
  Eye,
} from 'lucide-react'
import { ScenarioData, ScenarioMeta, EvidenceItem } from '../../types'
import { Timeline, TimelineStage } from './Timeline'
import { EvidenceInspector } from './EvidenceInspector'
import { PolicyDecisionPanel } from './PolicyDecisionPanel'
import { AuthorizationTicketCard } from './AuthorizationTicketCard'
import { RevalidationBarriers } from './RevalidationBarriers'
import { VerificationPanel } from './VerificationPanel'
import { RecoveryPanel } from './RecoveryPanel'

interface DecisionReplayProps {
  scenarios: ScenarioMeta[]
  selectedScenarioId: string
  onSelectScenario: (id: string) => void
  scenarioData: ScenarioData | null
  reducedMotion: boolean
}

export const DecisionReplay: React.FC<DecisionReplayProps> = ({
  scenarios,
  selectedScenarioId,
  onSelectScenario,
  scenarioData,
  reducedMotion,
}) => {
  const [activeStage, setActiveStage] = useState<number>(0)
  const [isPlaying, setIsPlaying] = useState<boolean>(false)
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1)
  const timerRef = useRef<NodeJS.Timeout | null>(null)

  const isScenarioA = selectedScenarioId.includes('scenario_a')
  const isScenarioB = selectedScenarioId.includes('scenario_b')
  const isScenarioC = selectedScenarioId.includes('scenario_c')

  // Define 10 lifecycle stages according to active scenario
  const stages: TimelineStage[] = [
    { index: 0, key: 'observe', label: '1. OBSERVE', subtitle: 'World State Snapshot', status: 'passed' },
    { index: 1, key: 'evidence', label: '2. EVIDENCE', subtitle: 'Sensors & Provenance', status: 'passed' },
    { index: 2, key: 'proposal', label: '3. PROPOSAL', subtitle: 'Unprivileged Agent Model', status: 'passed' },
    { index: 3, key: 'policy', label: '4. POLICY', subtitle: 'Deterministic Engine Gate', status: 'passed' },
    { index: 4, key: 'authorization', label: '5. AUTHORIZE', subtitle: 'Safety Enclave HMAC Ticket', status: 'passed' },
    {
      index: 5,
      key: 'world_change',
      label: '6. WORLD CHANGE',
      subtitle: isScenarioB ? 'Human Enters Zone (Drift)' : 'Stable Baseline',
      status: isScenarioB ? 'warning' : 'passed',
    },
    {
      index: 6,
      key: 'revalidation',
      label: '7. REVALIDATE',
      subtitle: isScenarioB ? 'TOCTOU Block Triggered' : '9 Barriers Verified',
      status: isScenarioB ? 'blocked' : 'passed',
    },
    {
      index: 7,
      key: 'execution',
      label: '8. EXECUTE',
      subtitle: isScenarioB ? 'Actuation Aborted' : '24V Actuator Energized',
      status: isScenarioB ? 'blocked' : 'passed',
    },
    {
      index: 8,
      key: 'verification',
      label: '9. VERIFY',
      subtitle: isScenarioC ? 'Limit Switch Mismatch' : isScenarioB ? 'Not Reached' : 'Postcondition Verified',
      status: isScenarioC ? 'warning' : isScenarioB ? 'pending' : 'passed',
    },
    {
      index: 9,
      key: 'recovery',
      label: '10. RECOVER',
      subtitle: isScenarioC ? 'Quarantine & Fresh Auth' : 'Nominal (No Fault)',
      status: isScenarioC ? 'passed' : 'pending',
    },
  ]

  // Playback timer loop
  useEffect(() => {
    if (isPlaying) {
      timerRef.current = setInterval(() => {
        setActiveStage((prev) => {
          if (prev >= stages.length - 1) {
            setIsPlaying(false)
            return prev
          }
          return prev + 1
        })
      }, 2200 / playbackSpeed)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [isPlaying, playbackSpeed, stages.length])

  // Reset stage on scenario switch
  useEffect(() => {
    setActiveStage(0)
    setIsPlaying(false)
  }, [selectedScenarioId])

  if (!scenarioData) {
    return <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading Scenario Data...</div>
  }

  const decRecord = scenarioData.decision_record || {}
  const worldState = decRecord.world_state_snapshot || (scenarioData as any).pre_state || {}
  const proposal = decRecord.action_proposal || (scenarioData as any).initial_proposal || {}
  const ticket = scenarioData.ticket || (scenarioData as any).initial_ticket
  const executionResult = scenarioData.execution_result || (scenarioData as any).failed_execution
  const verificationResult = scenarioData.verification_result || (scenarioData as any).failed_verification

  const evidenceList: EvidenceItem[] = decRecord.snapshots?.evidence || [
    {
      id: 'ev_vision_01',
      source: 'vision',
      target: 'valve_b',
      observation: { leak_detected: true, vapor_confirmed: true },
      confidence: 0.94,
      timestamp: Date.now() / 1000 - 2,
      provenance: 'cam_overhead_manifold_01',
      trust_status: 'VERIFIED_FIRST_PARTY',
    },
    {
      id: 'ev_pressure_01',
      source: 'pressure_sensor',
      target: 'valve_b',
      observation: { pressure_anomaly: true, pressure_psi: 42.5 },
      confidence: 0.96,
      timestamp: Date.now() / 1000 - 1,
      provenance: 'piezo_sensor_pt01',
      trust_status: 'OEM_TELEMETRY',
    },
  ]

  const isTicketInvalidated = isScenarioB && activeStage >= 5
  const isBlockedAtRevalidation = isScenarioB && activeStage >= 6

  return (
    <div role="region" aria-label="Decision Replay Screen">
      {/* Transport & Scenario Bar */}
      <div className="transport-bar">
        <div className="scenario-picker">
          <label htmlFor="scenario-select" style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Canonical Demo Scenario:
          </label>
          <select
            id="scenario-select"
            className="picker-select"
            value={selectedScenarioId}
            onChange={(e) => onSelectScenario(e.target.value)}
          >
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
        </div>

        {/* Playback Transport */}
        <div className="playback-controls">
          <button
            className="icon-btn"
            onClick={() => setActiveStage(0)}
            title="Restart Replay"
          >
            <RotateCcw size={14} />
          </button>

          <button
            className="icon-btn"
            onClick={() => setActiveStage((prev) => Math.max(0, prev - 1))}
            disabled={activeStage === 0}
            title="Step Back"
          >
            <SkipBack size={14} />
          </button>

          <button
            className={`play-btn ${!isPlaying ? 'paused' : ''}`}
            onClick={() => setIsPlaying(!isPlaying)}
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? <Pause size={14} /> : <Play size={14} />}
            <span>{isPlaying ? 'PAUSE' : 'PLAY'}</span>
          </button>

          <button
            className="icon-btn"
            onClick={() => setActiveStage((prev) => Math.min(stages.length - 1, prev + 1))}
            disabled={activeStage === stages.length - 1}
            title="Step Forward"
          >
            <SkipForward size={14} />
          </button>

          <span className="step-indicator">
            Stage {activeStage + 1} of {stages.length}
          </span>

          <button
            className="icon-btn"
            onClick={() => setPlaybackSpeed((s) => (s === 1 ? 2 : s === 2 ? 0.5 : 1))}
            title="Playback Speed"
          >
            <span>{playbackSpeed}x</span>
          </button>
        </div>
      </div>

      {/* 10-Stage Visual Timeline */}
      <Timeline
        stages={stages}
        activeStageIndex={activeStage}
        onSelectStage={(idx) => {
          setIsPlaying(false)
          setActiveStage(idx)
        }}
        reducedMotion={reducedMotion}
      />

      {/* Dynamic Scenario Subtitle / Flow Banner */}
      <div style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', padding: '10px 16px', marginBottom: '20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
        <div>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginRight: '8px' }}>
            Current Scenario Narrative:
          </span>
          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {scenarioData.subtitle}
          </span>
        </div>
        <div className="mono" style={{ fontSize: '11px', color: '#38bdf8' }}>
          {scenarioData.flow_summary}
        </div>
      </div>

      {/* Stage Details Grid */}
      <div className="stage-grid">
        {/* Stage 1: OBSERVE - Physical World State Snapshot */}
        <div className="console-card">
          <div className="console-card-header">
            <span className="console-card-title">
              <Eye size={14} />
              <span>1. Observe: Physical World State</span>
            </span>
            <span className="mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
              World Version: v{activeStage >= 5 && isScenarioB ? '2 (DRIFT)' : worldState.version || '1'}
            </span>
          </div>
          <div className="console-card-body">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px', fontSize: '12px' }}>
              <div className="barrier-item">
                <span className="barrier-name">Human Zone</span>
                <span
                  className="barrier-status"
                  style={{
                    color:
                      activeStage >= 5 && isScenarioB
                        ? 'var(--status-deny)'
                        : (worldState?.human_zone === 'CLEAR' || !worldState?.human_zone)
                        ? 'var(--status-allow)'
                        : 'var(--status-deny)',
                  }}
                >
                  {activeStage >= 5 && isScenarioB ? 'OCCUPIED (DRIFT)' : worldState?.human_zone || 'CLEAR'}
                </span>
              </div>

              <div className="barrier-item">
                <span className="barrier-name">Cooling Loop</span>
                <span className="barrier-status pass">{worldState?.cooling || 'ACTIVE'}</span>
              </div>

              <div className="barrier-item">
                <span className="barrier-name">Valve B Position</span>
                <span className="barrier-status" style={{ color: '#38bdf8' }}>
                  {activeStage >= 8 && !isScenarioB && !isScenarioC ? 'CLOSED' : 'OPEN'}
                </span>
              </div>

              <div className="barrier-item">
                <span className="barrier-name">Pump P1</span>
                <span className="barrier-status pass">{worldState?.pumps?.pump_p1 || 'INACTIVE'}</span>
              </div>
            </div>

            {/* Leak status indicator */}
            {worldState?.leak?.active && (
              <div style={{ marginTop: '10px', padding: '8px 12px', backgroundColor: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 'var(--radius-sm)', fontSize: '11px', display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#fca5a5' }}>
                  Active Coolant Leak: <strong>{worldState.leak.target}</strong>
                </span>
                <span className="mono" style={{ color: '#fca5a5' }}>
                  Flow: {worldState.leak.flow_rate_lpm} L/min
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Stage 3: PROPOSAL - Unprivileged AI Proposal */}
        <div className="console-card">
          <div className="console-card-header">
            <span className="console-card-title">
              <Radio size={14} />
              <span>3. Proposal: Unprivileged Model</span>
            </span>
            <span className="status-badge read-only" style={{ fontSize: '10px' }}>
              ZERO AUTHORITY
            </span>
          </div>
          <div className="console-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Action: </span>
                <strong className="mono" style={{ color: '#38bdf8', fontSize: '13px' }}>
                  {proposal?.action_type || 'CLOSE_VALVE'}
                </strong>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Target: </span>
                <strong className="mono" style={{ color: 'var(--text-primary)' }}>
                  {proposal?.target || 'valve_b'}
                </strong>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Confidence: </span>
                <strong className="mono" style={{ color: 'var(--status-allow)' }}>
                  {((proposal?.model_confidence ?? 0.96) * 100).toFixed(0)}%
                </strong>
              </div>
            </div>

            <div style={{ fontSize: '11px', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-surface-elevated)', padding: '8px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <strong>Agent Rationale: </strong>
              {proposal?.rationale || 'Isolate verified leaking coolant line on Valve B to restore plant pressure stability.'}
            </div>

            <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
              Security Invariant: AI proposal carries ZERO actuator credentials. Cannot directly command valve travel.
            </div>
          </div>
        </div>

        {/* Stage 2: EVIDENCE INSPECTOR */}
        <EvidenceInspector evidenceList={evidenceList} />

        {/* Stage 4: POLICY EVALUATION */}
        <PolicyDecisionPanel decisionRecord={decRecord} worldState={worldState} />

        {/* Stage 5: AUTHORIZATION TICKET */}
        <AuthorizationTicketCard
          ticket={ticket}
          isInvalidated={isTicketInvalidated}
          invalidationReason="Execution-Time Revalidation Failed: World State Version Drift (v1 -> v2) on human_zone"
          currentStage={activeStage}
          reducedMotion={reducedMotion}
        />

        {/* Stage 7: REVALIDATION (TOCTOU DEFENSE) */}
        <RevalidationBarriers
          isBlocked={isBlockedAtRevalidation}
          failedBarrier="world version"
          status={isBlockedAtRevalidation ? 'WORLD_STATE_CHANGED' : 'VALID'}
        />

        {/* Stage 9: VERIFICATION */}
        <VerificationPanel
          executionResult={executionResult}
          verificationResult={verificationResult}
          isBlockedBeforeExecution={isBlockedAtRevalidation}
        />

        {/* Stage 10: RECOVERY (for Scenario C) */}
        {isScenarioC && <RecoveryPanel scenarioData={scenarioData} />}
      </div>
    </div>
  )
}
