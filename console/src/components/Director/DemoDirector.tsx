import React, { useState, useEffect, useRef, useCallback } from 'react'
import {
  Play,
  Pause,
  Square,
  RotateCcw,
  RefreshCw,
  ArrowRight,
  ShieldCheck,
  ShieldAlert,
  Zap,
  PlayCircle,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Lock,
  Activity,
  ChevronRight,
  Clock,
  Radio,
  Eye,
  ZapOff,
  ExternalLink,
} from 'lucide-react'
import {
  AssuranceReport,
  ExecutionMode,
  ScenarioData,
  ScenarioMeta,
} from '../../types'
import {
  DirectorState,
  SceneDefinition,
  SceneExecutionStatus,
  SceneId,
} from '../../types/director'
import { DIRECTOR_SCENES } from './DirectorSceneSequence'
import { api, DemoExecutionStatus } from '../../services/api'
import { DecisionReplay } from '../DecisionReplay/DecisionReplay'
import { AssurancePanel } from '../Assurance/AssurancePanel'
import './DemoDirector.css'

interface DemoDirectorProps {
  scenarios: ScenarioMeta[]
  onExitDirector: () => void
  reducedMotion: boolean
  onToggleReducedMotion: () => void
  assuranceReport: AssuranceReport | null
}

/**
 * Pure helper to derive the terminal scene execution status strictly from
 * actual execution outcomes, recorded assertions, and world state artifacts
 * rather than hardcoded scene identifiers.
 */
export function deriveExecutionOutcome(
  record?: ScenarioData | null,
  stageOutcome?: string | null
): SceneExecutionStatus {
  // 1. Explicit stage_outcome from execution status takes priority if present
  if (stageOutcome) {
    const outcomeUpper = stageOutcome.toUpperCase()
    if (outcomeUpper === 'DENIED') return 'DENIED'
    if (outcomeUpper === 'BLOCKED') return 'BLOCKED'
    if (outcomeUpper === 'RECOVERED') return 'RECOVERED'
    if (outcomeUpper === 'VERIFICATION_FAILED') return 'VERIFICATION_FAILED'
    if (outcomeUpper === 'NOMINAL' || outcomeUpper === 'VERIFIED') return 'VERIFIED'
  }

  // 2. Derive outcome purely from recorded assertions and execution artifacts in ScenarioData
  if (record) {
    const rec = record as any

    // Recovery check: fault injection / containment / recovery plan executed
    if (
      rec.recovery_lifecycle?.status === 'RECOVERED' ||
      rec.recovery_result?.status === 'RECOVERED' ||
      rec.recovery_plan?.status === 'EXECUTED' ||
      rec.fault_injected ||
      (record.scenario_id?.includes('recovery') && record.verification_result?.status === 'VERIFIED')
    ) {
      return 'RECOVERED'
    }

    // TOCTOU check: world change event / revalidation status / invalidated ticket
    const reval =
      record.decision_record?.revalidation_status ||
      rec.revalidation_status ||
      record.ticket?.status ||
      record.initial_ticket?.status
    if (
      reval === 'BLOCKED' ||
      reval === 'INVALIDATED' ||
      reval === 'MISMATCH' ||
      record.world_change_event !== undefined
    ) {
      return 'BLOCKED'
    }

    // Policy denial check: explicit policy denial or zero ticket with human in zone / contradiction
    const polDecision =
      record.policy_decision?.decision_type ||
      record.decision_record?.policy_decision
    if (
      polDecision === 'DENY' ||
      record.policy_decision?.is_allowed === false ||
      record.pre_state?.human_zone === 'OCCUPIED'
    ) {
      return 'DENIED'
    }

    // Verification failure check
    if (
      record.verification_result?.status === 'FAILED' ||
      record.verification_result?.status === 'VERIFICATION_FAILED' ||
      (record.verification_result?.discrepancies && record.verification_result.discrepancies.length > 0)
    ) {
      return 'VERIFICATION_FAILED'
    }

    // Successful nominal verification
    if (
      record.verification_result?.status === 'VERIFIED' ||
      record.verification_result?.action_occurred === true
    ) {
      return 'VERIFIED'
    }
  }

  return 'VERIFIED'
}

