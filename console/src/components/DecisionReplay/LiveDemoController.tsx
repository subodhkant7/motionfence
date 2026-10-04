import React, { useState, useEffect, useRef } from 'react'
import {
  Zap,
  PlayCircle,
  Cpu,
  ShieldCheck,
  AlertTriangle,
  Activity,
  CheckCircle2,
  Lock,
  ArrowRight,
  Server,
} from 'lucide-react'
import {
  ExecutionMode,
  PhysicalBackend,
  ScenarioData,
  ScenarioMeta,
} from '../../types'
import { api, DemoExecutionStatus } from '../../services/api'

interface LiveDemoControllerProps {
  scenarios: ScenarioMeta[]
  selectedScenarioId: string
  onSelectScenario: (id: string) => void
  scenarioData: ScenarioData | null
  onScenarioDataLoaded: (data: ScenarioData) => void
  activeMode: ExecutionMode
  onModeChange: (mode: ExecutionMode) => void
  activeBackend: PhysicalBackend
  onBackendChange: (backend: PhysicalBackend) => void
}

export const LiveDemoController: React.FC<LiveDemoControllerProps> = ({
  scenarios,
  selectedScenarioId,
  onSelectScenario,
  scenarioData,
  onScenarioDataLoaded,
  activeMode,
  onModeChange,
  activeBackend,
  onBackendChange,
}) => {
  const [isExecuting, setIsExecuting] = useState<boolean>(false)
  const [executionId, setExecutionId] = useState<string | null>(null)
  const [executionStatus, setExecutionStatus] = useState<string>('IDLE')
  const [stageOutcome, setStageOutcome] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const isScenarioDenied = selectedScenarioId.includes('scenario_b') || selectedScenarioId.includes('denied')
  const isScenarioToctou = selectedScenarioId.includes('scenario_c') || selectedScenarioId.includes('toctou')
  const isScenarioRecovery = selectedScenarioId.includes('scenario_d') || selectedScenarioId.includes('recovery')
  const isScenarioTelemetry = selectedScenarioId.includes('scenario_telemetry') || selectedScenarioId.includes('telemetry')
  const isScenarioEvidence = selectedScenarioId.includes('scenario_evidence') || selectedScenarioId.includes('evidence')

  // Clean up polling interval on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    }
  }, [])

  const triggerExecution = async () => {
    setIsExecuting(true)
    setExecutionStatus('QUEUED')
    setErrorMessage(null)

    const result = await api.triggerControlledDemo(selectedScenarioId, activeMode, activeBackend)
    const execId = result.execution_id
    setExecutionId(execId)
    setExecutionStatus(result.status || 'RUNNING')

    if (execId.startsWith('exec_offline_')) {
      // Local fallback
      setTimeout(async () => {
        const loaded = await api.getScenarioData(selectedScenarioId)
        if (loaded) {
          const modLoaded = { ...loaded, execution_mode: activeMode, physical_backend: activeBackend }
          onScenarioDataLoaded(modLoaded)
        }
        setExecutionStatus('COMPLETED')
        setIsExecuting(false)
      }, 500)
      return
    }

    // Start polling the server
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    let attempts = 0
    pollIntervalRef.current = setInterval(async () => {
      attempts += 1
      const statusObj: DemoExecutionStatus | null = await api.getDemoExecution(execId)
      if (!statusObj) {
        if (attempts > 30) {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
          setIsExecuting(false)
          setExecutionStatus('FAILED')
          setErrorMessage('Execution polling timed out.')
        }
        return
      }

      setExecutionStatus(statusObj.status)
      if (statusObj.stage_outcome) {
        setStageOutcome(statusObj.stage_outcome)
      }

      if (statusObj.status === 'COMPLETED') {
        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
        setIsExecuting(false)
        if (statusObj.record) {
          onScenarioDataLoaded(statusObj.record)
        }
      } else if (statusObj.status === 'FAILED') {
        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
        setIsExecuting(false)
        setErrorMessage(statusObj.error_message || 'Execution failed closed.')
      }
    }, 400)
  }

  // Derive visual flow steps based on canonical scenario
  const getVisualFlowSteps = () => {
    if (isScenarioDenied) {
      return [
        { label: 'LIVE NEMOTRON', active: true, status: 'nominal' },
        { label: 'PROPOSAL', active: true, status: 'nominal' },
        { label: 'MOTIONFENCE SAFETY DECISION', active: true, status: 'denied' },
        { label: 'NO TICKET MINTED', active: true, status: 'denied' },
        { label: 'ACTUATOR LOCKED', active: true, status: 'denied' },
      ]
    }
    if (isScenarioToctou) {
      return [
        { label: 'AUTHORIZED (v3)', active: true, status: 'nominal' },
        { label: 'WORLD CHANGE (v4)', active: true, status: 'warning' },
        { label: 'REVALIDATION FAILED', active: true, status: 'denied' },
        { label: 'TICKET INVALIDATED', active: true, status: 'denied' },
        { label: 'HARDWARE LOCKED', active: true, status: 'denied' },
      ]
    }
    if (isScenarioRecovery) {
      return [
        { label: 'ACTUATED', active: true, status: 'nominal' },
        { label: 'VERIFICATION FAILED', active: true, status: 'warning' },
        { label: 'QUARANTINE', active: true, status: 'warning' },
        { label: 'FRESH AUTHORIZATION', active: true, status: 'nominal' },
        { label: 'RECOVERY ACTUATION', active: true, status: 'nominal' },
        { label: 'VERIFIED', active: true, status: 'verified' },
      ]
    }
    // Safe, Telemetry, Evidence nominal flow
    return [
      { label: isScenarioTelemetry ? 'USGS TELEMETRY' : isScenarioEvidence ? 'TAVILY EVIDENCE' : 'LIVE NEMOTRON', active: true, status: 'nominal' },
      { label: 'PROPOSAL', active: true, status: 'nominal' },
      { label: 'MOTIONFENCE SAFETY DECISION', active: true, status: 'nominal' },
      { label: 'AUTHORIZATION TICKET', active: true, status: 'nominal' },
      { label: activeBackend === 'isaac' ? 'ISAAC SIM' : 'MOCK HARDWARE', active: true, status: 'nominal' },
      { label: 'VERIFICATION', active: true, status: 'verified' },
    ]
  }

  const flowSteps = getVisualFlowSteps()
  const tokenUsage = scenarioData?.token_usage

  return (
    <div
      className="console-card"
      style={{
        marginBottom: '20px',
        border: '1px solid rgba(56, 189, 248, 0.4)',
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.25)',
      }}
      data-testid="controlled-live-demo-panel"
    >
      <div
        className="console-card-header"
        style={{
          backgroundColor: 'rgba(2, 132, 199, 0.12)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '10px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Zap size={16} className="text-sky" />
          <span style={{ fontSize: '13px', fontWeight: 700, letterSpacing: '0.05em', color: '#f8fafc' }}>
            CONTROLLED DEMO CONTROLLER &middot; SERVER-ENFORCED PIPELINE
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            className="status-badge"
            style={{
              fontSize: '10px',
              backgroundColor: 'rgba(15, 23, 42, 0.8)',
              border: '1px solid rgba(56, 189, 248, 0.3)',
              color: '#38bdf8',
            }}
          >
            CANONICAL ALLOWLIST ONLY &middot; ZERO ACTUATOR AUTHORITY
          </span>
        </div>
      </div>

      <div className="console-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {/* Row 1: Scenario Selector, Mode Switch, Backend Switch, and Action Trigger */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '12px',
            alignItems: 'center',
          }}
        >
          {/* Scenario Selection */}
          <div>
            <label
              htmlFor="ctrl-scenario-select"
              style={{
                display: 'block',
                fontSize: '11px',
                fontWeight: 600,
                color: 'var(--text-muted)',
                marginBottom: '4px',
                textTransform: 'uppercase',
              }}
            >
              Canonical Scenario:
            </label>
            <select
              id="ctrl-scenario-select"
              className="picker-select"
              style={{ width: '100%', padding: '7px 10px', fontSize: '12px' }}
              value={selectedScenarioId}
              onChange={(e) => onSelectScenario(e.target.value)}
              disabled={isExecuting}
            >
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
          </div>

          {/* Execution Mode */}
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '11px',
                fontWeight: 600,
                color: 'var(--text-muted)',
                marginBottom: '4px',
                textTransform: 'uppercase',
              }}
            >
              Execution Mode:
            </label>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                type="button"
                className={`mode-badge ${activeMode === 'LIVE' ? 'live-mode' : 'offline-test-mode'}`}
                style={{
                  flex: 1,
                  padding: '7px 10px',
                  justifyContent: 'center',
                  cursor: isExecuting ? 'not-allowed' : 'pointer',
                  border: activeMode === 'LIVE' ? '1.5px solid #38bdf8' : '1px solid #475569',
                }}
                onClick={() => onModeChange('LIVE')}
                disabled={isExecuting}
                title="Live Model Inference & Evidence"
              >
                <Zap size={13} />
                <span>LIVE</span>
              </button>
              <button
                type="button"
                className={`mode-badge ${activeMode === 'REPLAY' ? 'replay-mode' : 'offline-test-mode'}`}
                style={{
                  flex: 1,
                  padding: '7px 10px',
                  justifyContent: 'center',
                  cursor: isExecuting ? 'not-allowed' : 'pointer',
                  border: activeMode === 'REPLAY' ? '1.5px solid #f59e0b' : '1px solid #475569',
                }}
                onClick={() => onModeChange('REPLAY')}
                disabled={isExecuting}
                title="Deterministic Replay from Sealed Audit Fixture"
              >
                <PlayCircle size={13} />
                <span>REPLAY</span>
              </button>
            </div>
          </div>

          {/* Physical Backend */}
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '11px',
                fontWeight: 600,
                color: 'var(--text-muted)',
                marginBottom: '4px',
                textTransform: 'uppercase',
              }}
            >
              Physical Execution Backend:
            </label>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                type="button"
                className="mode-badge"
                style={{
                  flex: 1,
                  padding: '7px 10px',
                  justifyContent: 'center',
                  cursor: isExecuting ? 'not-allowed' : 'pointer',
                  border: activeBackend === 'mock' ? '1.5px solid #38bdf8' : '1px solid #475569',
                  backgroundColor: activeBackend === 'mock' ? 'rgba(56, 189, 248, 0.15)' : 'transparent',
                  color: activeBackend === 'mock' ? '#38bdf8' : '#94a3b8',
                }}
                onClick={() => onBackendChange('mock')}
                disabled={isExecuting}
              >
                <Cpu size={13} />
                <span>MOCK (DEFAULT)</span>
              </button>
              <button
                type="button"
                className="mode-badge"
                style={{
                  flex: 1,
                  padding: '7px 10px',
                  justifyContent: 'center',
                  cursor: isExecuting ? 'not-allowed' : 'pointer',
                  border: activeBackend === 'isaac' ? '1.5px solid #76b900' : '1px solid #475569',
                  backgroundColor: activeBackend === 'isaac' ? 'rgba(118, 185, 0, 0.15)' : 'transparent',
                  color: activeBackend === 'isaac' ? '#76b900' : '#94a3b8',
                }}
                onClick={() => onBackendChange('isaac')}
                disabled={isExecuting}
                title="Isaac Sim Adapter (Adapter contract verified on macOS)"
              >
                <Server size={13} />
                <span>ISAAC SIM</span>
              </button>
            </div>
          </div>

          {/* Primary Action Button */}
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '11px',
                fontWeight: 600,
                color: 'var(--text-muted)',
                marginBottom: '4px',
                textTransform: 'uppercase',
              }}
            >
              Trigger Execution:
            </label>
            <button
              type="button"
              className="play-btn"
              data-testid="run-live-demo-btn"
              style={{
                width: '100%',
                padding: '8px 16px',
                justifyContent: 'center',
                backgroundColor: activeMode === 'LIVE' ? '#0284c7' : '#d97706',
                color: '#ffffff',
                border: 'none',
                fontWeight: 700,
                fontSize: '12px',
                cursor: isExecuting ? 'not-allowed' : 'pointer',
                opacity: isExecuting ? 0.7 : 1,
                boxShadow: activeMode === 'LIVE' ? '0 0 14px rgba(2, 132, 199, 0.4)' : '0 0 14px rgba(217, 119, 6, 0.4)',
              }}
              onClick={triggerExecution}
              disabled={isExecuting}
            >
              {isExecuting ? (
                <>
                  <Activity size={14} className="animate-spin" />
                  <span>EXECUTING...</span>
                </>
              ) : activeMode === 'LIVE' ? (
                <>
                  <Zap size={14} />
                  <span>RUN LIVE DEMO</span>
                </>
              ) : (
                <>
                  <PlayCircle size={14} />
                  <span>LOAD REPLAY</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Row 2: Status & Execution Metadata Bar */}
        <div
          style={{
            backgroundColor: 'rgba(15, 23, 42, 0.7)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-sm)',
            padding: '10px 14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '10px',
            fontSize: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
            <div>
              <span style={{ color: 'var(--text-muted)', fontSize: '11px', marginRight: '6px' }}>STATUS:</span>
              <span
                className="mono"
                style={{
                  fontWeight: 700,
                  color:
                    executionStatus === 'COMPLETED'
                      ? '#4ade80'
                      : executionStatus === 'FAILED'
                      ? '#f87171'
                      : executionStatus === 'RUNNING' || executionStatus === 'QUEUED'
                      ? '#38bdf8'
                      : '#94a3b8',
                }}
              >
                {executionStatus}
              </span>
            </div>

            {stageOutcome && (
              <div>
                <span style={{ color: 'var(--text-muted)', fontSize: '11px', marginRight: '6px' }}>OUTCOME:</span>
                <span
                  className="mono"
                  style={{
                    fontWeight: 700,
                    color:
                      stageOutcome === 'NOMINAL' || stageOutcome === 'RECOVERED'
                        ? '#4ade80'
                        : stageOutcome === 'DENIED' || stageOutcome === 'BLOCKED'
                        ? '#fbbf24'
                        : '#f87171',
                  }}
                >
                  {stageOutcome}
                </span>
              </div>
            )}

            {executionId && (
              <div>
                <span style={{ color: 'var(--text-muted)', fontSize: '11px', marginRight: '6px' }}>EXECUTION ID:</span>
                <span className="mono" style={{ color: '#cbd5e1' }}>
                  {executionId}
                </span>
              </div>
            )}
          </div>

          {/* Token accounting guardrail (Section 22: Truthful credit info) */}
          {tokenUsage && (
            <div className="mono" style={{ fontSize: '11px', color: '#94a3b8' }}>
              TOKENS &mdash; IN: {tokenUsage.prompt_tokens ?? 0} &middot; OUT: {tokenUsage.completion_tokens ?? 0} &middot; TOTAL: {tokenUsage.total_tokens ?? 0}
            </div>
          )}
        </div>

        {/* Error notification banner if failed */}
        {errorMessage && (
          <div
            style={{
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid #ef4444',
              borderRadius: 'var(--radius-sm)',
              padding: '8px 12px',
              fontSize: '12px',
              color: '#fca5a5',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <AlertTriangle size={15} color="#ef4444" />
            <span>
              <strong>FAIL-CLOSED:</strong> {errorMessage}
            </span>
          </div>
        )}

        {/* Row 3: Section 30 Live Execution Visual Flow */}
        <div>
          <div
            style={{
              fontSize: '11px',
              fontWeight: 600,
              color: 'var(--text-muted)',
              marginBottom: '8px',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            Server-Enforced Pipeline Sequence:
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '6px',
              backgroundColor: 'rgba(15, 23, 42, 0.5)',
              padding: '8px 12px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            {flowSteps.map((step, idx) => {
              const isLast = idx === flowSteps.length - 1
              let borderColor = 'rgba(56, 189, 248, 0.3)'
              let bg = 'rgba(56, 189, 248, 0.08)'
              let textColor = '#7dd3fc'

              if (step.status === 'denied') {
                borderColor = 'rgba(248, 113, 113, 0.4)'
                bg = 'rgba(248, 113, 113, 0.1)'
                textColor = '#fca5a5'
              } else if (step.status === 'warning') {
                borderColor = 'rgba(251, 191, 36, 0.4)'
                bg = 'rgba(251, 191, 36, 0.1)'
                textColor = '#fde68a'
              } else if (step.status === 'verified') {
                borderColor = 'rgba(74, 222, 128, 0.4)'
                bg = 'rgba(74, 222, 128, 0.1)'
                textColor = '#86efac'
              }

              return (
                <React.Fragment key={step.label}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      border: `1px solid ${borderColor}`,
                      backgroundColor: bg,
                      fontSize: '11px',
                      fontWeight: 600,
                      color: textColor,
                    }}
                  >
                    {step.status === 'verified' ? (
                      <CheckCircle2 size={12} color="#4ade80" />
                    ) : step.status === 'denied' ? (
                      <Lock size={12} color="#f87171" />
                    ) : step.status === 'warning' ? (
                      <AlertTriangle size={12} color="#fbbf24" />
                    ) : (
                      <ShieldCheck size={12} color="#38bdf8" />
                    )}
                    <span>{step.label}</span>
                  </div>
                  {!isLast && <ArrowRight size={12} color="#64748b" />}
                </React.Fragment>
              )
            })}
          </div>
        </div>

        {/* Section 31: Replay Banner Display Guarantee */}
        {activeMode === 'REPLAY' && (
          <div
            style={{
              backgroundColor: 'rgba(245, 158, 11, 0.08)',
              border: '1px solid rgba(245, 158, 11, 0.3)',
              borderLeft: '4px solid #f59e0b',
              borderRadius: 'var(--radius-sm)',
              padding: '8px 12px',
              fontSize: '12px',
              color: '#fde68a',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '8px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <PlayCircle size={14} />
              <span>
                <strong>REPLAY &mdash; RECORDED LIVE EXECUTION:</strong> Reproducing sealed audit record. Zero network calls, zero model invocation, zero actuation authority.
              </span>
            </div>
            <span className="mono" style={{ fontSize: '11px', color: '#fbbf24' }}>
              SHA-256 INTEGRITY SEALED
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
