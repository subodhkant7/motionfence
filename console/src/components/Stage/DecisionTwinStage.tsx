import React, { useState, useEffect, useRef } from 'react'
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  RotateCcw,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  Shield,
  Key,
  Cpu,
  Layers,
  Radio,
  ExternalLink,
  ChevronRight,
  ChevronDown,
  Zap,
} from 'lucide-react'
import { ScenarioData } from '../../types'
import { PresentationFrame, PresentationTimeline } from '../../types/presentation'
import { derivePresentationTimeline } from '../../services/frameDerivation'
import { WebGLIndustrialPlant } from '../DigitalTwin/WebGLIndustrialPlant'
import './DecisionTwinStage.css'

interface DecisionTwinStageProps {
  scenarioId: string
  scenarioData: ScenarioData | null
  reducedMotion?: boolean
  autoPlay?: boolean
  onStageChange?: (stageIndex: number) => void
  onOutcomeDerived?: (outcome: string) => void
}

export const DecisionTwinStage: React.FC<DecisionTwinStageProps> = ({
  scenarioId,
  scenarioData,
  reducedMotion = false,
  autoPlay = false,
  onStageChange,
  onOutcomeDerived,
}) => {
  const [timeline, setTimeline] = useState<PresentationTimeline>(() =>
    derivePresentationTimeline(scenarioId, scenarioData)
  )
  const [activeStageIndex, setActiveStageIndex] = useState<number>(0)
  const [isPlaying, setIsPlaying] = useState<boolean>(autoPlay)
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Re-derive timeline when scenario changes
  useEffect(() => {
    const tl = derivePresentationTimeline(scenarioId, scenarioData)
    setTimeline(tl)
    setActiveStageIndex(0)
    setIsPlaying(autoPlay)
    if (onOutcomeDerived) {
      onOutcomeDerived(tl.overallOutcome)
    }
  }, [scenarioId, scenarioData, autoPlay, onOutcomeDerived])

  // Current frame
  const currentFrame: PresentationFrame =
    timeline.frames[activeStageIndex] || timeline.frames[0]

  // Notify parent of stage changes
  useEffect(() => {
    if (onStageChange) {
      onStageChange(activeStageIndex)
    }
  }, [activeStageIndex, onStageChange])

  // Playback loop
  useEffect(() => {
    if (isPlaying) {
      timerRef.current = setInterval(() => {
        setActiveStageIndex((prev) => {
          if (prev >= timeline.frames.length - 1) {
            setIsPlaying(false)
            return prev
          }
          return prev + 1
        })
      }, 1900 / playbackSpeed)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [isPlaying, playbackSpeed, timeline.frames.length])

  const handleStep = (delta: number) => {
    setIsPlaying(false)
    setActiveStageIndex((prev) => {
      const next = prev + delta
      if (next < 0) return 0
      if (next >= timeline.frames.length) return timeline.frames.length - 1
      return next
    })
  }

  const handleReset = () => {
    setIsPlaying(false)
    setActiveStageIndex(0)
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'PASSED':
        return (
          <span className="stage-pill pill-passed">
            <CheckCircle size={11} />
            <span>PASSED</span>
          </span>
        )
      case 'DENIED':
        return (
          <span className="stage-pill pill-denied">
            <XCircle size={11} />
            <span>DENIED</span>
          </span>
        )
      case 'BLOCKED':
        return (
          <span className="stage-pill pill-blocked">
            <AlertTriangle size={11} />
            <span>BLOCKED</span>
          </span>
        )
      case 'FAILED':
        return (
          <span className="stage-pill pill-failed">
            <XCircle size={11} />
            <span>FAILED</span>
          </span>
        )
      case 'NOT_APPLICABLE':
        return <span className="stage-pill pill-na">N/A</span>
      default:
        return <span className="stage-pill pill-pending">PENDING</span>
    }
  }

  return (
    <div className="decision-twin-stage" data-testid="decision-twin-stage">
      {/* 1. COMPACT TOP HEADER BAR */}
      <header className="stage-compact-header">
        <div className="header-left-cluster">
          <div className="scenario-badge-title">
            <span className={`outcome-chip outcome-${timeline.overallOutcome.toLowerCase()}`}>
              {timeline.overallOutcome}
            </span>
            <h2 className="stage-scenario-heading">{timeline.scenarioTitle}</h2>
          </div>
          <span className="provenance-tag">
            {currentFrame.provenanceMode === 'LIVE' ? (
              <span className="tag-live">
                <Radio size={10} className="pulse-dot" /> LIVE PROVIDER
              </span>
            ) : (
              <span className="tag-replay">DETERMINISTIC REPLAY</span>
            )}
          </span>
        </div>

        {/* Playback Transport Controls */}
        <div className="stage-playback-toolbar">
          <button
            type="button"
            className="transport-btn"
            onClick={() => handleStep(-1)}
            disabled={activeStageIndex === 0}
            title="Step to previous decision stage"
            aria-label="Previous Stage"
          >
            <SkipBack size={13} />
          </button>

          <button
            type="button"
            className={`transport-btn play-btn ${isPlaying ? 'active' : ''}`}
            onClick={() => setIsPlaying(!isPlaying)}
            title={isPlaying ? 'Pause playback' : 'Play synchronized execution'}
            aria-label={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? <Pause size={13} /> : <Play size={13} />}
            <span>{isPlaying ? 'Pause' : 'Play'}</span>
          </button>

          <button
            type="button"
            className="transport-btn"
            onClick={() => handleStep(1)}
            disabled={activeStageIndex >= timeline.frames.length - 1}
            title="Step to next decision stage"
            aria-label="Next Stage"
          >
            <SkipForward size={13} />
          </button>

          <button
            type="button"
            className="transport-btn reset-btn"
            onClick={handleReset}
            title="Reset to Stage 1"
            aria-label="Reset"
          >
            <RotateCcw size={13} />
          </button>

          <div className="stage-step-counter">
            <span className="step-num" data-testid="active-step-counter">{activeStageIndex + 1}</span>
            <span className="step-total">/ 10</span>
          </div>

          <div className="speed-toggle-group">
            {[1, 1.5, 2].map((s) => (
              <button
                key={s}
                type="button"
                className={`speed-btn ${playbackSpeed === s ? 'active' : ''}`}
                onClick={() => setPlaybackSpeed(s)}
              >
                {s}x
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* 2. SYNCHRONIZED SPLIT-SCREEN CONTAINER */}
      <div className="stage-split-body">
        {/* LEFT RAIL: 10 DECISION EXECUTION STAGES (38% WIDTH) */}
        <aside className="decision-execution-rail" aria-label="Decision Stages">
          <div className="rail-header">
            <Shield size={13} />
            <span>DECISION EXECUTION RAIL</span>
            <span className="rail-badge">ZERO AUTHORITY GATEWAY</span>
          </div>

          <div className="stages-scroll-list">
            {timeline.frames.map((frame, idx) => {
              const isActive = idx === activeStageIndex
              const isPast = idx < activeStageIndex

              return (
                <div
                  key={frame.stageKey}
                  className={`stage-row-item ${isActive ? 'is-active' : ''} ${
                    isPast ? 'is-past' : ''
                  }`}
                  onClick={() => {
                    setIsPlaying(false)
                    setActiveStageIndex(idx)
                  }}
                  data-testid={`stage-item-${frame.stageKey}`}
                >
                  <div className="stage-row-summary">
                    <div className="stage-row-left">
                      <span className="stage-index-num">{idx + 1}</span>
                      <div className="stage-text-block">
                        <span className="stage-label">{frame.stageLabel}</span>
                        <span className="stage-sub">{frame.stageSubtitle}</span>
                      </div>
                    </div>
                    <div className="stage-row-right">
                      {getStatusBadge(frame.stageStatus)}
                      {isActive ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </div>
                  </div>

                  {/* Expanded Stage Evidence Card */}
                  {isActive && (
                    <div className="stage-expanded-card" data-testid="stage-expanded-content">
                      {/* FRAME 2: PROPOSAL */}
                      {frame.proposal && (
                        <div className="card-section proposal-card">
                          <div className="card-sec-header">
                            <Cpu size={12} />
                            <span>AI Proposal Payload ({frame.proposal.model})</span>
                            <span className="unprivileged-tag">UNPRIVILEGED</span>
                          </div>
                          <div className="card-data-row">
                            <span className="data-key">Command:</span>
                            <span className="data-val highlight-cmd">{frame.proposal.action}</span>
                            <span className="data-key">Target:</span>
                            <span className="data-val">{frame.proposal.target}</span>
                          </div>
                          <p className="card-rationale">"{frame.proposal.rationale}"</p>
                          <div className="card-footer-note">
                            Model has zero actuator credentials; cannot command hardware.
                          </div>
                        </div>
                      )}

                      {/* FRAME 3: POLICY */}
                      {frame.policy && (
                        <div className={`card-section policy-card ${frame.policy.decision === 'DENY' ? 'is-deny' : 'is-allow'}`}>
                          <div className="card-sec-header">
                            <Shield size={12} />
                            <span>Deterministic Policy Firewall</span>
                            <span className={`decision-badge badge-${frame.policy.decision.toLowerCase()}`}>
                              DECISION: {frame.policy.decision}
                            </span>
                          </div>
                          <p className="policy-reason">{frame.policy.reason}</p>
                          {frame.policy.ruleViolations.length > 0 && (
                            <div className="violations-box">
                              {frame.policy.ruleViolations.map((v, i) => (
                                <div key={i} className="violation-line">
                                  <AlertTriangle size={11} />
                                  <span>{v}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* FRAME 4: AUTHORIZATION */}
                      {frame.authorization && (
                        <div className="card-section auth-card">
                          <div className="card-sec-header">
                            <Key size={12} />
                            <span>Cryptographic Execution Ticket</span>
                            <span className={`ticket-status-badge status-${frame.authorization.status.toLowerCase()}`}>
                              {frame.authorization.status}
                            </span>
                          </div>
                          {frame.authorization.ticketId ? (
                            <div className="ticket-meta-grid">
                              <div>
                                <span className="data-key">Ticket ID:</span>
                                <span className="data-val mono">{frame.authorization.ticketId}</span>
                              </div>
                              <div>
                                <span className="data-key">State Hash:</span>
                                <span className="data-val mono">{frame.authorization.plantHash}</span>
                              </div>
                              <div>
                                <span className="data-key">Algorithm:</span>
                                <span className="data-val">HMAC-SHA256 (Single-Use)</span>
                              </div>
                            </div>
                          ) : (
                            <p className="no-ticket-text">
                              Policy denied proposal. Zero authorization tickets issued.
                            </p>
                          )}
                        </div>
                      )}

                      {/* FRAME 5: WORLD CHANGE */}
                      {frame.worldChange && (
                        <div className="card-section world-card">
                          <div className="card-sec-header">
                            <Layers size={12} />
                            <span>World State Evolution</span>
                            <span className="version-pill">
                              v{frame.worldChange.previousVersion} → v{frame.worldChange.newVersion}
                            </span>
                          </div>
                          <p className="world-desc">{frame.worldChange.description}</p>
                        </div>
                      )}

                      {/* FRAME 6: REVALIDATION */}
                      {frame.revalidation && (
                        <div className={`card-section reval-card ${frame.revalidation.status === 'WORLD_STATE_CHANGED' ? 'drift-detected' : ''}`}>
                          <div className="card-sec-header">
                            <Clock size={12} />
                            <span>Pre-Stroke Revalidation (t_exec)</span>
                            <span className={`reval-badge status-${frame.revalidation.status.toLowerCase()}`}>
                              {frame.revalidation.status}
                            </span>
                          </div>
                          <div className="hash-compare-grid">
                            <div>
                              <span className="data-key">Bound Hash:</span>
                              <span className="data-val mono">{frame.revalidation.expectedHash}</span>
                            </div>
                            <div>
                              <span className="data-key">Live Hash:</span>
                              <span className="data-val mono">{frame.revalidation.actualHash}</span>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* FRAME 7: EXECUTION */}
                      {frame.execution && (
                        <div className="card-section exec-card">
                          <div className="card-sec-header">
                            <Zap size={12} />
                            <span>Actuator Interface</span>
                            <span className={`exec-badge status-${frame.execution.status.toLowerCase()}`}>
                              {frame.execution.status}
                            </span>
                          </div>
                          <div className="card-data-row">
                            <span className="data-key">Target Actuator:</span>
                            <span className="data-val">{frame.execution.actuatorId}</span>
                            <span className="data-key">Fault Injected:</span>
                            <span className="data-val">{frame.execution.faultInjected}</span>
                          </div>
                        </div>
                      )}

                      {/* FRAME 8: VERIFICATION */}
                      {frame.verification && (
                        <div className="card-section verif-card">
                          <div className="card-sec-header">
                            <CheckCircle size={12} />
                            <span>Independent Limit Switch Verification</span>
                            <span className={`verif-badge status-${frame.verification.status.toLowerCase()}`}>
                              {frame.verification.status}
                            </span>
                          </div>
                          <div className="card-data-row">
                            <span className="data-key">Readback:</span>
                            <span className="data-val">{frame.verification.limitSwitchReadback || 'N/A'}</span>
                          </div>
                        </div>
                      )}

                      {/* FRAME 9: RECOVERY */}
                      {frame.recovery && frame.recovery.status !== 'NOT_APPLICABLE' && (
                        <div className="card-section recovery-card">
                          <div className="card-sec-header">
                            <AlertTriangle size={12} />
                            <span>Autonomous Safe Recovery</span>
                            <span className="recovery-pill">RECOVERED</span>
                          </div>
                          <p className="recovery-path">{frame.recovery.recoveryPath}</p>
                          {frame.recovery.disclosureNotice && (
                            <div className="disclosure-banner">
                              <small>{frame.recovery.disclosureNotice}</small>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </aside>

        {/* RIGHT VIEWPORT: INTERACTIVE 3D WEBGL PLANT (62% WIDTH) */}
        <main className="plant-viewport-pane" aria-label="3D Industrial Plant Digital Twin">
          <WebGLIndustrialPlant
            plantState={currentFrame.plantState}
            cameraPreset={currentFrame.cameraPreset}
            height="100%"
            interactive={true}
            showHud={true}
          />
        </main>
      </div>
    </div>
  )
}
