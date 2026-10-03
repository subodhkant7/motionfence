import React, { useState } from 'react'
import {
  Waves,
  ExternalLink,
  ShieldCheck,
  CheckCircle2,
  Clock,
  Hash,
  MapPin,
  AlertCircle,
  Info,
  ChevronDown,
  ChevronRight,
  Layers,
  ArrowRight,
} from 'lucide-react'
import { TelemetryObservation } from '../../types'

interface TelemetryObservationPanelProps {
  observation?: TelemetryObservation
  snapshots?: TelemetryObservation[]
  environmentalContext?: {
    context_name: string
    classification: string
    threshold_value?: number
    rule_id?: string
    deterministic_hash?: string
  }
}

export const TelemetryObservationPanel: React.FC<TelemetryObservationPanelProps> = ({
  observation,
  snapshots = [],
  environmentalContext,
}) => {
  const [showDrilldown, setShowDrilldown] = useState<boolean>(true)
  const [showRawJson, setShowRawJson] = useState<boolean>(false)

  // Use primary observation or fallback to first snapshot
  const activeObs = observation || (snapshots.length > 0 ? snapshots[0] : null)

  if (!activeObs) {
    return null
  }

  const allSnapshots = snapshots.length > 0 ? snapshots : [activeObs]
  const isFresh = activeObs.freshness === 'FRESH'
  const isStale = activeObs.freshness === 'STALE'

  return (
    <div className="console-card" style={{ borderColor: 'rgba(14, 165, 233, 0.4)' }} role="region" aria-label="Real-World Telemetry Panel">
      <div className="console-card-header" style={{ backgroundColor: 'rgba(14, 165, 233, 0.08)' }}>
        <span className="console-card-title">
          <Waves size={15} className="text-sky" />
          <span>REAL-WORLD OBSERVATION (USGS WATER DATA OGC API)</span>
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            className={`status-badge ${isFresh ? 'operational' : isStale ? 'status-deny' : 'read-only'}`}
            style={{ fontSize: '10px' }}
          >
            {isFresh ? <CheckCircle2 size={10} /> : <AlertCircle size={10} />}
            <span>FRESHNESS: {activeObs.freshness}</span>
          </span>
          <span className="status-badge read-only" style={{ fontSize: '10px', color: '#38bdf8' }}>
            OBSERVATION ONLY — 0 ACTUATOR AUTHORITY
          </span>
        </div>
      </div>

      <div className="console-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {/* Architectural Distinction Banner */}
        <div
          style={{
            backgroundColor: 'rgba(15, 23, 42, 0.7)',
            border: '1px solid rgba(14, 165, 233, 0.25)',
            borderRadius: 'var(--radius-sm)',
            padding: '8px 12px',
            fontSize: '11px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '8px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#7dd3fc' }}>
            <Info size={13} />
            <span>
              <strong>CANONICAL SEPARATION:</strong> REAL PUBLIC OBSERVATION ≠ MODELED PLANT STATE &nbsp;|&nbsp; REAL DATA ≠ AUTOMATIC AUTHORIZATION
            </span>
          </div>
          <div className="mono" style={{ color: '#94a3b8' }}>
            SOURCE: {activeObs.provider} OGC API v1
          </div>
        </div>

        {/* Continuous Observation Metrics Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '10px' }}>
          {allSnapshots.map((snap) => (
            <div
              key={snap.observation_id}
              style={{
                backgroundColor: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: '12px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  {snap.parameter_name || `PARAM ${snap.parameter_code}`}
                </span>
                <span className="mono" style={{ fontSize: '10px', color: '#38bdf8' }}>
                  Code: {snap.parameter_code}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
                <span className="mono" style={{ fontSize: '24px', fontWeight: 700, color: '#38bdf8' }}>
                  {snap.normalized_value?.toLocaleString() ?? snap.raw_value}
                </span>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>
                  {snap.unit}
                </span>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                <span>Observed:</span>
                <span className="mono" style={{ color: 'var(--text-secondary)' }}>
                  {snap.observed_at ? new Date(snap.observed_at).toLocaleTimeString() : 'N/A'} (15-min series)
                </span>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                <span>Approval:</span>
                <span className="mono" style={{ color: '#fbbf24' }}>
                  {snap.approval_status || 'Provisional'}
                </span>
              </div>
            </div>
          ))}

          {/* Environmental Context Derivation Card (if present) */}
          {environmentalContext && (
            <div
              style={{
                backgroundColor: 'rgba(34, 197, 94, 0.06)',
                border: '1px solid rgba(34, 197, 94, 0.25)',
                borderRadius: 'var(--radius-sm)',
                padding: '12px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, color: '#4ade80', textTransform: 'uppercase' }}>
                  DERIVED ENVIRONMENTAL CONTEXT
                </span>
                <span className="mono" style={{ fontSize: '10px', color: '#86efac' }}>
                  DETERMINISTIC
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
                <span className="mono" style={{ fontSize: '18px', fontWeight: 700, color: '#22c55e' }}>
                  {environmentalContext.classification}
                </span>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                <span>Regime:</span>
                <span className="mono" style={{ color: 'var(--text-secondary)' }}>
                  {environmentalContext.context_name}
                </span>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                <span>Rule ID:</span>
                <span className="mono" style={{ color: 'var(--text-secondary)' }}>
                  {environmentalContext.rule_id || 'RULE_USGS_FLOW_STAGE_01'}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Monitoring Location & Station Information */}
        <div
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-sm)',
            padding: '10px 14px',
            fontSize: '11px',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <MapPin size={13} className="text-sky" />
              <span>
                <strong>Station:</strong> {activeObs.monitoring_location_name || activeObs.monitoring_location_id}
              </span>
              <span className="mono" style={{ color: '#38bdf8' }}>
                ({activeObs.monitoring_location_id})
              </span>
            </div>

            {activeObs.source_url && (
              <a
                href={activeObs.source_url}
                target="_blank"
                rel="noreferrer noopener"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  color: '#38bdf8',
                  textDecoration: 'none',
                  fontSize: '11px',
                }}
              >
                <span>USGS OGC API Endpoint</span>
                <ExternalLink size={11} />
              </a>
            )}
          </div>

          <div style={{ display: 'flex', gap: '16px', color: 'var(--text-muted)', flexWrap: 'wrap' }}>
            <span>
              Retrieved: <strong className="mono" style={{ color: 'var(--text-secondary)' }}>{new Date(activeObs.retrieved_at).toLocaleString()}</strong>
            </span>
            <span>
              Freshness Age: <strong className="mono" style={{ color: 'var(--text-secondary)' }}>{Math.round(activeObs.freshness_age_seconds || 0)}s</strong>
            </span>
            <span>
              Provenance Hash: <strong className="mono" style={{ color: '#94a3b8' }}>{activeObs.provenance_hash?.slice(0, 16)}...</strong>
            </span>
          </div>
        </div>

        {/* Section 24: Provenance Drill-Down Traceable Chain */}
        <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '10px' }}>
          <button
            onClick={() => setShowDrilldown(!showDrilldown)}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '11px',
              fontWeight: 600,
              color: '#38bdf8',
              padding: '0',
            }}
          >
            {showDrilldown ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <span>PROVENANCE DRILL-DOWN TRACEABLE CHAIN (SECTION 24)</span>
          </button>

          {showDrilldown && (
            <div
              style={{
                marginTop: '10px',
                backgroundColor: 'rgba(15, 23, 42, 0.6)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: '10px 14px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '6px',
                  fontSize: '11px',
                }}
              >
                <span className="chain-node" style={{ color: '#38bdf8' }}>1. Source: USGS</span>
                <ArrowRight size={11} className="text-muted" />
                <span className="chain-node" style={{ color: '#38bdf8' }}>2. Station: {activeObs.monitoring_location_id}</span>
                <ArrowRight size={11} className="text-muted" />
                <span className="chain-node" style={{ color: '#38bdf8' }}>3. Param: {activeObs.parameter_code}</span>
                <ArrowRight size={11} className="text-muted" />
                <span className="chain-node" style={{ color: '#4ade80' }}>4. Obs: {activeObs.normalized_value} {activeObs.unit}</span>
                <ArrowRight size={11} className="text-muted" />
                <span className="chain-node" style={{ color: '#fde047' }}>5. Freshness: {activeObs.freshness}</span>
                <ArrowRight size={11} className="text-muted" />
                <span className="chain-node" style={{ color: '#c084fc' }}>6. Evidence: ev_usgs_{activeObs.parameter_code}</span>
                <ArrowRight size={11} className="text-muted" />
                <span className="chain-node" style={{ color: '#38bdf8' }}>7. Policy Context: {environmentalContext?.classification || 'NORMAL_FLOW'}</span>
              </div>
            </div>
          )}
        </div>

        {/* Section 34 Semantic Honesty Statement */}
        <div
          style={{
            fontSize: '11px',
            color: 'var(--text-muted)',
            fontStyle: 'italic',
            borderLeft: '2px solid rgba(14, 165, 233, 0.4)',
            paddingLeft: '10px',
          }}
        >
          <strong>Semantic Honesty Guarantee:</strong> MotionFence ingests real-world public telemetry as externally sourced evidence while preserving provenance and freshness. It does NOT claim USGS is an internal plant sensor, nor does it grant external data actuation authority.
        </div>
      </div>
    </div>
  )
}