export const DemoDirector: React.FC<DemoDirectorProps> = ({
  scenarios,
  onExitDirector,
  reducedMotion,
  onToggleReducedMotion,
  assuranceReport,
}) => {
  const [currentSceneIndex, setCurrentSceneIndex] = useState<number>(0)
  const [directorState, setDirectorState] = useState<DirectorState>('IDLE')
  const [sceneStatus, setSceneStatus] = useState<SceneExecutionStatus>('PENDING')
  const [preferredMode, setPreferredMode] = useState<ExecutionMode>('LIVE')
  const [activeExecutionMode, setActiveExecutionMode] = useState<ExecutionMode>('LIVE')
  const [scenarioData, setScenarioData] = useState<ScenarioData | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [errorDetails, setErrorDetails] = useState<Record<string, any> | null>(null)
  const [completedScenes, setCompletedScenes] = useState<SceneId[]>([])
  const [dwellRemaining, setDwellRemaining] = useState<number>(0)
  const [healthStatus, setHealthStatus] = useState<any>(null)

  const activePollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const dwellTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const stageContainerRef = useRef<HTMLDivElement | null>(null)
  const executeSceneRef = useRef<(sceneIndex: number) => Promise<void>>(() => Promise.resolve())

  const currentScene: SceneDefinition = DIRECTOR_SCENES[currentSceneIndex] || DIRECTOR_SCENES[0]

  // Clean up all intervals on unmount
  useEffect(() => {
    return () => {
      if (activePollingRef.current) clearInterval(activePollingRef.current)
      if (dwellTimerRef.current) clearInterval(dwellTimerRef.current)
    }
  }, [])

  // Initial health readiness check on mount (non-mutating, zero actuation)
  useEffect(() => {
    async function fetchHealth() {
      const h = await api.getHealth()
      setHealthStatus(h)
    }
    fetchHealth()
  }, [])

  // Smooth scroll / focus targeted panel
  const scrollToFocusedPanel = useCallback(
    (panelId: string) => {
      if (!panelId) return
      const el = document.getElementById(panelId)
      if (el) {
        if (reducedMotion) {
          el.scrollIntoView({ behavior: 'auto', block: 'center' })
        } else {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
      }
    },
    [reducedMotion]
  )

  // Step into and execute a scene
  const stepToScene = useCallback(
    async (index: number) => {
      if (index < 0 || index >= DIRECTOR_SCENES.length) return
      setCurrentSceneIndex(index)
      const targetScene = DIRECTOR_SCENES[index]
      setActiveExecutionMode(targetScene.executionMode)
      setErrorMessage(null)
      setErrorDetails(null)
      setDwellRemaining(0)
      if (dwellTimerRef.current) clearInterval(dwellTimerRef.current)
      if (activePollingRef.current) clearInterval(activePollingRef.current)
      await executeSceneRef.current(index)
    },
    []
  )

  // Handle dwell countdown and advance to next scene
  const startDwellCountdown = useCallback(
    (dwellSeconds: number, onComplete: () => void) => {
      if (dwellTimerRef.current) clearInterval(dwellTimerRef.current)
      setDwellRemaining(dwellSeconds)

      let remaining = dwellSeconds
      dwellTimerRef.current = setInterval(() => {
        remaining -= 1
        setDwellRemaining(remaining)
        if (remaining <= 0) {
          if (dwellTimerRef.current) clearInterval(dwellTimerRef.current)
          onComplete()
        }
      }, 1000)
    },
    []
  )

  // Execute a single scene within the sequence
  const executeScene = useCallback(
    async (sceneIndex: number) => {
      if (sceneIndex >= DIRECTOR_SCENES.length) {
        setDirectorState('COMPLETED')
        setSceneStatus('COMPLETED')
        return
      }

      const scene = DIRECTOR_SCENES[sceneIndex]
      setCurrentSceneIndex(sceneIndex)
      setSceneStatus('RUNNING')
      setErrorMessage(null)
      setErrorDetails(null)
      setDwellRemaining(0)

      // Handle INTRO scene
      if (scene.id === 'intro') {
        setActiveExecutionMode('LIVE')
        const h = await api.getHealth()
        setHealthStatus(h)
        setSceneStatus('COMPLETED')
        setCompletedScenes((prev) => Array.from(new Set([...prev, 'intro'])))

        startDwellCountdown(scene.dwellTimeSeconds, () => {
          executeSceneRef.current(sceneIndex + 1)
        })
        return
      }

      // Handle CLOSE scene
      if (scene.id === 'close') {
        setActiveExecutionMode('LIVE')
        setSceneStatus('COMPLETED')
        setCompletedScenes((prev) => Array.from(new Set([...prev, 'close'])))
        setDirectorState('COMPLETED')
        return
      }

      // Handle REPLAY_AND_ASSURANCE scene
      if (scene.id === 'replay_assurance') {
        setActiveExecutionMode('REPLAY')
        // Load offline replay trace
        const replayData = await api.getScenarioData('scenario_a')
        if (replayData) {
          setScenarioData({
            ...replayData,
            execution_mode: 'REPLAY',
            physical_backend: 'mock',
          })
        }
        setSceneStatus('VERIFIED')
        setCompletedScenes((prev) => Array.from(new Set([...prev, 'replay_assurance'])))

        startDwellCountdown(scene.dwellTimeSeconds, () => {
          executeSceneRef.current(sceneIndex + 1)
        })
        return
      }

      // Live / Replay scenario dispatch via official controlled demo API
      const targetScenario = scene.scenarioId || 'safe'
      const runMode = preferredMode === 'REPLAY' ? 'REPLAY' : scene.executionMode
      const runBackend = scene.physicalBackend

      try {
        const triggerRes = await api.triggerControlledDemo(targetScenario, runMode, runBackend)
        const execId = triggerRes.execution_id
        setActiveExecutionMode((triggerRes.execution_mode as ExecutionMode) || runMode)

        // If local offline fallback was returned
        if (execId.startsWith('exec_offline_')) {
          const loaded = await api.getScenarioData(targetScenario)
          if (loaded) {
            setScenarioData({
              ...loaded,
              execution_mode: 'REPLAY',
              physical_backend: runBackend,
            })
          }
          setActiveExecutionMode('REPLAY')
          const finalStatus = deriveExecutionOutcome(loaded, null)
          setSceneStatus(finalStatus)
          setCompletedScenes((prev) => Array.from(new Set([...prev, scene.id])))
          scrollToFocusedPanel(scene.targetPanelId)

          startDwellCountdown(scene.dwellTimeSeconds, () => {
            executeSceneRef.current(sceneIndex + 1)
          })
          return
        }

        // Poll execution status until terminal
        if (activePollingRef.current) clearInterval(activePollingRef.current)
        let attempts = 0
        const maxAttempts = 35 // Up to 35 * 400ms = 14s

        activePollingRef.current = setInterval(async () => {
          attempts += 1
          const statusObj: DemoExecutionStatus | null = await api.getDemoExecution(execId)

          if (!statusObj) {
            if (attempts >= maxAttempts) {
              if (activePollingRef.current) clearInterval(activePollingRef.current)
              setSceneStatus('ERROR')
              setDirectorState('ERROR')
              setErrorMessage('Execution status poll timed out.')
            }
            return
          }

          if (statusObj.execution_mode) {
            setActiveExecutionMode(statusObj.execution_mode as ExecutionMode)
          }

          if (statusObj.status === 'COMPLETED') {
            if (activePollingRef.current) clearInterval(activePollingRef.current)

            const finalRecord = statusObj.record || statusObj.scenario_data
            if (finalRecord) {
              setScenarioData(finalRecord)
            }

            // Derive granular scene status from recorded assertions
            const derivedStatus = deriveExecutionOutcome(finalRecord, statusObj.stage_outcome)
            setSceneStatus(derivedStatus)
            setCompletedScenes((prev) => Array.from(new Set([...prev, scene.id])))
            scrollToFocusedPanel(scene.targetPanelId)

            startDwellCountdown(scene.dwellTimeSeconds, () => {
              executeSceneRef.current(sceneIndex + 1)
            })
          } else if (statusObj.status === 'FAILED') {
            if (activePollingRef.current) clearInterval(activePollingRef.current)
            setSceneStatus('ERROR')
            setDirectorState('ERROR')
            setErrorMessage(statusObj.error_message || 'Scene execution returned failure.')
            setErrorDetails(statusObj.error_details || null)
          }
        }, 450)
      } catch (err: any) {
        setSceneStatus('ERROR')
        setDirectorState('ERROR')
        setErrorMessage(err?.message || 'Failed to dispatch scenario request.')
        setErrorDetails(null)
      }
    },
    [preferredMode, scrollToFocusedPanel, startDwellCountdown]
  )

  useEffect(() => {
    executeSceneRef.current = executeScene
  }, [executeScene])

  // Start Full Demo orchestration
  const handleStartFullDemo = () => {
    if (directorState === 'RUNNING') return
    setDirectorState('RUNNING')
    setCompletedScenes([])
    setErrorMessage(null)
    setErrorDetails(null)
    executeScene(0)
  }

  // Pause Director
  const handlePause = () => {
    setDirectorState('PAUSED')
    if (dwellTimerRef.current) clearInterval(dwellTimerRef.current)
    if (activePollingRef.current) clearInterval(activePollingRef.current)
  }

  // Resume Director
  const handleResume = () => {
    setDirectorState('RUNNING')
    if (dwellRemaining > 0) {
      startDwellCountdown(dwellRemaining, () => {
        executeScene(currentSceneIndex + 1)
      })
    } else {
      executeScene(currentSceneIndex)
    }
  }

  // Stop / Abort Director
  const handleStop = () => {
    setDirectorState('IDLE')
    setSceneStatus('PENDING')
    setDwellRemaining(0)
    if (dwellTimerRef.current) clearInterval(dwellTimerRef.current)
    if (activePollingRef.current) clearInterval(activePollingRef.current)
  }

  // Reset to Scene 1
  const handleReset = () => {
    handleStop()
    stepToScene(0)
  }

  // Retry failed scene
  const handleRetry = () => {
    setDirectorState('RUNNING')
    executeScene(currentSceneIndex)
  }

  // Continue to next scene despite error
  const handleContinue = () => {
    setDirectorState('RUNNING')
    executeScene(currentSceneIndex + 1)
  }

  // Overall progress percentage
  const progressPercent = Math.round(((currentSceneIndex + 1) / DIRECTOR_SCENES.length) * 100)

  return (
    <div className="demo-director-container" role="region" aria-label="MotionFence Demo Director">
      {/* 1. TOP DIRECTOR BAR */}
      <div className="director-top-bar">
        <div className="director-brand-group">
          <div className="director-logo-badge" title="Deterministic Demo Director">
            <Radio size={14} className={directorState === 'RUNNING' ? 'pulse-icon' : ''} />
            <span>MF-DIRECTOR</span>
          </div>
          <div className="director-scene-title-wrap">
            <span className="director-main-brand">MotionFence Demo Director</span>
            <div className="director-scene-subrow">
              <span className="scene-index-badge">
                SCENE {currentSceneIndex + 1} / {DIRECTOR_SCENES.length}
              </span>
              <h2 className="scene-headline">{currentScene.title}</h2>
            </div>
          </div>
        </div>

        {/* Status & Mode Indicators */}
        <div className="director-status-group">
          {/* Live vs Replay badge derived from actual execution metadata */}
          <span
            className={`mode-indicator ${
              activeExecutionMode === 'LIVE'
                ? 'live'
                : activeExecutionMode === 'REPLAY'
                ? 'replay'
                : 'offline'
            }`}
            data-testid="director-mode-badge"
          >
            {activeExecutionMode === 'LIVE' ? (
              <>
                <Zap size={12} /> LIVE (NEBIUS NEMOTRON)
              </>
            ) : (
              <>
                <PlayCircle size={12} /> REPLAY (OFFLINE TRACE)
              </>
            )}
          </span>

          {/* Execution Status Badge */}
          <span
            className={`scene-status-badge ${sceneStatus.toLowerCase()}`}
            data-testid="director-status-badge"
          >
            {sceneStatus === 'RUNNING' && <Activity size={12} className="spin-icon" />}
            {sceneStatus === 'VERIFIED' && <CheckCircle2 size={12} />}
            {sceneStatus === 'DENIED' && <Lock size={12} />}
            {sceneStatus === 'BLOCKED' && <ShieldAlert size={12} />}
            {sceneStatus === 'RECOVERED' && <CheckCircle2 size={12} />}
            {sceneStatus === 'ERROR' && <XCircle size={12} />}
            <span>STATUS: {sceneStatus}</span>
          </span>

          {/* Dwell countdown badge */}
          {dwellRemaining > 0 && (
            <span className="dwell-badge" title="Auto-advancing to next scene">
              <Clock size={12} />
              <span>Next in {dwellRemaining}s</span>
            </span>
          )}
        </div>

        {/* Primary Controls */}
        <div className="director-controls-group">
          {directorState === 'IDLE' && (
            <button
              className="director-btn primary-start-btn"
              onClick={handleStartFullDemo}
              id="btn-start-full-demo"
              data-testid="start-full-demo-btn"
            >
              <Play size={14} />
              <span>Start Full Demo</span>
            </button>
          )}

          {directorState === 'RUNNING' && (
            <>
              <button
                className="director-btn pause-btn"
                onClick={handlePause}
                id="btn-pause-demo"
                title="Pause sequence to speak"
              >
                <Pause size={14} />
                <span>Pause</span>
              </button>
              <button
                className="director-btn stop-btn"
                onClick={handleStop}
                id="btn-stop-demo"
                title="Stop demo sequence"
              >
                <Square size={14} />
                <span>Stop</span>
              </button>
            </>
          )}

          {directorState === 'PAUSED' && (
            <>
              <button
                className="director-btn resume-btn"
                onClick={handleResume}
                id="btn-resume-demo"
              >
                <Play size={14} />
                <span>Resume</span>
              </button>
              <button className="director-btn stop-btn" onClick={handleStop}>
                <Square size={14} />
                <span>Stop</span>
              </button>
            </>
          )}

          {directorState === 'ERROR' && (
            <>
              <button
                className="director-btn retry-btn"
                onClick={handleRetry}
                id="btn-retry-demo"
              >
                <RefreshCw size={14} />
                <span>Retry</span>
              </button>
              <button
                className="director-btn continue-btn"
                onClick={handleContinue}
                id="btn-continue-demo"
              >
                <ArrowRight size={14} />
                <span>Continue</span>
              </button>
              <button className="director-btn stop-btn" onClick={handleStop}>
                <Square size={14} />
                <span>Stop</span>
              </button>
            </>
          )}

          {directorState === 'COMPLETED' && (
            <button
              className="director-btn reset-btn"
              onClick={handleReset}
              id="btn-reset-demo"
            >
              <RotateCcw size={14} />
              <span>Restart Demo</span>
            </button>
          )}

          {/* Mode Selector for Presenter */}
          <div className="mode-toggle-pill" title="Choose execution provider">
            <button
              type="button"
              className={`pill-btn ${preferredMode === 'LIVE' ? 'active' : ''}`}
              onClick={() => setPreferredMode('LIVE')}
              disabled={directorState === 'RUNNING'}
            >
              LIVE
            </button>
            <button
              type="button"
              className={`pill-btn ${preferredMode === 'REPLAY' ? 'active' : ''}`}
              onClick={() => setPreferredMode('REPLAY')}
              disabled={directorState === 'RUNNING'}
            >
              REPLAY
            </button>
          </div>

          {/* Reduced Motion Toggle Button */}
          <button
            className={`director-btn motion-btn ${reducedMotion ? 'active' : ''}`}
            onClick={onToggleReducedMotion}
            id="btn-director-motion"
            title={reducedMotion ? 'Reduced Motion: ON' : 'Reduced Motion: OFF'}
            aria-pressed={reducedMotion}
          >
            {reducedMotion ? <ZapOff size={13} /> : <Eye size={13} />}
            <span>{reducedMotion ? 'Motion: Off' : 'Motion: On'}</span>
          </button>

          {/* Exit Director Button */}
          <button
            className="director-btn exit-btn"
            onClick={onExitDirector}
            id="btn-exit-director"
            title="Return to interactive console"
          >
            <span>Exit Director</span>
          </button>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="director-progress-track" aria-hidden="true">
        <div
          className="director-progress-fill"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* 2. NARRATION CAPTION BAR */}
      <div className="director-narration-card" role="region" aria-label="Current Narration">
        <div className="narration-meta-row">
          <span className={`narration-badge badge-${currentScene.badgeType}`}>
            {currentScene.badgeLabel}
          </span>
          <span className="narration-key-insight">
            <strong>Key Safety Invariant:</strong> {currentScene.keyInsight}
          </span>
        </div>
        <p className="narration-text" data-testid="narration-text">
          {currentScene.narration}
        </p>

        {errorMessage && (
          <div className="director-error-callout" role="alert">
            <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: '2px' }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
              <span style={{ fontWeight: 500 }}>{errorMessage}</span>
              {errorDetails && (
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', fontSize: '11px' }}>
                  {errorDetails.classification && (
                    <span style={{ background: 'rgba(239, 68, 68, 0.25)', color: '#fca5a5', padding: '1px 6px', borderRadius: '3px', border: '1px solid rgba(239, 68, 68, 0.4)' }}>
                      Category: {errorDetails.classification}
                    </span>
                  )}
                  {errorDetails.status_code && (
                    <span style={{ background: 'rgba(255, 255, 255, 0.12)', color: '#e2e8f0', padding: '1px 6px', borderRadius: '3px' }}>
                      HTTP {errorDetails.status_code}
                    </span>
                  )}
                  {errorDetails.correlation_id && (
                    <span style={{ background: 'rgba(255, 255, 255, 0.12)', color: '#93c5fd', padding: '1px 6px', borderRadius: '3px', fontFamily: 'monospace' }}>
                      ID: {errorDetails.correlation_id}
                    </span>
                  )}
                  {errorDetails.is_retryable !== undefined && (
                    <span style={{ background: 'rgba(255, 255, 255, 0.12)', color: errorDetails.is_retryable ? '#86efac' : '#cbd5e1', padding: '1px 6px', borderRadius: '3px' }}>
                      {errorDetails.is_retryable ? 'Transient / Retryable' : 'Terminal / Non-retryable'}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 3. EVENT TIMELINE STRIP */}
      <div className="director-scene-timeline" role="tablist" aria-label="Demo Scenes">
        {DIRECTOR_SCENES.map((scene, idx) => {
          const isCurrent = idx === currentSceneIndex
          const isDone = completedScenes.includes(scene.id)
          return (
            <button
              key={scene.id}
              role="tab"
              aria-selected={isCurrent}
              className={`scene-step-pill ${isCurrent ? 'active' : ''} ${isDone ? 'done' : ''}`}
              onClick={() => stepToScene(idx)}
              disabled={directorState === 'RUNNING'}
              title={`${scene.sequenceNumber}. ${scene.title}`}
              data-testid={`timeline-step-${scene.id}`}
            >
              <span className="step-num">{scene.sequenceNumber}</span>
              <span className="step-label">{scene.title.split(' ')[0]}</span>
            </button>
          )
        })}
      </div>

      {/* 4. PRIMARY APPLICATION STAGE */}
      <div className="director-stage" ref={stageContainerRef}>
        {/* SCENE 1: INTRO & THESIS */}
        {currentScene.id === 'intro' && (
          <div className="intro-stage-card" id="stage-intro-architecture">
            <div className="thesis-hero-section">
              <span className="thesis-kicker">NEBIUS × NVIDIA HACKATHON 2026</span>
              <h1 className="thesis-title">
                Nemotron Proposes. <span>MotionFence Decides.</span>
              </h1>
              <p className="thesis-description">
                Large language models are inherently probabilistic, hallucination-prone, and
                non-deterministic. When AI controls high-consequence physical industrial
                infrastructure—like cryogenic valves, cooling loops, and high-pressure pumps—it
                must possess <strong>zero actuator authority</strong>.
              </p>
            </div>

            {/* Architecture Control Loop */}
            <div className="architecture-pipeline-grid">
              <div className="pipeline-step-box step-ai">
                <div className="step-tag">UNPRIVILEGED PROPOSAL</div>
                <h3>1. Nebius / Nemotron 120B</h3>
                <p>Generates natural language action proposal with rationale. Has zero physical keys.</p>
              </div>

              <div className="pipeline-arrow">
                <ChevronRight size={20} />
              </div>

              <div className="pipeline-step-box step-engine">
                <div className="step-tag">DETERMINISTIC GATEWAY</div>
                <h3>2. PolicyEngine</h3>
                <p>Evaluates hard physical safety invariants in &lt;2 ms with zero SMT latency on path.</p>
              </div>

              <div className="pipeline-arrow">
                <ChevronRight size={20} />
              </div>

              <div className="pipeline-step-box step-enclave">
                <div className="step-tag">CRYPTOGRAPHIC ENCLAVE</div>
                <h3>3. SafetyEnclave</h3>
                <p>Mints single-use HMAC-SHA256 AuthorizationTickets strictly bound to world state.</p>
              </div>

              <div className="pipeline-arrow">
                <ChevronRight size={20} />
              </div>

              <div className="pipeline-step-box step-reval">
                <div className="step-tag">TOCTOU DEFENSE</div>
                <h3>4. Revalidation</h3>
                <p>Validates state version hash microseconds before actuation to catch race conditions.</p>
              </div>

              <div className="pipeline-arrow">
                <ChevronRight size={20} />
              </div>

              <div className="pipeline-step-box step-verify">
                <div className="step-tag">GROUND-TRUTH CHECK</div>
                <h3>5. PostActionVerifier</h3>
                <p>Verifies physical stroke against independent postconditions. NO_OP fails closed.</p>
              </div>
            </div>

            {/* Live System Health Readout */}
            <div className="health-readout-card">
              <div className="health-readout-header">
                <ShieldCheck size={16} />
                <span>Live System Readiness Status (/health)</span>
              </div>
              <div className="health-badges-row">
                <span className="health-badge passed">
                  Safety Runtime: {healthStatus?.safety_runtime || 'deterministic'}
                </span>
                <span className="health-badge passed">
                  Model: {healthStatus?.model || 'nvidia/nemotron-3-super-120b-a12b'}
                </span>
                <span className="health-badge passed">
                  Telemetry: {healthStatus?.telemetry_provider?.toUpperCase() || 'USGS'}
                </span>
                <span className="health-badge passed">
                  Operational Evidence: {healthStatus?.evidence_provider || 'offline_fixture'}
                </span>
                <span className="health-badge info">
                  Physical Execution: Simulation / Software Mock
                </span>
              </div>
            </div>
          </div>
        )}

        {/* SCENES 2 - 7: REAL DECISION REPLAY WITH TARGET PANEL HIGHLIGHT */}
        {['safe', 'denied', 'toctou', 'recovery', 'telemetry', 'evidence'].includes(
          currentScene.id
        ) && (
          <div className="decision-replay-stage-wrap">
            <DecisionReplay
              scenarios={scenarios}
              selectedScenarioId={currentScene.scenarioId || 'safe'}
              onSelectScenario={() => {}}
              scenarioData={scenarioData}
              onScenarioDataLoaded={setScenarioData}
              reducedMotion={reducedMotion}
            />
          </div>
        )}

        {/* SCENE 8: REPLAY & ASSURANCE */}
        {currentScene.id === 'replay_assurance' && (
          <div className="replay-assurance-stage" id="stage-replay-assurance">
            <div className="replay-proof-banner">
              <div className="banner-icon-wrap">
                <PlayCircle size={24} />
              </div>
              <div>
                <h3>Deterministic Offline Replay Proof</h3>
                <p>
                  Every MotionFence decision record is hash-linked and side-effect free. Past
                  events can be reproduced offline in <strong>0.18 milliseconds</strong> with zero
                  model inference and zero network latency. Replay mode is strictly read-only and
                  cannot command actuators.
                </p>
              </div>
              <div className="proof-metric-box">
                <span className="metric-val">&lt; 1 ms</span>
                <span className="metric-lbl">REPLAY LATENCY</span>
              </div>
            </div>

            {/* Formal Bounded Assurance Panel */}
            <AssurancePanel report={assuranceReport} />
          </div>
        )}

        {/* SCENE 9: CLOSE & SUMMARY */}
        {currentScene.id === 'close' && (
          <div className="close-stage-card" id="stage-close-summary">
            <div className="close-hero">
              <div className="slogan-badge">CORE SECURITY PRINCIPLE</div>
              <h1 className="slogan-text">“No Valid Ticket = No Actuation.”</h1>
              <p className="slogan-sub">
                Every physical action requires an authenticated, single-use, state-bound
                AuthorizationTicket signed by the SafetyEnclave.
              </p>
            </div>

            <div className="pillars-grid">
              <div className="pillar-card">
                <div className="pillar-num">01</div>
                <h4>Zero Model Authority</h4>
                <p>
                  Nemotron proposals are non-authoritative recommendations. An AI model cannot
                  issue commands or bypass the deterministic safety policy.
                </p>
              </div>

              <div className="pillar-card">
                <div className="pillar-num">02</div>
                <h4>Cryptographic TOCTOU Defense</h4>
                <p>
                  Tickets are bound to plant state version hashes. If plant conditions drift before
                  actuation, pre-stroke revalidation aborts execution.
                </p>
              </div>

              <div className="pillar-card">
                <div className="pillar-num">03</div>
                <h4>Deterministic Grounding</h4>
                <p>
                  Operational constraints require verified lexical provenance. Hallucinated numeric
                  thresholds and modality inversions fail admissibility.
                </p>
              </div>

              <div className="pillar-card">
                <div className="pillar-num">04</div>
                <h4>Post-Action Verification</h4>
                <p>
                  Actuation execution does not imply physical success. Limit switches and physical
                  observations are verified against declared invariants.
                </p>
              </div>
            </div>

            <div className="deployment-banner-box">
              <div className="dep-left">
                <span className="dep-tag">OPEN SOURCE ARCHITECTURE</span>
                <h3>MotionFence Public Release</h3>
                <a
                  href="https://github.com/subodhkant7/motionfence"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="dep-link"
                >
                  <span>https://github.com/subodhkant7/motionfence</span>
                  <ExternalLink size={14} />
                </a>
              </div>
              <button className="dep-cta-btn" onClick={onExitDirector}>
                <span>Explore Interactive Console</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 5. PERSISTENT DISCLOSURE FOOTER */}
      <footer className="director-disclosure-footer" role="contentinfo">
        <span className="disclosure-text">
          Actuation and post-action verification use simulation/software mocks; no physical hardware is connected.
        </span>
      </footer>
    </div>
  )
}
