import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  RotateCcw,
  Zap,
  PlayCircle,
  Cpu,
} from 'lucide-react'
import {
  ScenarioData,
  ScenarioMeta,
  ExecutionMode,
  PhysicalBackend,
} from '../../types'
import { Timeline, TimelineStage } from './Timeline'
import { TelemetryObservationPanel } from './TelemetryObservationPanel'
import { LiveDemoController } from './LiveDemoController'
import { DecisionTwinStage } from '../Stage/DecisionTwinStage'
import { WebGLIndustrialPlant } from '../DigitalTwin/WebGLIndustrialPlant'
import {
  derivePresentationTimeline,
  displayedStageStatus,
} from '../../services/frameDerivation'

interface DecisionReplayProps {
  scenarios: ScenarioMeta[]
  selectedScenarioId: string
  onSelectScenario: (id: string) => void
  scenarioData: ScenarioData | null
  onScenarioDataLoaded?: (data: ScenarioData) => void
  reducedMotion: boolean
  defaultView?: 'stage' | 'audit'
}

export const DecisionReplay: React.FC<DecisionReplayProps> = ({
  scenarios,
  selectedScenarioId,
  onSelectScenario,
  scenarioData,
  onScenarioDataLoaded = () => {},
  reducedMotion,
  defaultView = 'audit',
}) => {
  const [viewMode, setViewMode] = useState<'stage' | 'audit'>(defaultView)
  const [cursor, setCursor] = useState({
    id: selectedScenarioId,
    data: scenarioData,
    index: 0,
  })
  const activeStage =
    cursor.id === selectedScenarioId && cursor.data === scenarioData
      ? cursor.index
      : 0
  const setActiveStage = useCallback(
    (update: number | ((previous: number) => number)) => {
      setCursor((previous) => ({
        id: selectedScenarioId,
        data: scenarioData,
        index:
          typeof update === 'function'
            ? update(
                previous.id === selectedScenarioId &&
                  previous.data === scenarioData
                  ? previous.index
                  : 0
              )
            : update,
      }))
    },
    [selectedScenarioId, scenarioData]
  )
  const [isPlaying, setIsPlaying] = useState<boolean>(false)
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1)
  const [activeMode, setActiveMode] = useState<ExecutionMode>('REPLAY')
  const [activeBackend, setActiveBackend] = useState<PhysicalBackend>('mock')
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const presentation = useMemo(
    () => derivePresentationTimeline(selectedScenarioId, scenarioData),
    [selectedScenarioId, scenarioData]
  )
  const frame = presentation.frames[activeStage]
  const currentMode = scenarioData?.current_execution_mode ?? 'REPLAY'
  const stages: TimelineStage[] = presentation.frames.map((item) => {
    const status = displayedStageStatus(item, activeStage)
    return {
      index: item.stageIndex,
      key: item.stageKey,
      label: item.stageLabel,
      subtitle:
        item.stageIndex > activeStage
          ? 'Awaiting playback'
          : item.stageSubtitle,
      status:
        status === 'PASSED'
          ? 'passed'
          : status === 'PENDING'
            ? 'pending'
            : ['BLOCKED', 'DENIED', 'FAILED'].includes(status)
              ? 'blocked'
              : 'warning',
    }
  })

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
  }, [isPlaying, playbackSpeed, stages.length, setActiveStage])

  // Reset stage on scenario switch
  useEffect(() => {
    setIsPlaying(false)
  }, [selectedScenarioId])

  if (!scenarioData) {
    return (
      <div
        style={{
          padding: '40px',
          textAlign: 'center',
          color: 'var(--text-muted)',
        }}
      >
        Loading Canonical Scenario Telemetry...
      </div>
    )
  }

  return (
    <div role="region" aria-label="Decision Replay Screen">
      {/* View Mode Selector: 3D Decision Twin Stage vs Classic Audit Grid */}
      <div
        className="replay-view-toggle-bar"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          backgroundColor: 'var(--bg-surface-elevated)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-md)',
          padding: '6px 14px',
          marginBottom: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              fontSize: '11px',
              fontWeight: 700,
              letterSpacing: '0.05em',
              color: 'var(--text-muted)',
            }}
          >
            CONSOLE VIEW:
          </span>
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            type="button"
            data-testid="view-mode-stage"
            onClick={() => setViewMode('stage')}
            style={{
              padding: '4px 12px',
              fontSize: '11px',
              fontWeight: 700,
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              border:
                viewMode === 'stage'
                  ? '1.5px solid #38bdf8'
                  : '1px solid var(--border-subtle)',
              backgroundColor:
                viewMode === 'stage'
                  ? 'rgba(56, 189, 248, 0.15)'
                  : 'transparent',
              color: viewMode === 'stage' ? '#38bdf8' : 'var(--text-muted)',
            }}
          >
            3D SPLIT STAGE (PHASE 2Y)
          </button>
          <button
            type="button"
            data-testid="view-mode-audit"
            onClick={() => setViewMode('audit')}
            style={{
              padding: '4px 12px',
              fontSize: '11px',
              fontWeight: 700,
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              border:
                viewMode === 'audit'
                  ? '1.5px solid #38bdf8'
                  : '1px solid var(--border-subtle)',
              backgroundColor:
                viewMode === 'audit'
                  ? 'rgba(56, 189, 248, 0.15)'
                  : 'transparent',
              color: viewMode === 'audit' ? '#38bdf8' : 'var(--text-muted)',
            }}
          >
            DETAILED AUDIT CARDS
          </button>
        </div>
      </div>

      {viewMode === 'stage' ? (
        <div style={{ width: '100%', minHeight: '680px' }}>
          <DecisionTwinStage
            scenarioId={selectedScenarioId}
            scenarioData={scenarioData}
            reducedMotion={reducedMotion}
          />
        </div>
      ) : (
        <>
          {/* Phase 2R: Controlled Live Demo Controller */}
          <LiveDemoController
            playbackStageIndex={activeStage}
            scenarios={scenarios}
            selectedScenarioId={selectedScenarioId}
            onSelectScenario={onSelectScenario}
            scenarioData={scenarioData}
            onScenarioDataLoaded={onScenarioDataLoaded}
            activeMode={activeMode}
            onModeChange={setActiveMode}
            activeBackend={activeBackend}
            onBackendChange={setActiveBackend}
          />

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
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                flexWrap: 'wrap',
              }}
            >
              <button
                className={`mode-badge ${activeMode === 'LIVE' ? 'live-mode' : 'offline-test-mode'}`}
                style={{
                  cursor: 'pointer',
                  border:
                    activeMode === 'LIVE'
                      ? '1.5px solid #38bdf8'
                      : '1px solid #475569',
                }}
                onClick={() => setActiveMode('LIVE')}
                title="Switch to Live Nebius Token Factory Mode"
              >
                <Zap size={12} />
                <span>RUN LIVE SCENARIO</span>
              </button>

              <button
                className={`mode-badge ${activeMode === 'REPLAY' ? 'replay-mode' : 'offline-test-mode'}`}
                style={{
                  cursor: 'pointer',
                  border:
                    activeMode === 'REPLAY'
                      ? '1.5px solid #f59e0b'
                      : '1px solid #475569',
                }}
                onClick={() => setActiveMode('REPLAY')}
                title="Load Deterministic Replay (Zero network, zero model calls, zero actuation authority)"
              >
                <PlayCircle size={12} />
                <span>LOAD REPLAY</span>
              </button>

              {/* Phase 2P: Physical Backend Switcher */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  marginLeft: '4px',
                  paddingLeft: '8px',
                  borderLeft: '1px solid var(--border-subtle)',
                }}
              >
                <button
                  className="mode-badge"
                  data-testid="toggle-backend-mock"
                  style={{
                    cursor: 'pointer',
                    border:
                      activeBackend === 'mock'
                        ? '1.5px solid #38bdf8'
                        : '1px solid #475569',
                    backgroundColor:
                      activeBackend === 'mock'
                        ? 'rgba(56, 189, 248, 0.15)'
                        : 'transparent',
                    color: activeBackend === 'mock' ? '#38bdf8' : '#94a3b8',
                  }}
                  onClick={() => setActiveBackend('mock')}
                  title="Switch to Deterministic Mock Hardware Endpoint"
                >
                  <Cpu size={12} />
                  <span>MOCK</span>
                </button>

                <button
                  className="mode-badge"
                  data-testid="toggle-backend-isaac"
                  style={{
                    cursor: 'pointer',
                    border:
                      activeBackend === 'isaac'
                        ? '1.5px solid #76b900'
                        : '1px solid #475569',
                    backgroundColor:
                      activeBackend === 'isaac'
                        ? 'rgba(118, 185, 0, 0.15)'
                        : 'transparent',
                    color: activeBackend === 'isaac' ? '#76b900' : '#94a3b8',
                  }}
                  onClick={() => setActiveBackend('isaac')}
                  title="Switch to NVIDIA Isaac Sim Physical Simulation Backend"
                >
                  <Cpu size={12} />
                  <span>ISAAC SIM</span>
                </button>
              </div>
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
                onClick={() =>
                  setActiveStage((prev) =>
                    Math.min(stages.length - 1, prev + 1)
                  )
                }
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
                onClick={() =>
                  setPlaybackSpeed((s) => (s === 1 ? 2 : s === 2 ? 0.5 : 1))
                }
                title="Playback Speed"
              >
                <span>{playbackSpeed}x</span>
              </button>
            </div>
          </div>

          {/* Prominent Mode Context Alert */}
          {currentMode === 'LIVE' ? (
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
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  color: '#7dd3fc',
                }}
              >
                <Zap size={14} />
                <span>
                  <strong>LIVE MODE ACTIVE:</strong> Action proposals originate
                  from real Nebius Token Factory (
                  <span className="mono">
                    {scenarioData.model || 'NOT_RECORDED'}
                  </span>
                  ). Evaluated by deterministic MotionFence runtime.
                </span>
              </div>
              <div
                className="mono"
                style={{ fontSize: '11px', color: '#38bdf8' }}
              >
                CREDIT: Token Factory Free Tier | SHA256:{' '}
                {scenarioData.sha256_hash?.slice(0, 12)}...
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
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  color: '#fde68a',
                }}
              >
                <PlayCircle size={14} />
                <span>
                  <strong>REPLAY MODE ACTIVE:</strong> Displaying recorded
                  evidence. No fresh model inference or actuator authority.
                </span>
              </div>
              <div
                className="mono"
                style={{ fontSize: '11px', color: '#fbbf24' }}
              >
                Recorded hash: {frame.recordHash ?? 'NOT_RECORDED'}
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
              <span
                style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                }}
              >
                {frame.stageSubtitle}
              </span>
            </div>
            <div
              className="mono"
              style={{ fontSize: '11px', color: '#38bdf8' }}
            >
              {frame.outcome}
            </div>
          </div>

          <div className="console-card" style={{ marginBottom: '16px' }}>
            <div className="console-card-header">Recorded plant state</div>
            <div className="console-card-body">
              <p data-testid="physical-backend-badge">
                PHYSICAL BACKEND: {frame.physicalBackend}
              </p>
              <p>
                Requested backend for next execution: {activeBackend}. A
                selection does not establish a simulator run.
              </p>
              <p>
                MODELED PLANT (CONTROL-SYSTEM DIGITAL TWIN) · PUMP P1:{' '}
                {frame.plantState.pump_state} · VALVE B:{' '}
                {frame.plantState.valve_b_state}
              </p>
              {scenarioData.telemetry_observation && (
                <p>
                  REAL-WORLD OBSERVATION (USGS OGC API) — ENVIRONMENTAL CONTEXT
                  · EXTERNAL OBSERVATION ≠ INTERNAL ACTUATOR STATE
                </p>
              )}
              <p>
                The digital twin and mock hardware are software representations
                used for demonstration and validation.
              </p>
              {activeBackend === 'isaac' && (
                <div data-testid="isaac-stage-inspector">
                  <p>
                    NVIDIA Isaac Sim Stage Inspector · SIMULATOR ONLY — ZERO
                    SAFETY AUTHORITY
                  </p>
                  <p>
                    Recorded USD prim paths:{' '}
                    {scenarioData.isaac_prim_paths
                      ? JSON.stringify(scenarioData.isaac_prim_paths)
                      : 'NOT_RECORDED'}
                  </p>
                  <p>
                    Joint Angle:{' '}
                    {frame.plantState.valve_b_angle_deg ?? 'NOT_RECORDED'} ·
                    Worker Proximity:{' '}
                    {frame.plantState.human_distance_m ?? 'NOT_RECORDED'}
                  </p>
                </div>
              )}
            </div>
          </div>
          {scenarioData.telemetry_observation && (
            <TelemetryObservationPanel
              observation={scenarioData.telemetry_observation}
              snapshots={scenarioData.telemetry_snapshots}
              environmentalContext={
                scenarioData.pre_state?.external_observations
                  ?.environmental_context
              }
            />
          )}
          <div style={{ height: '500px', marginBottom: '20px' }}>
            <WebGLIndustrialPlant
              key={selectedScenarioId}
              plantState={frame.plantState}
              cameraPreset={frame.cameraPreset}
              reducedMotion={reducedMotion}
            />
          </div>
          <div className="stage-grid">
            {presentation.frames.map((item) => {
              const visible = item.stageIndex <= activeStage
              const facts =
                item.proposal ??
                item.policy ??
                item.authorization ??
                item.worldChange ??
                item.revalidation ??
                item.execution ??
                item.verification ??
                item.recovery ??
                (item.stageKey === 'observe'
                  ? item.plantState
                  : scenarioData.decision_record?.snapshots?.evidence)
              return (
                <div
                  className="console-card"
                  key={item.stageKey}
                  data-testid={`audit-evidence-${item.stageKey}`}
                >
                  <div className="console-card-header">
                    <span className="console-card-title">
                      {item.stageKey === 'proposal'
                        ? 'MODEL PROPOSAL (UNPRIVILEGED)'
                        : item.stageKey === 'policy'
                          ? 'MOTIONFENCE DECISION'
                          : `Evidence: ${item.stageKey}`}
                    </span>
                    <span>{displayedStageStatus(item, activeStage)}</span>
                  </div>
                  <div className="console-card-body">
                    <p>{visible ? item.stageSubtitle : 'Awaiting playback'}</p>
                    {item.stageKey === 'proposal' && (
                      <p>
                        PROPOSES ONLY — 0 AUTHORITY · Tokens:{' '}
                        {visible
                          ? (scenarioData.token_usage?.total_tokens ??
                            'NOT_RECORDED')
                          : 'PENDING'}
                      </p>
                    )}
                    {visible && (
                      <>
                        <p>Source: {item.sourcePaths.join(' · ')}</p>
                        {item.evidenceIssues.length > 0 && (
                          <p role="alert">{item.evidenceIssues.join(' · ')}</p>
                        )}
                        <pre
                          style={{
                            whiteSpace: 'pre-wrap',
                            overflowWrap: 'anywhere',
                            fontSize: '12px',
                          }}
                        >
                          {facts
                            ? JSON.stringify(facts, null, 2)
                            : 'NOT_RECORDED'}
                        </pre>
                      </>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
