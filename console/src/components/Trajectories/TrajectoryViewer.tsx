import React, { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  GitBranch,
  Play,
  Pause,
  RotateCcw,
  SkipBack,
  SkipForward,
  Eye,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  ShieldAlert,
} from 'lucide-react'
import { DynamicTrajectoryData, TrajectoryStepData } from '../../types'

interface TrajectoryViewerProps {
  trajectories: DynamicTrajectoryData[]
  reducedMotion: boolean
}

export const TrajectoryViewer: React.FC<TrajectoryViewerProps> = ({ trajectories, reducedMotion }) => {
  const [selectedTrajIndex, setSelectedTrajIndex] = useState<number>(0)
  const [activeStepIndex, setActiveStepIndex] = useState<number>(0)
  const [isPlaying, setIsPlaying] = useState<boolean>(false)
  const timerRef = useRef<NodeJS.Timeout | null>(null)

  const currentTraj = trajectories[selectedTrajIndex] || null
  const steps = currentTraj?.timesteps || []
  const currentStep: TrajectoryStepData | null = steps[activeStepIndex] || null

  // Playback timer loop
  useEffect(() => {
    if (isPlaying && steps.length > 0) {
      timerRef.current = setInterval(() => {
        setActiveStepIndex((prev) => {
          if (prev >= steps.length - 1) {
            setIsPlaying(false)
            return prev
          }
          return prev + 1
        })
      }, 2000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [isPlaying, steps.length])

  // Reset step on trajectory change
  useEffect(() => {
    setActiveStepIndex(0)
    setIsPlaying(false)
  }, [selectedTrajIndex])

  if (!currentTraj || steps.length === 0) {
    return <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>No trajectories loaded.</div>
  }

  return (
    <div role="region" aria-label="Bounded Dynamic Trajectories Explorer">
      {/* Trajectory Selector & Controls */}
      <div className="transport-bar">
        <div className="scenario-picker">
          <label htmlFor="traj-select" style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Dynamic Physical Trajectory:
          </label>
          <select
            id="traj-select"
            className="picker-select"
            value={selectedTrajIndex}
            onChange={(e) => setSelectedTrajIndex(Number(e.target.value))}
          >
            {trajectories.map((t, i) => (
              <option key={t.trajectory_id} value={i}>
                [{t.trajectory_id.slice(0, 16)}] Depth {t.depth} — {t.description.slice(0, 48)}...
              </option>
            ))}
          </select>
        </div>

        <div className="playback-controls">
          <button className="icon-btn" onClick={() => setActiveStepIndex(0)} title="Restart">
            <RotateCcw size={14} />
          </button>
          <button
            className="icon-btn"
            onClick={() => setActiveStepIndex((prev) => Math.max(0, prev - 1))}
            disabled={activeStepIndex === 0}
            title="Step Back"
          >
            <SkipBack size={14} />
          </button>
          <button
            className={`play-btn ${!isPlaying ? 'paused' : ''}`}
            onClick={() => setIsPlaying(!isPlaying)}
          >
            {isPlaying ? <Pause size={14} /> : <Play size={14} />}
            <span>{isPlaying ? 'PAUSE' : 'PLAY'}</span>
          </button>
          <button
            className="icon-btn"
            onClick={() => setActiveStepIndex((prev) => Math.min(steps.length - 1, prev + 1))}
            disabled={activeStepIndex === steps.length - 1}
            title="Step Forward"
          >
            <SkipForward size={14} />
          </button>
          <span className="step-indicator">
            Step t{activeStepIndex} of t{steps.length - 1}
          </span>
        </div>
      </div>

      {/* Trajectory Overview Header */}
      <div style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', padding: '12px 18px', marginBottom: '20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginRight: '8px' }}>
            Exploration Depth Bound:
          </span>
          <span className="mono" style={{ fontSize: '13px', fontWeight: 700, color: '#38bdf8' }}>
            Depth {currentTraj.depth} Steps
          </span>
          <span style={{ margin: '0 8px', color: 'var(--text-muted)' }}>•</span>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{currentTraj.description}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Outcome:</span>
          <span className={`status-badge ${currentTraj.is_regression ? 'status-deny' : 'operational'}`}>
            {currentTraj.outcome}
          </span>
        </div>
      </div>

      {/* Timestep Scrubbing Track */}
      <div style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', padding: '14px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Temporal Trajectory Progress
          </span>
          <span className="mono" style={{ fontSize: '11px', color: '#38bdf8' }}>
            t{activeStepIndex} : {currentStep?.event_name}
          </span>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          {steps.map((st, idx) => {
            const isActive = idx === activeStepIndex
            const isFailing = currentTraj.failing_step_index === idx

            return (
              <div
                key={idx}
                onClick={() => {
                  setIsPlaying(false)
                  setActiveStepIndex(idx)
                }}
                style={{
                  flex: 1,
                  padding: '8px 10px',
                  backgroundColor: isActive ? 'rgba(56, 189, 248, 0.12)' : 'var(--bg-surface-elevated)',
                  border: `1px solid ${isActive ? '#38bdf8' : isFailing ? 'var(--status-deny-border)' : 'var(--border-subtle)'}`,
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  textAlign: 'center',
                  transition: 'all 150ms ease',
                }}
              >
                <div className="mono" style={{ fontSize: '11px', fontWeight: 700, color: isActive ? '#38bdf8' : 'var(--text-primary)' }}>
                  t{idx}
                </div>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', marginTop: '2px' }}>
                  {st.action || st.event_name}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Dual State Visualizer: Observed vs Hidden Ground Truth (Section 16 Requirement) */}
      <div className="stage-grid">
        {/* Panel 1: Observed State (What the runtime sees) */}
        <div className="console-card">
          <div className="console-card-header">
            <span className="console-card-title">
              <Eye size={14} />
              <span>1. Observed State (Runtime Telemetry Perception)</span>
            </span>
            <span className="status-badge operational" style={{ fontSize: '10px' }}>
              RUNTIME OBSERVABLE
            </span>
          </div>
          <div className="console-card-body">
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '10px' }}>
              State perceived by the runtime policy engine and sensors during timestep t{activeStepIndex}.
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
              <div className="barrier-item">
                <span className="barrier-name">Human Zone</span>
                <span className={`barrier-status ${currentStep?.observed_state.human_zone === 'CLEAR' ? 'pass' : 'blocked'}`}>
                  {currentStep?.observed_state.human_zone}
                </span>
              </div>
              <div className="barrier-item">
                <span className="barrier-name">Cooling Loop</span>
                <span className="barrier-status pass">{currentStep?.observed_state.cooling}</span>
              </div>
              <div className="barrier-item">
                <span className="barrier-name">Valve B</span>
                <span className="barrier-status pass">{currentStep?.observed_state.valve_b}</span>
              </div>
              <div className="barrier-item">
                <span className="barrier-name">State Version</span>
                <span className="barrier-status pass mono">v{currentStep?.observed_state.version}</span>
              </div>
            </div>

            <div style={{ marginTop: '12px', padding: '8px 10px', backgroundColor: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', fontSize: '11px' }}>
              <div>
                Action Proposal: <strong className="mono" style={{ color: '#38bdf8' }}>{currentStep?.action || 'NONE'}</strong>
              </div>
              <div style={{ marginTop: '4px' }}>
                Revalidation Status:{' '}
                <strong style={{ color: currentStep?.revalidation_passed ? 'var(--status-allow)' : 'var(--status-deny)' }}>
                  {currentStep?.revalidation_passed ? 'BARRIERS PASSED' : 'TOCTOU BLOCKED'}
                </strong>
              </div>
            </div>
          </div>
        </div>

        {/* Panel 2: Hidden Ground Truth (Physical Simulator Reality) */}
        <div className="console-card">
          <div className="console-card-header">
            <span className="console-card-title">
              <ShieldAlert size={14} />
              <span>2. Hidden Ground Truth (Physical Environment)</span>
            </span>
            <span className="status-badge read-only" style={{ fontSize: '10px' }}>
              SIMULATOR REALITY
            </span>
          </div>
          <div className="console-card-body">
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '10px' }}>
              True physical environment state (unknown to ungrounded models; used strictly for evaluation).
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
              <div className="barrier-item">
                <span className="barrier-name">Human Present</span>
                <span className="barrier-status" style={{ color: currentStep?.hidden_ground_truth.human_physically_present ? 'var(--status-deny)' : 'var(--status-allow)' }}>
                  {currentStep?.hidden_ground_truth.human_physically_present ? 'YES (HAZARD)' : 'NO'}
                </span>
              </div>
              <div className="barrier-item">
                <span className="barrier-name">Chiller Status</span>
                <span className="barrier-status pass">
                  {currentStep?.hidden_ground_truth.chiller_operational ? 'OPERATIONAL' : 'DEGRADED'}
                </span>
              </div>
              <div className="barrier-item">
                <span className="barrier-name">Valve Seated</span>
                <span className="barrier-status pass">
                  {currentStep?.hidden_ground_truth.valve_mechanically_seated ? 'SEATED' : 'UNSEATED'}
                </span>
              </div>
              <div className="barrier-item">
                <span className="barrier-name">Pressure Line</span>
                <span className="barrier-status pass">STEADY</span>
              </div>
            </div>

            {/* Injected Fault Indicator */}
            {currentStep?.fault && (
              <div style={{ marginTop: '12px', padding: '8px 10px', backgroundColor: 'var(--status-deny-bg)', border: '1px solid var(--status-deny-border)', borderRadius: 'var(--radius-sm)', fontSize: '11px', color: '#fca5a5' }}>
                <strong>Injected Environmental Fault:</strong> {currentStep.fault}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Trajectory Minimization / Prefix Isolation */}
      {currentTraj.failing_step_index !== null && currentTraj.failing_step_index !== undefined && (
        <div className="console-card" style={{ marginTop: '20px' }}>
          <div className="console-card-header">
            <span className="console-card-title">
              <GitBranch size={14} />
              <span>Delta-Debugging Trajectory Minimizer (Minimal Causal Prefix)</span>
            </span>
            <span className="status-badge status-deny" style={{ fontSize: '10px' }}>
              MINIMAL COUNTEREXAMPLE PREFIX
            </span>
          </div>
          <div className="console-card-body">
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {currentTraj.explanation}
            </div>
            <div style={{ marginTop: '8px', fontSize: '11px', color: 'var(--text-muted)' }}>
              Minimal prefix length: <strong>t0 .. t{currentTraj.failing_step_index}</strong> (isolated from depth {currentTraj.depth}).
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
