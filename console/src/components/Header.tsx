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
} from 'lucide-react'
import { ViewMode } from '../types'

interface HeaderProps {
  currentView: ViewMode
  onViewChange: (view: ViewMode) => void
  isLive: boolean
  reducedMotion: boolean
  onToggleReducedMotion: () => void
}

export const Header: React.FC<HeaderProps> = ({
  currentView,
  onViewChange,
  isLive,
  reducedMotion,
  onToggleReducedMotion,
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

          <span
            className={`status-badge ${isLive ? 'live' : 'offline-replay'}`}
            title={isLive ? 'Connected to live Python API adapter' : 'Running from static canonical audit records'}
          >
            <PlayCircle size={12} />
            <span>{isLive ? 'LIVE BACKEND' : 'OFFLINE DETERMINISTIC REPLAY'}</span>
          </span>
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
            <span>Assurance (44 Props)</span>
          </button>
        </nav>

        <div className="nav-controls">
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
