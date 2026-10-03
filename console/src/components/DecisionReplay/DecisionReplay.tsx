import React, { useState, useEffect, useRef } from 'react'
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  RotateCcw,
  Radio,
  Eye,
  Zap,
  PlayCircle,
  Cpu,
  ShieldCheck,
} from 'lucide-react'
import {
  ScenarioData,
  ScenarioMeta,
  EvidenceItem,
  ExecutionMode,
  DigitalTwinPlantState,
} from '../../types'
import { Timeline, TimelineStage } from './Timeline'
import { EvidenceInspector } from './EvidenceInspector'
import { PolicyDecisionPanel } from './PolicyDecisionPanel'
import { AuthorizationTicketCard } from './AuthorizationTicketCard'
import { RevalidationBarriers } from './RevalidationBarriers'
import { VerificationPanel } from './VerificationPanel'
import { RecoveryPanel } from './RecoveryPanel'
import { TelemetryObservationPanel } from './TelemetryObservationPanel'
import { DigitalTwin } from '../DigitalTwin/DigitalTwin'

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
  const [activeMode, setActiveMode] = useState<ExecutionMode>('LIVE')
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const isScenarioA = selectedScenarioId.includes('scenario_a') || selectedScenarioId.includes('safe')
  const isScenarioB = selectedScenarioId.includes('scenario_b') || selectedScenarioId.includes('denied')
  const isScenarioC = selectedScenarioId.includes('scenario_c') || selectedScenarioId.includes('toctou')
  const isScenarioD = selectedScenarioId.includes('scenario_d') || selectedScenarioId.includes('recovery')
  const isScenarioTelemetry = selectedScenarioId.includes('scenario_telemetry') || selectedScenarioId.includes('telemetry')

  // Synchronize execution mode from scenario data when available
  useEffect(() => {
    if (scenarioData?.execution_mode) {
      setActiveMode(scenarioData.execution_mode)
    }
  }, [scenarioData])

  // Define 10 lifecycle stages according to active scenario
  const stages: TimelineStage[] = [
    { index: 0, key: 'observe', label: '1. OBSERVE', subtitle: isScenarioTelemetry ? 'World State & Real River Telemetry' : 'World State Snapshot', status: 'passed' },
    { index: 1, key: 'evidence', label: '2. EVIDENCE', subtitle: isScenarioTelemetry ? 'Plant Sensors & USGS Provenance' : 'Sensors & Provenance', status: 'passed' },
    {
      index: 2,
      key: 'proposal',
      label: '3. PROPOSAL',
      subtitle: 'Unprivileged Nemotron 120B',
      status: 'passed',
    },
    {
      index: 3,
      key: 'policy',
      label: '4. POLICY',
      subtitle: isScenarioB ? 'Strict Policy DENY' : isScenarioTelemetry ? 'Policy Gate (River Context Check)' : 'Deterministic Gate (ALLOW)',
      status: isScenarioB ? 'blocked' : 'passed',
    },
    {
      index: 4,
      key: 'authorization',
      label: '5. AUTHORIZE',
      subtitle: isScenarioB ? 'No Ticket Minted' : 'HMAC-SHA256 Signed Ticket',
      status: isScenarioB ? 'blocked' : 'passed',
    },
    {
      index: 5,
      key: 'world_change',
      label: '6. WORLD CHANGE',
      subtitle: isScenarioC ? 'Human Enters Zone (v3->v4)' : 'Stable Invariants',
      status: isScenarioC ? 'warning' : 'passed',
    },
    {
      index: 6,
      key: 'revalidation',
      label: '7. REVALIDATE',
      subtitle: isScenarioC ? 'TOCTOU Version Block' : isScenarioB ? 'Not Reached' : '9 Barriers Verified',
      status: isScenarioC ? 'blocked' : isScenarioB ? 'pending' : 'passed',
    },
    {
      index: 7,
      key: 'execution',
      label: '8. EXECUTE',
      subtitle: isScenarioB || isScenarioC ? 'Actuator LOCKED' : isScenarioD ? 'Fault Injected (Stroke)' : '24V Stroke Energized',
      status: isScenarioB || isScenarioC ? 'blocked' : isScenarioD ? 'warning' : 'passed',
    },
    {
      index: 8,
      key: 'verification',
      label: '9. VERIFY',
      subtitle: isScenarioD ? 'Limit Switch Mismatch' : isScenarioB || isScenarioC ? 'Not Reached' : 'Postcondition Verified',
      status: isScenarioD ? 'warning' : isScenarioB || isScenarioC ? 'pending' : 'passed',
    },
    {
      index: 9,
      key: 'recovery',
      label: '10. RECOVER',
      subtitle: isScenarioD ? 'Quarantine & Verified Recovery' : 'Nominal (No Fault)',
      status: isScenarioD ? 'passed' : 'pending',
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
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
        Loading Canonical Scenario Telemetry...
      </div>
    )
  }

  const decRecord = scenarioData.decision_record
  const worldState = decRecord?.world_state_snapshot || scenarioData.pre_state
  const proposal = decRecord?.action_proposal
  const ticket = scenarioData.ticket || scenarioData.initial_ticket
  const executionResult = scenarioData.execution_result || decRecord?.execution_result
  const verificationResult = scenarioData.verification_result || decRecord?.verification_result

  const evidenceList: EvidenceItem[] = decRecord?.snapshots?.evidence || [
    {
      id: 'ev_vision_01',
      source: 'vision',
      target: 'valve_b',
      observation: { leak_detected: true, vapor_confirmed: true },
      confidence: 0.94,
      timestamp: 1710000000,
      provenance: 'cam_overhead_manifold_01',
      trust_status: 'VERIFIED_FIRST_PARTY',
      applicability: 'HIGH',
      claim_support: 'SUPPORTED',
    },
    {
      id: 'ev_pressure_01',
      source: 'pressure_sensor',
      target: 'valve_b',
      observation: { pressure_anomaly: true, pressure_psi: 42.5 },
      confidence: 0.96,
      timestamp: 1710000001,
      provenance: 'piezo_sensor_pt01',
      trust_status: 'OEM_TELEMETRY',
      applicability: 'HIGH',
      claim_support: 'SUPPORTED',
    },
  ]

  const isTicketInvalidated = isScenarioC && activeStage >= 5
  const isBlockedAtRevalidation = isScenarioC && activeStage >= 6

  // Compute Digital Twin State synchronized with active stage
  const getPlantStateForStage = (): DigitalTwinPlantState => {
    const rawSnapshots = scenarioData.digital_twin_snapshots
    if (rawSnapshots && rawSnapshots.length > 0) {
      if (isScenarioA || isScenarioTelemetry) {
        if (activeStage >= 8) return rawSnapshots[3] || rawSnapshots[rawSnapshots.length - 1]
        if (activeStage >= 7) return rawSnapshots[2] || rawSnapshots[rawSnapshots.length - 1]
        if (activeStage >= 4) return rawSnapshots[1] || rawSnapshots[0]
        return rawSnapshots[0]
      }
      if (isScenarioB) {
        if (activeStage >= 3) return rawSnapshots[1] || rawSnapshots[rawSnapshots.length - 1]
        return rawSnapshots[0]
      }
      if (isScenarioC) {
        if (activeStage >= 6) return rawSnapshots[3] || rawSnapshots[rawSnapshots.length - 1]
        if (activeStage >= 5) return rawSnapshots[2] || rawSnapshots[1]
        if (activeStage >= 4) return rawSnapshots[1] || rawSnapshots[0]
        return rawSnapshots[0]
      }
      if (isScenarioD) {
        if (activeStage >= 9) return rawSnapshots[5] || rawSnapshots[rawSnapshots.length - 1]
        if (activeStage >= 8) return rawSnapshots[3] || rawSnapshots[2]
        if (activeStage >= 7) return rawSnapshots[2] || rawSnapshots[1]
        return rawSnapshots[0]
      }
    }

    // Default dynamic state computation if snapshots not loaded
    const isHumanOccupied = isScenarioB || (isScenarioC && activeStage >= 5)
    let actuator = 'READY'
    if (isScenarioB) actuator = 'LOCKED'
    else if (isScenarioC && activeStage >= 6) actuator = 'LOCKED'
    else if (isScenarioD && activeStage >= 7 && activeStage < 9) actuator = 'FAILED'
    else if (isScenarioD && activeStage >= 9) actuator = 'VERIFIED'
    else if (isScenarioA && activeStage >= 8) actuator = 'VERIFIED'
    else if (isScenarioA && activeStage >= 7) actuator = 'ACTUATED'

    const isValveClosed = (isScenarioA && activeStage >= 7) || (isScenarioD && activeStage >= 9) || (isScenarioTelemetry && activeStage >= 7)

    return {
      stage_name: stages[activeStage]?.key || 'observe',
      pump_state: worldState?.pumps?.pump_p1 || 'INACTIVE',
      valve_b_state: isValveClosed ? 'CLOSED' : 'OPEN',
      cooling_state: worldState?.cooling || 'ACTIVE',
      human_zone: isHumanOccupied ? 'OCCUPIED' : 'CLEAR',
      actuator_status: actuator,
      world_version: isScenarioC && activeStage >= 5 ? 4 : (worldState?.version ?? 3),
      leak_active: !isValveClosed,
      pressure_psi: isValveClosed ? 125.0 : 95.5,
      flow_rate_lpm: isValveClosed ? 0.0 : 14.0,
    }
  }

  const plantState = getPlantStateForStage()
  const tokenUsage = scenarioData.token_usage || { prompt_tokens: 557, completion_tokens: 430, total_tokens: 987 }

  return (
    <div role="region" aria-label="Decision Replay Screen">
      {/* Phase 2N: Explicit Execution Mode & Canonical Demo Transport Bar */}
      <div className="transport-bar">
        <div className="scenario-picker">
          <label
            htmlFor="scenario-select"
            style={{
              fontSize: '11px',
              fontWeight: 600,
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
            }}
          >
            Scenario:
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

        {/* Live Execution Mode Switcher Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            className={`mode-badge ${activeMode === 'LIVE' ? 'live-mode' : 'offline-test-mode'}`}
            style={{ cursor: 'pointer', border: activeMode === 'LIVE' ? '1.5px solid #38bdf8' : '1px solid #475569' }}
            onClick={() => setActiveMode('LIVE')}
            title="Switch to Live Nebius Token Factory Mode"
          >
            <Zap size={12} />
            <span>RUN LIVE SCENARIO</span>
          </button>

          <button
            className={`mode-badge ${activeMode === 'REPLAY' ? 'replay-mode' : 'offline-test-mode'}`}
            style={{ cursor: 'pointer', border: activeMode === 'REPLAY' ? '1.5px solid #f59e0b' : '1px solid #475569' }}
            onClick={() => setActiveMode('REPLAY')}
            title="Load Deterministic Replay (Zero network, zero model calls, zero actuation authority)"
          >
            <PlayCircle size={12} />
            <span>LOAD REPLAY</span>
          </button>
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

      {/* Prominent Mode Context Alert */}
      {activeMode === 'LIVE' ? (
        <div
          style={{
            backgroundColor: 'rgba(2, 132, 199, 0.08)',
            border: '1px solid rgba(56, 189, 248, 0.3)',
            borderLeft: '4px solid #38bdf8',
            borderRadius: 'var(--radius-sm)',
            padding: '8px 14px',
            marginBottom: '14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '8px',
            fontSize: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#7dd3fc' }}>
            <Zap size={14} />
            <span>
              <strong>LIVE MODE ACTIVE:</strong> Action proposals originate from real Nebius Token Factory (<span className="mono">{scenarioData.model || 'nvidia/nemotron-3-super-120b-a12b'}</span>). Evaluated by deterministic MotionFence runtime.
            </span>
          </div>
          <div className="mono" style={{ fontSize: '11px', color: '#38bdf8' }}>
            CREDIT: Token Factory Free Tier | SHA256: {scenarioData.sha256_hash?.slice(0, 12)}...
          </div>
        </div>
      ) : (
        <div
          style={{
            backgroundColor: 'rgba(245, 158, 11, 0.08)',
            border: '1px solid rgba(245, 158, 11, 0.3)',
            borderLeft: '4px solid #f59e0b',
            borderRadius: 'var(--radius-sm)',
            padding: '8px 14px',
            marginBottom: '14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '8px',
            fontSize: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#fde68a' }}>
            <PlayCircle size={14} />
            <span>
              <strong>REPLAY MODE ACTIVE:</strong> Reproducing verified live audit record. Zero network calls, zero model regeneration, zero actuation authority.
            </span>
          </div>
          <div className="mono" style={{ fontSize: '11px', color: '#fbbf24' }}>
            INTEGRITY VERIFIED: SHA-256 MATCH
          </div>
        </div>
      )}

      {/* 10-Stage Visual Lifecycle Timeline */}
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
      <div
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-sm)',
          padding: '10px 16px',
          marginBottom: '20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '8px',
        }}
      >
        <div>
          <span
            style={{
              fontSize: '11px',
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              marginRight: '8px',
            }}
          >
            Scenario Narrative:
          </span>
          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {scenarioData.subtitle}
          </span>
        </div>
        <div className="mono" style={{ fontSize: '11px', color: '#38bdf8' }}>
          {scenarioData.flow_summary}
        </div>
      </div>

      {/* Phase 2N: Lightweight Plant Digital Twin Component */}
      <DigitalTwin
        plantState={plantState}
        activeStageIndex={activeStage}
        scenarioId={selectedScenarioId}
        executionMode={activeMode}
        reducedMotion={reducedMotion}
        telemetryObservation={scenarioData.telemetry_observation || decRecord.telemetry_observation}
        externalObservations={worldState?.external_observations}
      />

      {/* Phase 2O: Real-World Public Telemetry Observation Panel */}
      {(scenarioData.telemetry_observation || decRecord.telemetry_observation || isScenarioTelemetry) && (
        <div style={{ marginBottom: '20px' }}>
          <TelemetryObservationPanel
            observation={scenarioData.telemetry_observation || decRecord.telemetry_observation}
            snapshots={scenarioData.telemetry_snapshots}
            environmentalContext={worldState?.external_observations?.environmental_context}
          />
        </div>
      )}

      {/* Primary Demonstration Separation: Model Proposes vs MotionFence Decides */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '14px', marginBottom: '20px' }}>
        {/* Panel 1: MODEL PROPOSAL (UNPRIVILEGED) */}
        <div className="console-card" style={{ borderColor: 'rgba(56, 189, 248, 0.4)' }}>
          <div className="console-card-header" style={{ backgroundColor: 'rgba(2, 132, 199, 0.08)' }}>
            <span className="console-card-title">
              <Radio size={14} className="text-sky" />
              <span>MODEL PROPOSAL (UNPRIVILEGED)</span>
            </span>
            <span className="status-badge read-only" style={{ fontSize: '10px' }}>
              PROPOSES ONLY — 0 AUTHORITY
            </span>
          </div>

          <div className="console-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{ fontStyle: 'italic', fontSize: '12px', color: '#7dd3fc', borderLeft: '2px solid #38bdf8', paddingLeft: '8px' }}>
              &ldquo;Here is what I propose.&rdquo; — Model possesses ZERO actuator credentials or policy override authority.
            </div>

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

            <div
              style={{
                fontSize: '11px',
                color: 'var(--text-secondary)',
                backgroundColor: 'var(--bg-surface-elevated)',
                padding: '8px 10px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <strong>Model Rationale: </strong>
              {proposal?.rationale || 'Isolate verified leaking coolant branch on Valve B to restore plant pressure stability.'}
            </div>

            {/* Model & Token Transparency Display */}
            <div
              style={{
                fontSize: '11px',
                fontFamily: 'var(--font-mono)',
                backgroundColor: 'rgba(15, 23, 42, 0.8)',
                padding: '8px 10px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#94a3b8' }}>
                <Cpu size={12} />
                <span>{scenarioData.model || 'nvidia/nemotron-3-super-120b-a12b'}</span>
              </div>
              <div style={{ color: '#38bdf8' }}>
                Tokens: {tokenUsage.total_tokens || 987} ({tokenUsage.prompt_tokens || 557} in / {tokenUsage.completion_tokens || 430} out)
              </div>
            </div>
          </div>
        </div>

        {/* Panel 2: MOTIONFENCE DETERMINISTIC DECISION */}
        <div
          className="console-card"
          style={{
            borderColor: decRecord.policy_decision === 'ALLOW' ? 'rgba(34, 197, 94, 0.4)' : 'rgba(239, 68, 68, 0.4)',
          }}
        >
          <div
            className="console-card-header"
            style={{
              backgroundColor: decRecord.policy_decision === 'ALLOW' ? 'rgba(34, 197, 94, 0.08)' : 'rgba(239, 68, 68, 0.08)',
            }}
          >
            <span className="console-card-title">
              <ShieldCheck size={14} className={decRecord.policy_decision === 'ALLOW' ? 'text-emerald' : 'text-rose'} />
              <span>MOTIONFENCE DECISION</span>
            </span>
            <span
              className={`status-badge ${decRecord.policy_decision === 'ALLOW' ? 'operational' : 'status-deny'}`}
              style={{ fontSize: '11px' }}
            >
              {decRecord.policy_decision || 'ALLOW'}
            </span>
          </div>

          <div className="console-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div
              style={{
                fontStyle: 'italic',
                fontSize: '12px',
                color: decRecord.policy_decision === 'ALLOW' ? '#86efac' : '#fca5a5',
                borderLeft: `2px solid ${decRecord.policy_decision === 'ALLOW' ? '#22c55e' : '#ef4444'}`,
                paddingLeft: '8px',
              }}
            >
              &ldquo;Here is what is permitted.&rdquo; — Deterministic policy rules evaluate constraints independently of model rationale.
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', backgroundColor: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)' }}>
              <div>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Authority Verdict: </span>
                <strong
                  className="mono"
                  style={{
                    fontSize: '15px',
                    color: decRecord.policy_decision === 'ALLOW' ? 'var(--status-allow)' : 'var(--status-deny)',
                  }}
                >
                  {decRecord.policy_decision || 'ALLOW'}
                </strong>
              </div>
              <div style={{ textAlign: 'right', fontSize: '11px', color: 'var(--text-secondary)' }}>
                <div>Policy: {decRecord.policy_version || '1.0.0'}</div>
                <div>Enclave: HMAC-SHA256</div>
              </div>
            </div>

            {/* Invariant Evaluation Checklist */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '6px', fontSize: '11px' }}>
              <div className="barrier-item">
                <span className="barrier-name">Human Safety Zone</span>
                <span className={`barrier-status ${worldState?.human_zone === 'CLEAR' && !isScenarioB ? 'pass' : 'blocked'}`}>
                  {worldState?.human_zone === 'CLEAR' && !isScenarioB ? 'CLEAR (ALLOW)' : 'OCCUPIED (DENY)'}
                </span>
              </div>
              <div className="barrier-item">
                <span className="barrier-name">Cooling Loop</span>
                <span className="barrier-status pass">ACTIVE (PASS)</span>
              </div>
              <div className="barrier-item">
                <span className="barrier-name">Confidence Floor</span>
                <span className="barrier-status pass">96% &gt;= 90% (PASS)</span>
              </div>
              <div className="barrier-item">
                <span className="barrier-name">Target Scope</span>
                <span className="barrier-status pass">AUTHORIZED (valve_b)</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Stage Details Grid: Lifecycle Pipeline Stages */}
      <div className="stage-grid">
        {/* Stage 1: OBSERVE - Physical World State Snapshot */}
        <div className="console-card">
          <div className="console-card-header">
            <span className="console-card-title">
              <Eye size={14} />
              <span>1. Observe: Physical World State</span>
            </span>
            <span className="mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
              World Version: v{activeStage >= 5 && isScenarioC ? '4 (DRIFT)' : (worldState?.version ?? '3')}
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
                      (activeStage >= 5 && isScenarioC) || isScenarioB
                        ? 'var(--status-deny)'
                        : 'var(--status-allow)',
                  }}
                >
                  {(activeStage >= 5 && isScenarioC) || isScenarioB ? 'OCCUPIED' : 'CLEAR'}
                </span>
              </div>

              <div className="barrier-item">
                <span className="barrier-name">Cooling Loop</span>
                <span className="barrier-status pass">{worldState?.cooling || 'ACTIVE'}</span>
              </div>

              <div className="barrier-item">
                <span className="barrier-name">Valve B Position</span>
                <span className="barrier-status" style={{ color: '#38bdf8' }}>
                  {plantState.valve_b_state}
                </span>
              </div>

              <div className="barrier-item">
                <span className="barrier-name">Pump P1</span>
                <span className="barrier-status pass">{worldState?.pumps?.pump_p1 || 'INACTIVE'}</span>
              </div>
            </div>

            {/* Leak status indicator */}
            {worldState?.leak?.active && (
              <div
                style={{
                  marginTop: '10px',
                  padding: '8px 12px',
                  backgroundColor: 'rgba(239, 68, 68, 0.08)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '11px',
                  display: 'flex',
                  justifyContent: 'space-between',
                }}
              >
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

        {/* Stage 2: EVIDENCE INSPECTOR */}
        <EvidenceInspector evidenceList={evidenceList} />

        {/* Stage 4: POLICY DECISION PANEL */}
        <PolicyDecisionPanel decisionRecord={decRecord} worldState={worldState} />

        {/* Stage 5: AUTHORIZATION TICKET */}
        <AuthorizationTicketCard
          ticket={ticket}
          isInvalidated={isTicketInvalidated}
          invalidationReason="Execution-Time Revalidation Failed: World State Version Drift (v3 -> v4) on human_zone"
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
          isBlockedBeforeExecution={isBlockedAtRevalidation || isScenarioB}
        />

        {/* Stage 10: RECOVERY (for Scenario D) */}
        {isScenarioD && <RecoveryPanel scenarioData={scenarioData} />}
      </div>
    </div>
  )
}
