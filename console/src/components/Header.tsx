import React from 'react'
import {
  ShieldAlert,
  PlayCircle,
  FileCheck2,
  GitBranch,
  ShieldCheck,
  Eye,
  Activity,
  ZapOff,
  Zap,
  Radio,
} from 'lucide-react'
import { ViewMode, ExecutionMode } from '../types'

interface HeaderProps {
  currentView: ViewMode
  onViewChange: (view: ViewMode) => void
  isLive: boolean
  executionMode?: ExecutionMode
  reducedMotion: boolean
  onToggleReducedMotion: () => void
  onOpenDirector?: () => void
  onOpenSafetyLab?: () => void
}

export const Header: React.FC<HeaderProps> = ({
  currentView,
  onViewChange,
  isLive,
  executionMode = isLive ? 'LIVE' : 'REPLAY',
  reducedMotion,
  onToggleReducedMotion,
  onOpenDirector,
  onOpenSafetyLab,
}) => {
  return (
    <header className="console-header" role="banner">
      <div className="header-top-row">
        <div className="brand-section">
          <div className="brand-logo-badge" title="Deterministic Runtime Authorization Gateway">
            <ShieldCheck size={16} />
            <span>MF-GATEWAY</span>
          </div>
          <div>
            <h1 className="brand-title">MotionFence Judge Console</h1>
            <p className="brand-subtitle">
              Deterministic Runtime Authorization Layer for AI-Generated Physical Actions
            </p>
          </div>
        </div>

        <div className="header-badges">
          <span className="status-badge operational" title="Core safety rules active">
            <Activity size={12} />
            <span>STATUS: OPERATIONAL</span>
          </span>

          <span
            className="status-badge read-only"
            title="UI possesses ZERO actuation authority or ticket minting capability"
          >
            <ShieldAlert size={12} />
            <span>READ-ONLY / ZERO AUTHORITY</span>
          </span>

          {/* Phase 2N: Prominently distinguish LIVE / REPLAY / OFFLINE TEST */}
          {executionMode === 'LIVE' ? (
            <span
              className="mode-badge live-mode"
              title="LIVE MODE: Real Nebius Token Factory / Nemotron 120B model generates unprivileged proposals"
            >
              <Zap size={13} />
              <span>LIVE — NEBIUS / NEMOTRON</span>
            </span>
          ) : executionMode === 'REPLAY' ? (
            <span
              className="mode-badge replay-mode"
              title="REPLAY MODE: Reproducing real recorded live execution with 0 network calls and 0 actuation authority"
            >
              <PlayCircle size={13} />
              <span>REPLAY — RECORDED LIVE EXECUTION (OFFLINE DETERMINISTIC REPLAY)</span>
            </span>
          ) : (
            <span
              className="mode-badge offline-test-mode"
              title="OFFLINE TEST MODE: Deterministic CI synthetic fixtures with 0 network calls"
            >
              <PlayCircle size={13} />
              <span>OFFLINE TEST</span>
            </span>
          )}
        </div>
      </div>

      <div className="nav-tabs-row">
        <nav className="nav-tabs" role="tablist" aria-label="Main Navigation">
          <button
            role="tab"
            aria-selected={currentView === 'replay'}
            className={`nav-tab-btn ${currentView === 'replay' ? 'active' : ''}`}
            onClick={() => onViewChange('replay')}
            id="tab-replay"
          >
            <PlayCircle size={14} />
            <span>Decision Replay</span>
          </button>

          <button
            role="tab"
            aria-selected={currentView === 'firewall'}
            className={`nav-tab-btn ${currentView === 'firewall' ? 'active' : ''}`}
            onClick={() => onViewChange('firewall')}
            id="tab-firewall"
          >
            <FileCheck2 size={14} />
            <span>Policy Firewall</span>
          </button>

          <button
            role="tab"
            aria-selected={currentView === 'trajectories'}
            className={`nav-tab-btn ${currentView === 'trajectories' ? 'active' : ''}`}
            onClick={() => onViewChange('trajectories')}
            id="tab-trajectories"
          >
            <GitBranch size={14} />
            <span>Trajectories</span>
          </button>

          <button
            role="tab"
            aria-selected={currentView === 'assurance'}
            className={`nav-tab-btn ${currentView === 'assurance' ? 'active' : ''}`}
            onClick={() => onViewChange('assurance')}
            id="tab-assurance"
          >
            <ShieldCheck size={14} />
            <span>Assurance (51 Props)</span>
          </button>
        </nav>

        <div className="nav-controls">
          {onOpenSafetyLab && (
            <button
              className="icon-btn safetylab-trigger-btn"
              onClick={onOpenSafetyLab}
              title="Open Public Safety Lab & Quantitative Benchmark"
              id="btn-open-safetylab"
              style={{
                background: 'rgba(14, 165, 233, 0.15)',
                borderColor: 'rgba(56, 189, 248, 0.5)',
                color: '#38bdf8',
                fontWeight: 600,
              }}
            >
              <ShieldCheck size={13} />
              <span>Safety Lab & Benchmark</span>
            </button>
          )}

          {onOpenDirector && (
            <button
              className="icon-btn director-trigger-btn"
              onClick={onOpenDirector}
              title="Open 1-Click Demo Director (Recording Mode)"
              id="btn-open-director"
            >
              <Radio size={13} className="director-pulse-icon" />
              <span>Demo Director (1-Click)</span>
            </button>
          )}

          <button
            className={`icon-btn ${reducedMotion ? 'active' : ''}`}
            onClick={onToggleReducedMotion}
            title={reducedMotion ? 'Reduced Motion: ON' : 'Reduced Motion: OFF'}
            aria-pressed={reducedMotion}
          >
            {reducedMotion ? <ZapOff size={13} /> : <Eye size={13} />}
            <span>{reducedMotion ? 'Motion: Reduced' : 'Motion: Standard'}</span>
          </button>
        </div>
      </div>
    </header>
  )
}
