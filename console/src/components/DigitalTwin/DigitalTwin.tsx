import React from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Droplets,
  Gauge,
  Lock,
  Power,
  Shield,
  ShieldAlert,
  ShieldCheck,
  UserCheck,
  UserX,
  Waves,
  Zap,
} from 'lucide-react'
import { DigitalTwinPlantState, ExecutionMode, TelemetryObservation } from '../../types'

interface DigitalTwinProps {
  plantState: DigitalTwinPlantState
  activeStageIndex: number
  scenarioId: string
  executionMode?: ExecutionMode
  reducedMotion?: boolean
  telemetryObservation?: TelemetryObservation
  externalObservations?: Record<string, any>
}

export const DigitalTwin: React.FC<DigitalTwinProps> = ({
  plantState,
  activeStageIndex,
  scenarioId,
  executionMode = 'LIVE',
  reducedMotion = false,
  telemetryObservation,
  externalObservations,
}) => {
  const isPumpActive = plantState.pump_state === 'ACTIVE'
  const isValveOpen = plantState.valve_b_state === 'OPEN'
  const isValveClosing = plantState.valve_b_state === 'CLOSING'
  const isHumanZoneClear = plantState.human_zone === 'CLEAR'
  const isCoolingActive = plantState.cooling_state === 'ACTIVE'
  const isLeakActive = Boolean(plantState.leak_active)

  // Determine actuator badge color & status text
  const actuatorStatus = plantState.actuator_status || 'READY'
  const isActuatorLocked = actuatorStatus === 'LOCKED'
  const isActuatorFailed = actuatorStatus === 'FAILED'
  const isActuatorQuarantined = actuatorStatus === 'QUARANTINED'
  const isActuatorVerified = actuatorStatus === 'VERIFIED' || actuatorStatus === 'ACTUATED'

  const getActuatorBadge = () => {
    if (isActuatorLocked) {
      return {
        bg: 'rgba(239, 68, 68, 0.15)',
        border: 'rgba(239, 68, 68, 0.4)',
        color: '#ef4444',
        icon: <Lock size={13} />,
        label: 'ACTUATOR LOCKED (SAFETY BOUNDARY)',
      }
    }
    if (isActuatorQuarantined) {
      return {
        bg: 'rgba(245, 158, 11, 0.15)',
        border: 'rgba(245, 158, 11, 0.4)',
        color: '#f59e0b',
        icon: <AlertOctagon size={13} />,
        label: 'ACTUATOR QUARANTINED (ISOLATED)',
      }
    }
    if (isActuatorFailed) {
      return {
        bg: 'rgba(239, 68, 68, 0.15)',
        border: 'rgba(239, 68, 68, 0.4)',
        color: '#ef4444',
        icon: <AlertTriangle size={13} />,
        label: 'ACTUATOR FAULT (STROKE MISMATCH)',
      }
    }
    if (isActuatorVerified) {
      return {
        bg: 'rgba(34, 197, 94, 0.15)',
        border: 'rgba(34, 197, 94, 0.4)',
        color: '#22c55e',
        icon: <CheckCircle2 size={13} />,
        label: 'ACTUATOR VERIFIED (TICKET CONSUMED)',
      }
    }
    return {
      bg: 'rgba(56, 189, 248, 0.15)',
      border: 'rgba(56, 189, 248, 0.4)',
      color: '#38bdf8',
      icon: <Activity size={13} />,
      label: 'ACTUATOR ARMED / READY',
    }
  }

  const badge = getActuatorBadge()

  return (
    <div className="digital-twin-container" role="region" aria-label="Plant Digital Twin Simulation">
      <div className="twin-header">
        <div className="twin-title-group">
          <div className="twin-icon-box">
            <Activity size={16} />
          </div>
          <div>
            <div className="twin-title">Plant Digital Twin — Physical AI Telemetry</div>
            <div className="twin-subtitle">
              Deterministic 2D physical world state reflection synchronized with PhysicalWorld simulation
            </div>
          </div>
        </div>

        <div className="twin-meta-badges">
          <span className="mono-pill version-pill" title="Physical world monotonic state version">
            WORLD v{plantState.world_version}
          </span>
          <span
            className="mono-pill"
            style={{
              backgroundColor: badge.bg,
              borderColor: badge.border,
              color: badge.color,
            }}
          >
            {badge.icon}
            <span>{badge.label}</span>
          </span>
        </div>
      </div>

      {/* Main 2D Plant Schematic Diagram */}
      <div className="twin-schematic">
        <svg
          viewBox="0 0 840 280"
          className="plant-svg"
          preserveAspectRatio="xMidYMid meet"
          style={{ width: '100%', height: 'auto', maxHeight: '280px' }}
        >
          <defs>
            <linearGradient id="pipeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#1e293b" />
              <stop offset="50%" stopColor="#334155" />
              <stop offset="100%" stopColor="#1e293b" />
            </linearGradient>

            <linearGradient id="waterFlow" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#0284c7" stopOpacity="0.8" />
              <stop offset="50%" stopColor="#38bdf8" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#0284c7" stopOpacity="0.8" />
            </linearGradient>

            <linearGradient id="leakSpray" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.1" />
            </linearGradient>

            <pattern id="hazardStripes" width="20" height="20" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="10" height="20" fill="rgba(239, 68, 68, 0.12)" />
              <rect x="10" width="10" height="20" fill="rgba(245, 158, 11, 0.12)" />
            </pattern>
          </defs>

          {/* Plant Enclosure Grid Background */}
          <rect
            x="10"
            y="10"
            width="820"
            height="260"
            rx="12"
            fill="#090d16"
            stroke="#1e293b"
            strokeWidth="1.5"
          />

          {/* Flow Direction Annotations */}
          <text x="30" y="36" fill="#64748b" fontSize="11" fontFamily="var(--font-mono)" letterSpacing="1">
            COOLANT MANIFOLD LOOP [CH1-PRIMARY]
          </text>

          {/* 1. Pipe Section: Inlet to Pump P1 */}
          <line x1="40" y1="100" x2="120" y2="100" stroke="#334155" strokeWidth="18" strokeLinecap="round" />
          <line x1="40" y1="100" x2="120" y2="100" stroke="#0284c7" strokeWidth="8" strokeOpacity={isPumpActive ? "0.9" : "0.3"} />

          {/* 2. Pump P1 Unit */}
          <g transform="translate(140, 100)">
            <circle
              r="34"
              fill={isPumpActive ? '#0c4a6e' : '#1e293b'}
              stroke={isPumpActive ? '#38bdf8' : '#475569'}
              strokeWidth="2.5"
            />
            {/* Impeller blades */}
            <motion.g
              animate={!reducedMotion && isPumpActive ? { rotate: 360 } : { rotate: 0 }}
              transition={{ repeat: Infinity, duration: 2, ease: 'linear' }}
            >
              <line x1="-20" y1="0" x2="20" y2="0" stroke={isPumpActive ? '#7dd3fc' : '#64748b'} strokeWidth="3" />
              <line x1="0" y1="-20" x2="0" y2="20" stroke={isPumpActive ? '#7dd3fc' : '#64748b'} strokeWidth="3" />
            </motion.g>
            <text
              y="48"
              textAnchor="middle"
              fill={isPumpActive ? '#38bdf8' : '#94a3b8'}
              fontSize="12"
              fontWeight="600"
              fontFamily="var(--font-mono)"
            >
              PUMP P1
            </text>
            <text
              y="62"
              textAnchor="middle"
              fill={isPumpActive ? '#22c55e' : '#64748b'}
              fontSize="10"
              fontFamily="var(--font-mono)"
            >
              [{plantState.pump_state}]
            </text>
          </g>

          {/* 3. Pipe Section: Pump P1 to Valve B */}
          <line x1="174" y1="100" x2="380" y2="100" stroke="#334155" strokeWidth="18" strokeLinecap="round" />
          {/* Animated coolant flow line */}
          <motion.line
            x1="174"
            y1="100"
            x2="380"
            y2="100"
            stroke="#38bdf8"
            strokeWidth="8"
            strokeDasharray="16, 8"
            animate={!reducedMotion && (isPumpActive || isLeakActive) ? { strokeDashoffset: -48 } : {}}
            transition={{ repeat: Infinity, duration: 1.5, ease: 'linear' }}
            strokeOpacity={isValveOpen ? 0.9 : 0.2}
          />

          {/* Pressure & Flow Sensor Callout */}
          <g transform="translate(270, 50)">
            <rect x="-45" y="-18" width="90" height="36" rx="6" fill="#0f172a" stroke="#334155" strokeWidth="1.2" />
            <text x="0" y="-3" textAnchor="middle" fill="#94a3b8" fontSize="9" fontFamily="var(--font-mono)">
              PRESSURE / FLOW
            </text>
            <text x="0" y="11" textAnchor="middle" fill="#38bdf8" fontSize="11" fontWeight="600" fontFamily="var(--font-mono)">
              {plantState.pressure_psi?.toFixed(1) || '120.0'} PSI
            </text>
          </g>
          <line x1="270" y1="68" x2="270" y2="91" stroke="#475569" strokeWidth="1.5" strokeDasharray="3,3" />

          {/* 4. Valve B Component */}
          <g transform="translate(420, 100)">
            {/* Actuator housing on top */}
            <rect
              x="-24"
              y="-56"
              width="48"
              height="34"
              rx="4"
              fill={badge.bg}
              stroke={badge.border}
              strokeWidth="2"
            />
            {/* Actuator stem */}
            <motion.line
              x1="0"
              y1="-22"
              x2="0"
              y2={isValveOpen ? '0' : '12'}
              stroke="#cbd5e1"
              strokeWidth="4"
              animate={{ y2: isValveOpen ? 0 : 12 }}
              transition={{ duration: 0.5 }}
            />
            {/* Valve body (double wedge) */}
            <polygon
              points="-28,-22 28,22 28,-22 -28,22"
              fill={isValveOpen ? '#0f172a' : '#1e1b4b'}
              stroke={isValveOpen ? '#38bdf8' : '#818cf8'}
              strokeWidth="2.5"
            />
            {/* Gate indicator inside valve */}
            <line
              x1="0"
              y1="-16"
              x2="0"
              y2={isValveOpen ? '-16' : '16'}
              stroke={isValveOpen ? '#38bdf8' : '#ef4444'}
              strokeWidth="5"
            />

            <text
              y="48"
              textAnchor="middle"
              fill={isValveOpen ? '#38bdf8' : '#a5b4fc'}
              fontSize="12"
              fontWeight="600"
              fontFamily="var(--font-mono)"
            >
              VALVE B
            </text>
            <text
              y="62"
              textAnchor="middle"
              fill={isValveOpen ? '#38bdf8' : '#f43f5e'}
              fontSize="10"
              fontFamily="var(--font-mono)"
            >
              [{plantState.valve_b_state}]
            </text>

            {/* Leak spray visualization if leak is active */}
            {isLeakActive && isValveOpen && (
              <g transform="translate(0, 24)">
                <path
                  d="M0,0 L-14,35 L14,35 Z"
                  fill="url(#leakSpray)"
                />
                <circle cx="-6" cy="38" r="2.5" fill="#f43f5e" opacity="0.8" />
                <circle cx="8" cy="42" r="3" fill="#f43f5e" opacity="0.7" />
                <circle cx="0" cy="46" r="2" fill="#f43f5e" opacity="0.9" />
                <text x="0" y="58" textAnchor="middle" fill="#f43f5e" fontSize="9" fontFamily="var(--font-mono)" fontWeight="600">
                  LEAK: {plantState.flow_rate_lpm?.toFixed(1) || '14.0'} L/min
                </text>
              </g>
            )}
          </g>

          {/* 5. Pipe Section: Valve B to Plant Return */}
          <line x1="448" y1="100" x2="620" y2="100" stroke="#334155" strokeWidth="18" strokeLinecap="round" />
          {isValveOpen && (
            <motion.line
              x1="448"
              y1="100"
              x2="620"
              y2="100"
              stroke="#38bdf8"
              strokeWidth="8"
              strokeDasharray="16, 8"
              animate={!reducedMotion ? { strokeDashoffset: -48 } : {}}
              transition={{ repeat: Infinity, duration: 1.5, ease: 'linear' }}
            />
          )}

          {/* 6. Plant Return Header */}
          <g transform="translate(640, 100)">
            <rect x="-10" y="-35" width="20" height="70" rx="4" fill="#1e293b" stroke="#475569" strokeWidth="2" />
            <text x="28" y="4" fill="#94a3b8" fontSize="11" fontFamily="var(--font-mono)">
              HEAT EXCHANGER
            </text>
            <text x="28" y="18" fill={isCoolingActive ? '#22c55e' : '#f59e0b'} fontSize="9" fontFamily="var(--font-mono)">
              COOLING: {plantState.cooling_state}
            </text>
          </g>

          {/* 7. Human Safety Zone (Boundary Rectangle below Valve B) */}
          <g transform="translate(310, 175)">
            <rect
              x="0"
              y="0"
              width="230"
              height="80"
              rx="8"
              fill={isHumanZoneClear ? 'rgba(34, 197, 94, 0.05)' : 'rgba(239, 68, 68, 0.12)'}
              stroke={isHumanZoneClear ? 'rgba(34, 197, 94, 0.4)' : 'rgba(239, 68, 68, 0.8)'}
              strokeWidth={isHumanZoneClear ? '1.5' : '2.5'}
              strokeDasharray={isHumanZoneClear ? 'none' : '6, 4'}
            />
            {/* Zone hazard pattern overlay if occupied */}
            {!isHumanZoneClear && (
              <rect x="0" y="0" width="230" height="80" rx="8" fill="url(#hazardStripes)" />
            )}

            <text
              x="12"
              y="22"
              fill={isHumanZoneClear ? '#22c55e' : '#ef4444'}
              fontSize="11"
              fontWeight="600"
              fontFamily="var(--font-mono)"
            >
              HUMAN SAFETY ZONE [SECTOR 4]
            </text>

            <g transform="translate(18, 48)">
              {isHumanZoneClear ? (
                <g>
                  <circle cx="10" cy="-6" r="8" fill="#22c55e" opacity="0.2" stroke="#22c55e" strokeWidth="1.5" />
                  <text x="26" y="-2" fill="#22c55e" fontSize="11" fontFamily="var(--font-mono)" fontWeight="600">
                    STATUS: CLEAR (ZONE SECURE)
                  </text>
                  <text x="26" y="12" fill="#86efac" fontSize="9" fontFamily="var(--font-mono)">
                    No human personnel detected within safety envelope
                  </text>
                </g>
              ) : (
                <g>
                  <circle cx="10" cy="-6" r="8" fill="#ef4444" opacity="0.3" stroke="#ef4444" strokeWidth="2" />
                  <text x="26" y="-2" fill="#ef4444" fontSize="11" fontFamily="var(--font-mono)" fontWeight="700">
                    STATUS: OCCUPIED (SAFETY TRIPPED)
                  </text>
                  <text x="26" y="12" fill="#fca5a5" fontSize="9" fontFamily="var(--font-mono)">
                    Technician present — Policy blocks valve actuation
                  </text>
                </g>
              )}
            </g>
          </g>

          {/* 8. Mock Hardware Security Boundary Layer */}
          <g transform="translate(560, 200)">
            <rect
              x="0"
              y="0"
              width="250"
              height="55"
              rx="6"
              fill="#0b1120"
              stroke="#334155"
              strokeWidth="1.2"
            />
            <text x="12" y="18" fill="#94a3b8" fontSize="10" fontFamily="var(--font-mono)">
              MOCK HARDWARE ENDPOINT
            </text>
            <text x="12" y="34" fill={badge.color} fontSize="11" fontFamily="var(--font-mono)" fontWeight="600">
              GATEWAY: {actuatorStatus}
            </text>
            <text x="12" y="47" fill="#64748b" fontSize="8.5" fontFamily="var(--font-mono)">
              HMAC-SHA256 Auth Boundary Enforced
            </text>
          </g>
        </svg>
      </div>

      {/* Phase 2O: Real-World Public Telemetry Environmental Context Card */}
      {(telemetryObservation || externalObservations?.usgs) && (
        <div style={{ marginBottom: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              REAL-WORLD OBSERVATION (USGS OGC API) — ENVIRONMENTAL CONTEXT
            </span>
            <span className="status-badge read-only" style={{ fontSize: '9px', color: '#38bdf8' }}>
              EXTERNAL OBSERVATION ≠ INTERNAL ACTUATOR STATE
            </span>
          </div>

          <div className="twin-telemetry-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
            <div className="twin-card" style={{ borderColor: 'rgba(56, 189, 248, 0.4)' }}>
              <div className="twin-card-header" style={{ backgroundColor: 'rgba(56, 189, 248, 0.08)' }}>
                <Waves size={13} className="text-sky" />
                <span>Station: {telemetryObservation?.monitoring_location_id || 'USGS-01646500'}</span>
              </div>
              <div className="twin-card-body">
                <div className="telemetry-row">
                  <span className="telemetry-label">Streamflow / Discharge:</span>
                  <span className="telemetry-val mono" style={{ color: '#38bdf8' }}>
                    {externalObservations?.usgs?.streamflow_cfs?.value ?? telemetryObservation?.normalized_value ?? 2350} {telemetryObservation?.unit || 'ft³/s'}
                  </span>
                </div>
                <div className="telemetry-row">
                  <span className="telemetry-label">Freshness Classification:</span>
                  <span className="telemetry-val mono" style={{ color: '#22c55e' }}>
                    {externalObservations?.usgs?.streamflow_cfs?.freshness ?? telemetryObservation?.freshness ?? 'FRESH'}
                  </span>
                </div>
              </div>
            </div>

            <div className="twin-card" style={{ borderColor: 'rgba(56, 189, 248, 0.4)' }}>
              <div className="twin-card-header" style={{ backgroundColor: 'rgba(56, 189, 248, 0.08)' }}>
                <Waves size={13} className="text-sky" />
                <span>Gage Height &amp; Context</span>
              </div>
              <div className="twin-card-body">
                <div className="telemetry-row">
                  <span className="telemetry-label">Gage Height:</span>
                  <span className="telemetry-val mono" style={{ color: '#38bdf8' }}>
                    {externalObservations?.usgs?.gage_height_ft?.value ?? '2.90'} ft
                  </span>
                </div>
                <div className="telemetry-row">
                  <span className="telemetry-label">Flow Regime Context:</span>
                  <span className="telemetry-val mono" style={{ color: '#22c55e' }}>
                    {externalObservations?.environmental_context?.classification || 'NORMAL_FLOW'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modeled Plant Control-System State */}
      <div style={{ marginBottom: '6px' }}>
        <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          MODELED PLANT (CONTROL-SYSTEM DIGITAL TWIN)
        </span>
      </div>

      {/* Telemetry Summary Cards */}
      <div className="twin-telemetry-grid">
        <div className="twin-card">
          <div className="twin-card-header">
            <Droplets size={13} className="text-sky" />
            <span>Manifold & Valves</span>
          </div>
          <div className="twin-card-body">
            <div className="telemetry-row">
              <span className="telemetry-label">Valve B State:</span>
              <span className="telemetry-val mono" style={{ color: isValveOpen ? '#38bdf8' : '#a5b4fc' }}>
                {plantState.valve_b_state}
              </span>
            </div>
            <div className="telemetry-row">
              <span className="telemetry-label">Active Leak:</span>
              <span className="telemetry-val mono" style={{ color: isLeakActive ? '#f43f5e' : '#22c55e' }}>
                {isLeakActive ? `YES (${plantState.flow_rate_lpm?.toFixed(1) || '14.0'} L/min)` : 'NONE (ISOLATED)'}
              </span>
            </div>
          </div>
        </div>

        <div className="twin-card">
          <div className="twin-card-header">
            <Power size={13} className="text-amber" />
            <span>Pumps & Cooling</span>
          </div>
          <div className="twin-card-body">
            <div className="telemetry-row">
              <span className="telemetry-label">Pump P1:</span>
              <span className="telemetry-val mono" style={{ color: isPumpActive ? '#22c55e' : '#94a3b8' }}>
                {plantState.pump_state}
              </span>
            </div>
            <div className="telemetry-row">
              <span className="telemetry-label">Cooling System:</span>
              <span className="telemetry-val mono" style={{ color: isCoolingActive ? '#22c55e' : '#ef4444' }}>
                {plantState.cooling_state}
              </span>
            </div>
          </div>
        </div>

        <div className="twin-card">
          <div className="twin-card-header">
            {isHumanZoneClear ? <UserCheck size={13} className="text-emerald" /> : <UserX size={13} className="text-rose" />}
            <span>Human Safety Zone</span>
          </div>
          <div className="twin-card-body">
            <div className="telemetry-row">
              <span className="telemetry-label">Zone Status:</span>
              <span className="telemetry-val mono" style={{ color: isHumanZoneClear ? '#22c55e' : '#ef4444' }}>
                {plantState.human_zone}
              </span>
            </div>
            <div className="telemetry-row">
              <span className="telemetry-label">Policy Constraint:</span>
              <span className="telemetry-val mono" style={{ color: isHumanZoneClear ? '#22c55e' : '#f59e0b' }}>
                {isHumanZoneClear ? 'PERMITTED IF AUTHORIZED' : 'VALVE MUTATION FORBIDDEN'}
              </span>
            </div>
          </div>
        </div>

        <div className="twin-card">
          <div className="twin-card-header">
            <ShieldCheck size={13} style={{ color: badge.color }} />
            <span>Actuator Boundary</span>
          </div>
          <div className="twin-card-body">
            <div className="telemetry-row">
              <span className="telemetry-label">Hardware State:</span>
              <span className="telemetry-val mono" style={{ color: badge.color }}>
                {actuatorStatus}
              </span>
            </div>
            <div className="telemetry-row">
              <span className="telemetry-label">Physical Authority:</span>
              <span className="telemetry-val mono" style={{ color: isActuatorLocked ? '#ef4444' : '#38bdf8' }}>
                {isActuatorLocked ? 'LOCKED / NO TICKET' : isActuatorQuarantined ? 'QUARANTINED' : 'SAFETY ENCLAVE REQUIRED'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Mandatory Industrial Hardware Disclaimer */}
      <div className="twin-disclaimer">
        <Shield size={12} className="text-muted" />
        <span>
          <strong>Engineering Disclaimer:</strong> The digital twin and mock hardware are software representations used for demonstration and validation. They do not claim equivalence to certified industrial hardware.
        </span>
      </div>
    </div>
  )
}
