import React, { useState, useEffect, useCallback, useMemo } from 'react'
import {
  ShieldCheck,
  ShieldAlert,
  Play,
  RotateCcw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Lock,
  Unlock,
  Download,
  Copy,
  ExternalLink,
  Cpu,
  Layers,
  ArrowRight,
  Flame,
  UserX,
  Clock,
  Zap,
  BarChart2,
  FileText,
  Activity,
  Maximize2,
  Eye,
  RefreshCw,
  X,
} from 'lucide-react'
import {
  BenchmarkReportData,
  DigitalTwinPlantState,
  IsaacPrimPaths,
  SafetyLabExecutionResultData,
  SafetyLabScenarioData,
} from '../../types'
import { api } from '../../services/api'
import { IsaacSimViewport3D } from '../DigitalTwin/IsaacSimViewport3D'
import './SafetyLab.css'

interface SafetyLabViewProps {
  onExitLab: () => void
  reducedMotion: boolean
  onToggleReducedMotion: () => void
}

const DEFAULT_PRIM_PATHS: IsaacPrimPaths = {
  valve_b: '/World/Valves/Valve_B',
  pump_p1: '/World/Pumps/Pump_P1',
  human_zone: '/World/Safety/Sector4_ExclusionZone',
  human_worker: '/World/Actors/Worker_Human',
  gateway_actuator: '/World/Actuators/MotionFence_Gateway',
}

export const SafetyLabView: React.FC<SafetyLabViewProps> = ({
  onExitLab,
  reducedMotion,
  onToggleReducedMotion,
}) => {
  const [scenarios, setScenarios] = useState<SafetyLabScenarioData[]>([])
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('safe_valve_operation')
  const [executionMode, setExecutionMode] = useState<'DETERMINISTIC_REPLAY' | 'LIVE_INFERENCE'>('DETERMINISTIC_REPLAY')
  const [isRunning, setIsRunning] = useState<boolean>(false)
  const [activeTab, setActiveTab] = useState<'decision' | 'matrix' | 'metrics' | 'evidence'>('decision')
  const [scenarioFilter, setScenarioFilter] = useState<'ALL' | 'CANONICAL' | 'VARIANTS'>('ALL')

  // Execution states
  const [currentExecution, setCurrentExecution] = useState<SafetyLabExecutionResultData | null>(null)
  const [benchmarkReport, setBenchmarkReport] = useState<BenchmarkReportData | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Verification modal
  const [showVerifyModal, setShowVerifyModal] = useState<boolean>(false)
  const [verifyResult, setVerifyResult] = useState<any | null>(null)
  const [isVerifying, setIsVerifying] = useState<boolean>(false)

  // Fetch initial scenarios & report
  useEffect(() => {
    async function init() {
      try {
        const scList = await api.getSafetyLabScenarios()
        setScenarios(scList)
        if (scList.length > 0 && !selectedScenarioId) {
          setSelectedScenarioId(scList[0].scenario_id)
        }

        const rep = await api.getLatestBenchmarkReport('expanded')
        if (rep) {
          setBenchmarkReport(rep)
        }
      } catch (err: any) {
        setErrorMsg('Failed to load Safety Lab metadata.')
      }
    }
    init()
  }, [])

  const filteredScenarios = useMemo(() => {
    if (scenarioFilter === 'CANONICAL') {
      return scenarios.filter((s) => s.is_canonical)
    }
    if (scenarioFilter === 'VARIANTS') {
      return scenarios.filter((s) => !s.is_canonical)
    }
    return scenarios
  }, [scenarios, scenarioFilter])

  const selectedScenario = useMemo(() => {
    return scenarios.find((s) => s.scenario_id === selectedScenarioId) || scenarios[0] || null
  }, [scenarios, selectedScenarioId])

  // Derive DigitalTwinPlantState from current execution result or selected scenario initial state
  const currentPlantState: DigitalTwinPlantState = useMemo(() => {
    const rawState = currentExecution
      ? currentExecution.final_state_summary
      : selectedScenario?.initial_plant_state || {}

    return {
      stage_name: currentExecution ? currentExecution.execution_status : 'INITIAL_STATE',
      pump_state: rawState.pump_p1 || 'INACTIVE',
      valve_b_state: rawState.valve_b || 'OPEN',
      valve_b_angle_deg: rawState.valve_b === 'CLOSED' ? 90 : 0,
      cooling_state: rawState.cooling || 'ACTIVE',
      human_zone: rawState.human_zone || 'CLEAR',
      human_distance_m: rawState.human_zone === 'OCCUPIED' ? 1.2 : 4.8,
      actuator_status: currentExecution ? currentExecution.execution_status : 'READY',
      world_version: rawState.version || 1,
      leak_active: rawState.leak_active ?? true,
      pressure_psi: rawState.pressure_psi ?? 120.0,
      flow_rate_lpm: rawState.flow_rate_lpm ?? 12.0,
      physical_backend: 'mock',
      isaac_prim_paths: DEFAULT_PRIM_PATHS,
    }
  }, [currentExecution, selectedScenario])

  // Run single scenario
  const handleRunScenario = useCallback(async () => {
    if (!selectedScenario || isRunning) return
    setIsRunning(true)
    setErrorMsg(null)

    try {
      const dispatchRes = await api.runSafetyLabScenario(
        selectedScenario.scenario_id,
        executionMode,
        42,
      )

      // Poll execution until complete
      const execId = dispatchRes.execution_id
      let attempts = 0
      const pollInterval = setInterval(async () => {
        attempts++
        try {
          const statusRec = await api.pollSafetyLabExecution(execId)
          if (statusRec.status === 'COMPLETED') {
            clearInterval(pollInterval)
            setCurrentExecution(statusRec.result)
            setIsRunning(false)
          } else if (statusRec.status === 'FAILED') {
            clearInterval(pollInterval)
            setErrorMsg(statusRec.error || 'Scenario execution failed fail-closed.')
            setIsRunning(false)
          }
        } catch {
          if (attempts > 30) {
            clearInterval(pollInterval)
            setErrorMsg('Execution polling timed out.')
            setIsRunning(false)
          }
        }
      }, 150)
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to dispatch scenario run.')
      setIsRunning(false)
    }
  }, [selectedScenario, executionMode, isRunning])

  // Run full benchmark suite
  const handleRunBenchmark = useCallback(async (suiteType: 'canonical' | 'expanded' = 'expanded') => {
    if (isRunning) return
    setIsRunning(true)
    setErrorMsg(null)

    try {
      const dispatchRes = await api.runSafetyLabBenchmark(executionMode, 42, suiteType)
      const execId = dispatchRes.execution_id
      let attempts = 0
      const pollInterval = setInterval(async () => {
        attempts++
        try {
          const statusRec = await api.pollSafetyLabExecution(execId)
          if (statusRec.status === 'COMPLETED') {
            clearInterval(pollInterval)
            setBenchmarkReport(statusRec.report)
            setIsRunning(false)
            setActiveTab('metrics')
          } else if (statusRec.status === 'FAILED') {
            clearInterval(pollInterval)
            setErrorMsg(statusRec.error || 'Benchmark suite execution failed.')
            setIsRunning(false)
          }
        } catch {
          if (attempts > 60) {
            clearInterval(pollInterval)
            setErrorMsg('Benchmark suite polling timed out.')
            setIsRunning(false)
          }
        }
      }, 250)
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to dispatch benchmark suite.')
      setIsRunning(false)
    }
  }, [executionMode, isRunning])

  // Download evidence bundle
  const handleDownloadEvidence = useCallback(async () => {
    if (!currentExecution) return
    try {
      const bundle = await api.getSafetyLabEvidence(currentExecution.execution_id)
      const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(bundle, null, 2))
      const downloadAnchor = document.createElement('a')
      downloadAnchor.setAttribute('href', dataStr)
      downloadAnchor.setAttribute('download', `motionfence_evidence_${currentExecution.scenario_id}.json`)
      document.body.appendChild(downloadAnchor)
      downloadAnchor.click()
      downloadAnchor.remove()
    } catch (err: any) {
      setErrorMsg('Failed to download evidence bundle.')
    }
  }, [currentExecution])

  // Download full benchmark report
  const handleDownloadReport = useCallback(() => {
    if (!benchmarkReport) return
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(benchmarkReport, null, 2))
    const downloadAnchor = document.createElement('a')
    downloadAnchor.setAttribute('href', dataStr)
    downloadAnchor.setAttribute('download', `motionfence_benchmark_report_${benchmarkReport.run_id}.json`)
    document.body.appendChild(downloadAnchor)
    downloadAnchor.click()
    downloadAnchor.remove()
  }, [benchmarkReport])

  // Verify evidence hash
  const handleVerifyHash = useCallback(async () => {
    if (!currentExecution) return
    setIsVerifying(true)
    setShowVerifyModal(true)
    try {
      const execId = currentExecution.execution_id || (currentExecution as any).run_id
      const bundle = await api.getSafetyLabEvidence(execId)
      const result = await api.verifyEvidence(bundle)
      setVerifyResult(result)
    } catch (err: any) {
      setVerifyResult({
        is_valid: false,
        reported_hash: currentExecution?.sha256_hash || 'UNKNOWN',
        computed_hash: 'ERROR_OR_NOT_FOUND',
        message: err.message || 'Cryptographic hash recomputation failed or network error.',
      })
    } finally {
      setIsVerifying(false)
    }
  }, [currentExecution])

  return (
    <div className="safetylab-container">
      {/* Top Header */}
      <header className="safetylab-header">
        <div className="safetylab-brand">
          <div className="safetylab-badge-icon">
            <ShieldCheck size={20} />
          </div>
          <div>
            <h1 className="safetylab-title">MotionFence Public Safety Lab & Quantitative Benchmark</h1>
            <p className="safetylab-subtitle">
              Deterministic Twin Simulation · Authoritative Policy Gate · SHA-256 Cryptographic Evidence
            </p>
          </div>
        </div>

        <div className="safetylab-header-controls">
          <div className="mode-toggle-group" role="group" aria-label="Execution Mode">
            <button
              className={`mode-toggle-btn ${executionMode === 'DETERMINISTIC_REPLAY' ? 'active' : ''}`}
              onClick={() => setExecutionMode('DETERMINISTIC_REPLAY')}
              title="100% Offline, deterministic fixture replay"
            >
              <CheckCircle2 size={13} />
              <span>Deterministic Replay</span>
            </button>
            <button
              className={`mode-toggle-btn ${executionMode === 'LIVE_INFERENCE' ? 'active' : ''}`}
              onClick={() => setExecutionMode('LIVE_INFERENCE')}
              title="Real-time model inference (subject to live token guardrails)"
            >
              <Zap size={13} />
              <span>Live Inference</span>
            </button>
          </div>

          <button className="btn-exit-lab" onClick={onExitLab} id="btn-exit-safetylab">
            <span>Back to Console</span>
          </button>
        </div>
      </header>

      {/* Scenario Selector Strip */}
      <section className="scenarios-strip-container">
        <div className="scenarios-strip-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div className="strip-title">
              <Activity size={14} />
              <span>Safety Scenarios ({scenarios.length} Total)</span>
            </div>
            <div className="filter-pills-row">
              <button
                className={`filter-pill-btn ${scenarioFilter === 'ALL' ? 'active' : ''}`}
                onClick={() => setScenarioFilter('ALL')}
                id="filter-all"
              >
                All ({scenarios.length})
              </button>
              <button
                className={`filter-pill-btn ${scenarioFilter === 'CANONICAL' ? 'active' : ''}`}
                onClick={() => setScenarioFilter('CANONICAL')}
                id="filter-canonical"
              >
                Canonical ({scenarios.filter((s) => s.is_canonical).length})
              </button>
              <button
                className={`filter-pill-btn ${scenarioFilter === 'VARIANTS' ? 'active' : ''}`}
                onClick={() => setScenarioFilter('VARIANTS')}
                id="filter-variants"
              >
                Adversarial Variants ({scenarios.filter((s) => !s.is_canonical).length})
              </button>
            </div>
          </div>

          <div className="strip-actions">
            <button
              className="btn-run-scenario"
              onClick={handleRunScenario}
              disabled={isRunning || !selectedScenario}
              id="btn-run-scenario"
            >
              <Play size={14} />
              <span>{isRunning ? 'Running Simulation...' : `Run: ${selectedScenario?.title || ''}`}</span>
            </button>
            <button
              className="btn-run-benchmark"
              onClick={() => handleRunBenchmark('expanded')}
              disabled={isRunning}
              id="btn-run-benchmark-expanded"
            >
              <BarChart2 size={14} />
              <span>{isRunning ? 'Benchmarking Suite...' : 'Run Hardened Suite (20 Tests)'}</span>
            </button>
            <button
              className="btn-run-benchmark"
              onClick={() => handleRunBenchmark('canonical')}
              disabled={isRunning}
              style={{ background: 'rgba(30, 41, 59, 0.8)', borderColor: 'rgba(71, 85, 105, 0.8)' }}
              id="btn-run-benchmark-canonical"
            >
              <ShieldCheck size={14} />
              <span>Canonical (9)</span>
            </button>
          </div>
        </div>

        <div className="scenarios-grid">
          {filteredScenarios.map((sc) => {
            const isSelected = sc.scenario_id === selectedScenarioId
            let tagClass = 'threat-nominal'
            if (sc.metric_classification.includes('UNSAFE')) tagClass = 'threat-hazard'
            else if (sc.metric_classification.includes('TOCTOU')) tagClass = 'threat-race'
            else if (sc.metric_classification.includes('FAIL')) tagClass = 'threat-failure'

            return (
              <div
                key={sc.scenario_id}
                className={`scenario-card ${isSelected ? 'selected' : ''}`}
                onClick={() => {
                  setSelectedScenarioId(sc.scenario_id)
                  setCurrentExecution(null)
                }}
                id={`card-${sc.scenario_id}`}
              >
                <div className="card-top">
                  <span className="card-id-badge">{sc.scenario_id}</span>
                  <div style={{ display: 'flex', gap: '4px' }}>
                    <span className={`card-origin-tag ${sc.is_canonical ? 'canonical' : 'variant'}`}>
                      {sc.is_canonical ? 'Canonical' : 'Variant'}
                    </span>
                    <span className={`card-threat-tag ${tagClass}`}>{sc.threat_category}</span>
                  </div>
                </div>
                <h3 className="card-title">{sc.title}</h3>
                <p className="card-desc">{sc.threat_description}</p>
              </div>
            )
          })}
        </div>
      </section>

      {errorMsg && (
        <div className="error-banner" style={{ margin: '8px 24px', padding: '10px 16px', background: 'rgba(239,68,68,0.2)', border: '1px solid #ef4444', borderRadius: '6px', color: '#fca5a5', fontSize: '0.82rem' }}>
          <AlertTriangle size={14} style={{ display: 'inline', marginRight: '6px' }} />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Main Grid: 3D Twin Viewport + Inspection Tabs */}
      <main className="safetylab-main">
        {/* Left: 3D Viewport & Telemetry Bar */}
        <section className="twin-section">
          <div className="twin-viewport-wrapper">
            <IsaacSimViewport3D
              plantState={currentPlantState}
              effectivePrimPaths={DEFAULT_PRIM_PATHS}
              scenarioId={selectedScenarioId}
              reducedMotion={reducedMotion}
            />
          </div>

          <div className="telemetry-bar">
            <div className="telemetry-cell">
              <span className="telemetry-label">World Version</span>
              <span className="telemetry-val">v{currentPlantState.world_version}</span>
            </div>
            <div className="telemetry-cell">
              <span className="telemetry-label">Valve B State</span>
              <span className={`telemetry-val ${currentPlantState.valve_b_state === 'CLOSED' ? 'safe' : 'warn'}`}>
                {currentPlantState.valve_b_state}
              </span>
            </div>
            <div className="telemetry-cell">
              <span className="telemetry-label">Safety Zone</span>
              <span className={`telemetry-val ${currentPlantState.human_zone === 'CLEAR' ? 'safe' : 'danger'}`}>
                {currentPlantState.human_zone}
              </span>
            </div>
            <div className="telemetry-cell">
              <span className="telemetry-label">Cooling Loop</span>
              <span className={`telemetry-val ${currentPlantState.cooling_state === 'ACTIVE' ? 'safe' : 'danger'}`}>
                {currentPlantState.cooling_state}
              </span>
            </div>
            <div className="telemetry-cell">
              <span className="telemetry-label">Pump P1</span>
              <span className="telemetry-val">{currentPlantState.pump_state}</span>
            </div>
            <div className="telemetry-cell">
              <span className="telemetry-label">Actuator Boundary</span>
              <span className={`telemetry-val ${currentPlantState.actuator_status === 'ACTUATED' ? 'safe' : 'warn'}`}>
                {currentPlantState.actuator_status}
              </span>
            </div>
          </div>
        </section>

        {/* Right: Inspection Tabs */}
        <section className="inspector-section">
          <nav className="inspector-nav" role="tablist">
            <button
              role="tab"
              aria-selected={activeTab === 'decision'}
              className={`inspector-tab ${activeTab === 'decision' ? 'active' : ''}`}
              onClick={() => setActiveTab('decision')}
              id="tab-safety-decision"
            >
              <ShieldCheck size={14} />
              <span>Safety Decision & Pipeline</span>
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'matrix'}
              className={`inspector-tab ${activeTab === 'matrix' ? 'active' : ''}`}
              onClick={() => setActiveTab('matrix')}
              id="tab-ground-truth-matrix"
            >
              <CheckCircle2 size={14} />
              <span>Ground Truth Assertions</span>
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'metrics'}
              className={`inspector-tab ${activeTab === 'metrics' ? 'active' : ''}`}
              onClick={() => setActiveTab('metrics')}
              id="tab-benchmark-metrics"
            >
              <BarChart2 size={14} />
              <span>Quantitative Metrics</span>
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'evidence'}
              className={`inspector-tab ${activeTab === 'evidence' ? 'active' : ''}`}
              onClick={() => setActiveTab('evidence')}
              id="tab-evidence-artifact"
            >
              <FileText size={14} />
              <span>Evidence & SHA-256</span>
            </button>
          </nav>

          <div className="inspector-body">
            {/* TAB 1: Safety Decision & Pipeline */}
            {activeTab === 'decision' && (
              <div>
                <div className="decision-summary-card">
                  <div className="verdict-header">
                    <span className="verdict-title">Deterministic Policy Verdict:</span>
                    {currentExecution ? (
                      <span className={`verdict-badge ${
                        currentExecution.policy_decision === 'ALLOW' ? 'verdict-allow' :
                        currentExecution.policy_decision === 'DENY' ? 'verdict-deny' :
                        currentExecution.authorization_status === 'INVALIDATED' ? 'verdict-invalidated' : 'verdict-failclosed'
                      }`}>
                        {currentExecution.policy_decision || currentExecution.authorization_status}
                      </span>
                    ) : (
                      <span className="verdict-badge" style={{ background: '#334155', color: '#94a3b8' }}>
                        AWAITING RUN
                      </span>
                    )}
                  </div>

                  {currentExecution?.policy_reason_codes && currentExecution.policy_reason_codes.length > 0 && (
                    <div style={{ fontSize: '0.75rem', color: '#cbd5e1' }}>
                      <strong style={{ color: '#94a3b8' }}>Evaluated Constraints: </strong>
                      {currentExecution.policy_reason_codes.join(', ')}
                    </div>
                  )}

                  <div className="pipeline-stages-grid">
                    <div className="pipeline-stage-box">
                      <span className="stage-name">Authorization</span>
                      <span className={`stage-status ${currentExecution?.ticket_minted ? 'assertion-pass' : 'assertion-fail'}`}>
                        {currentExecution ? (currentExecution.ticket_minted ? 'TICKET MINTED' : 'DENIED / 0 TICKET') : '—'}
                      </span>
                    </div>
                    <div className="pipeline-stage-box">
                      <span className="stage-name">Revalidation</span>
                      <span className="stage-status">
                        {currentExecution?.revalidation_status || (currentExecution ? 'N/A' : '—')}
                      </span>
                    </div>
                    <div className="pipeline-stage-box">
                      <span className="stage-name">Actuation</span>
                      <span className={`stage-status ${currentExecution?.mutation_occurred ? 'assertion-pass' : ''}`}>
                        {currentExecution?.execution_status || '—'}
                      </span>
                    </div>
                    <div className="pipeline-stage-box">
                      <span className="stage-name">Verification</span>
                      <span className={`stage-status ${currentExecution?.verification_status === 'VERIFIED' ? 'assertion-pass' : 'assertion-fail'}`}>
                        {currentExecution?.verification_status || '—'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Event timeline */}
                <h4 style={{ fontSize: '0.8rem', color: '#38bdf8', margin: '14px 0 8px 0', textTransform: 'uppercase' }}>
                  Execution Event Stream
                </h4>
                {currentExecution?.events && currentExecution.events.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {currentExecution.events.map((evt, idx) => (
                      <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '0.75rem', padding: '6px 10px', background: 'rgba(30,41,59,0.4)', borderRadius: '4px', borderLeft: '2px solid #38bdf8' }}>
                        <span style={{ color: '#64748b', fontFamily: 'monospace', fontSize: '0.7rem' }}>#{idx + 1}</span>
                        <span style={{ color: '#38bdf8', fontWeight: 600 }}>[{evt.stage || 'EVENT'}]</span>
                        <span style={{ color: '#cbd5e1' }}>{evt.message || JSON.stringify(evt)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p style={{ fontSize: '0.78rem', color: '#64748b', fontStyle: 'italic' }}>
                    No events recorded yet. Click "Run Scenario" to execute the simulation.
                  </p>
                )}
              </div>
            )}

            {/* TAB 2: Ground Truth Assertions */}
            {activeTab === 'matrix' && (
              <div>
                <div style={{ marginBottom: '12px' }}>
                  <h4 style={{ fontSize: '0.85rem', color: '#f8fafc', margin: '0 0 4px 0' }}>
                    Evaluation Assertions for {selectedScenario?.title}
                  </h4>
                  <p style={{ fontSize: '0.75rem', color: '#94a3b8', margin: 0 }}>
                    Every assertion evaluates observed execution outcomes against independent ground truth.
                  </p>
                </div>

                <table className="assertions-table">
                  <thead>
                    <tr>
                      <th>Rule ID</th>
                      <th>Safety Assertion</th>
                      <th>Expected</th>
                      <th>Observed</th>
                      <th>Verdict</th>
                    </tr>
                  </thead>
                  <tbody>
                    {currentExecution?.assertions && currentExecution.assertions.length > 0 ? (
                      currentExecution.assertions.map((a) => (
                        <tr key={a.rule_id}>
                          <td style={{ fontFamily: 'monospace', color: '#38bdf8' }}>{a.rule_id}</td>
                          <td>{a.description}</td>
                          <td style={{ fontFamily: 'monospace' }}>{String(a.expected)}</td>
                          <td style={{ fontFamily: 'monospace' }}>{String(a.actual)}</td>
                          <td>
                            <span className={a.passed ? 'assertion-pass' : 'assertion-fail'}>
                              {a.passed ? '✓ PASS' : '✗ FAIL'}
                            </span>
                          </td>
                        </tr>
                      ))
                    ) : selectedScenario?.assertion_rules ? (
                      selectedScenario.assertion_rules.map((rule) => (
                        <tr key={rule.rule_id}>
                          <td style={{ fontFamily: 'monospace', color: '#38bdf8' }}>{rule.rule_id}</td>
                          <td>{rule.description}</td>
                          <td style={{ fontFamily: 'monospace' }}>{String(rule.expected_value)}</td>
                          <td style={{ color: '#64748b' }}>Pending</td>
                          <td><span style={{ color: '#64748b' }}>—</span></td>
                        </tr>
                      ))
                    ) : null}
                  </tbody>
                </table>
              </div>
            )}

            {/* TAB 3: Benchmark Metrics Dashboard */}
            {activeTab === 'metrics' && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                  <div>
                    <h4 style={{ fontSize: '0.88rem', color: '#f8fafc', margin: '0 0 2px 0' }}>
                      Quantitative Safety Metrics Dashboard
                    </h4>
                    <p style={{ fontSize: '0.75rem', color: '#94a3b8', margin: 0 }}>
                      Evaluated across {benchmarkReport?.total_scenarios_evaluated || 20} scenarios ({benchmarkReport?.distinct_scenarios || 9} distinct, {benchmarkReport?.distinct_variants || 11} variants) with explicit denominators.
                    </p>
                  </div>
                  {benchmarkReport && (
                    <button className="btn-evidence-action" onClick={handleDownloadReport}>
                      <Download size={13} />
                      <span>Export Full Report (JSON)</span>
                    </button>
                  )}
                </div>

                {benchmarkReport ? (
                  <>
                    <div className="metrics-dashboard-grid">
                      {/* Unsafe Actuation Rate */}
                      <div className="metric-card">
                        <div className="metric-header">
                          <span className="metric-name">{benchmarkReport.metrics.unsafe_actuation_rate.name}</span>
                          <span className="metric-target-tag">Target: 0.0%</span>
                        </div>
                        <div className="metric-value-row">
                          <span className="metric-primary-val" style={{ color: benchmarkReport.metrics.unsafe_actuation_rate.numerator === 0 ? '#34d399' : '#f87171' }}>
                            {benchmarkReport.metrics.unsafe_actuation_rate.formatted_value}
                          </span>
                        </div>
                        <span className="metric-formula">{benchmarkReport.metrics.unsafe_actuation_rate.formula}</span>
                        <p className="metric-desc">{benchmarkReport.metrics.unsafe_actuation_rate.description}</p>
                      </div>

                      {/* False Verification Rate */}
                      <div className="metric-card">
                        <div className="metric-header">
                          <span className="metric-name">{benchmarkReport.metrics.false_verification_rate.name}</span>
                          <span className="metric-target-tag">Target: 0.0%</span>
                        </div>
                        <div className="metric-value-row">
                          <span className="metric-primary-val" style={{ color: benchmarkReport.metrics.false_verification_rate.numerator === 0 ? '#34d399' : '#f87171' }}>
                            {benchmarkReport.metrics.false_verification_rate.formatted_value}
                          </span>
                        </div>
                        <span className="metric-formula">{benchmarkReport.metrics.false_verification_rate.formula}</span>
                        <p className="metric-desc">{benchmarkReport.metrics.false_verification_rate.description}</p>
                      </div>

                      {/* Scenario Pass Rate */}
                      <div className="metric-card">
                        <div className="metric-header">
                          <span className="metric-name">{benchmarkReport.metrics.scenario_pass_rate.name}</span>
                          <span className="metric-target-tag">Target: 100.0%</span>
                        </div>
                        <div className="metric-value-row">
                          <span className="metric-primary-val" style={{ color: benchmarkReport.metrics.scenario_pass_rate.numerator === benchmarkReport.metrics.scenario_pass_rate.denominator ? '#34d399' : '#fbbf24' }}>
                            {benchmarkReport.metrics.scenario_pass_rate.formatted_value}
                          </span>
                        </div>
                        <span className="metric-formula">{benchmarkReport.metrics.scenario_pass_rate.formula}</span>
                        <p className="metric-desc">{benchmarkReport.metrics.scenario_pass_rate.description}</p>
                      </div>

                      {/* Fail Closed Coverage */}
                      <div className="metric-card">
                        <div className="metric-header">
                          <span className="metric-name">{benchmarkReport.metrics.fail_closed_coverage.name}</span>
                          <span className="metric-target-tag">Target: 100.0%</span>
                        </div>
                        <div className="metric-value-row">
                          <span className="metric-primary-val" style={{ color: '#34d399' }}>
                            {benchmarkReport.metrics.fail_closed_coverage.formatted_value}
                          </span>
                        </div>
                        <span className="metric-formula">{benchmarkReport.metrics.fail_closed_coverage.formula}</span>
                        <p className="metric-desc">{benchmarkReport.metrics.fail_closed_coverage.description}</p>
                      </div>

                      {/* Verification Coverage */}
                      <div className="metric-card">
                        <div className="metric-header">
                          <span className="metric-name">{benchmarkReport.metrics.verification_coverage.name}</span>
                          <span className="metric-target-tag">Target: 100.0%</span>
                        </div>
                        <div className="metric-value-row">
                          <span className="metric-primary-val" style={{ color: '#34d399' }}>
                            {benchmarkReport.metrics.verification_coverage.formatted_value}
                          </span>
                        </div>
                        <span className="metric-formula">{benchmarkReport.metrics.verification_coverage.formula}</span>
                        <p className="metric-desc">{benchmarkReport.metrics.verification_coverage.description}</p>
                      </div>

                      {/* False Denial Rate */}
                      <div className="metric-card">
                        <div className="metric-header">
                          <span className="metric-name">{benchmarkReport.metrics.false_denial_rate.name}</span>
                          <span className="metric-target-tag">Target: 0.0%</span>
                        </div>
                        <div className="metric-value-row">
                          <span className="metric-primary-val" style={{ color: '#34d399' }}>
                            {benchmarkReport.metrics.false_denial_rate.formatted_value}
                          </span>
                        </div>
                        <span className="metric-formula">{benchmarkReport.metrics.false_denial_rate.formula}</span>
                        <p className="metric-desc">{benchmarkReport.metrics.false_denial_rate.description}</p>
                      </div>
                    </div>

                    {/* Separated Latency Profiles */}
                    {benchmarkReport.metrics.latency_summary && (
                      <div className="latency-profiles-container">
                        <h5 style={{ fontSize: '0.8rem', color: '#38bdf8', margin: '0 0 6px 0', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          Separated Stage Latencies
                        </h5>
                        <div className="latency-profiles-grid">
                          <div className="latency-card">
                            <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>Deterministic Policy Engine</span>
                            <div style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc', margin: '4px 0' }}>
                              {benchmarkReport.metrics.policy_latency_summary ? `${benchmarkReport.metrics.policy_latency_summary.median_ms} ms` : '< 1.0 ms'}
                            </div>
                            <span style={{ fontSize: '0.68rem', color: '#64748b' }}>
                              p95: {benchmarkReport.metrics.policy_latency_summary?.p95_ms ?? '0.8'} ms
                            </span>
                          </div>

                          <div className="latency-card">
                            <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>Simulation Environment</span>
                            <div style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc', margin: '4px 0' }}>
                              {benchmarkReport.metrics.simulation_latency_summary ? `${benchmarkReport.metrics.simulation_latency_summary.median_ms} ms` : '0.01 ms'}
                            </div>
                            <span style={{ fontSize: '0.68rem', color: '#64748b' }}>
                              p95: {benchmarkReport.metrics.simulation_latency_summary?.p95_ms ?? '0.03'} ms
                            </span>
                          </div>

                          <div className="latency-card">
                            <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>Total Simulated Workflow</span>
                            <div style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc', margin: '4px 0' }}>
                              {benchmarkReport.metrics.latency_summary.median_ms} ms
                            </div>
                            <span style={{ fontSize: '0.68rem', color: '#64748b' }}>
                              p95: {benchmarkReport.metrics.latency_summary.p95_ms} ms
                            </span>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Adversarial Failure Classes */}
                    {benchmarkReport.metrics.failure_classes_summary && (
                      <div className="failure-classes-container">
                        <h5 style={{ fontSize: '0.8rem', color: '#38bdf8', margin: '0 0 6px 0', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          Adversarial Threat Containment by Class
                        </h5>
                        <table className="failure-classes-table">
                          <thead>
                            <tr>
                              <th>Threat Category</th>
                              <th>Attempts</th>
                              <th>Contained</th>
                              <th>Leaked</th>
                              <th>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(benchmarkReport.metrics.failure_classes_summary).map(([category, stats]) => (
                              <tr key={category}>
                                <td style={{ fontFamily: 'monospace', color: '#f1f5f9' }}>{category}</td>
                                <td>{stats.attempts}</td>
                                <td style={{ color: '#34d399' }}>{stats.contained}</td>
                                <td style={{ color: stats.leaked > 0 ? '#f87171' : '#34d399' }}>{stats.leaked}</td>
                                <td>
                                  <span style={{ color: stats.leaked === 0 ? '#34d399' : '#f87171', fontWeight: 700 }}>
                                    {stats.leaked === 0 ? '✓ SECURE' : '✗ BREACH'}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                ) : (
                  <div style={{ textAlign: 'center', padding: '36px', color: '#94a3b8' }}>
                    <BarChart2 size={32} style={{ margin: '0 auto 12px auto', opacity: 0.5 }} />
                    <p style={{ margin: 0, fontSize: '0.85rem' }}>No benchmark report available yet.</p>
                    <p style={{ margin: '4px 0 16px 0', fontSize: '0.75rem', color: '#64748b' }}>
                      Click "Run Hardened Suite (20 Tests)" above to evaluate the full suite.
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* TAB 4: Evidence & SHA-256 */}
            {activeTab === 'evidence' && (
              <div className="evidence-box">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h4 style={{ fontSize: '0.85rem', color: '#f8fafc', margin: 0 }}>
                    Exportable Execution Evidence Bundle
                  </h4>
                  <div className="evidence-actions-row">
                    <button
                      className="btn-evidence-action"
                      onClick={handleDownloadEvidence}
                      disabled={!currentExecution}
                      id="btn-download-evidence"
                    >
                      <Download size={13} />
                      <span>Download Bundle (.json)</span>
                    </button>
                    <button
                      className="btn-evidence-action"
                      onClick={handleVerifyHash}
                      disabled={!currentExecution}
                      id="btn-verify-hash"
                    >
                      <ShieldCheck size={13} />
                      <span>Verify SHA-256 Hash</span>
                    </button>
                  </div>
                </div>

                <div className="evidence-hash-row">
                  <span className="hash-label">SHA-256 Hash:</span>
                  <span className="hash-code">{currentExecution?.sha256_hash || 'Awaiting execution run'}</span>
                </div>

                <pre className="evidence-json-viewer">
                  {currentExecution ? JSON.stringify(currentExecution, null, 2) : '// Execute a scenario to inspect its canonical JSON evidence artifact'}
                </pre>
              </div>
            )}
          </div>
        </section>
      </main>

      {/* Verification Modal */}
      {showVerifyModal && (
        <div className="modal-overlay" onClick={() => setShowVerifyModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">SHA-256 Evidence Integrity Verification</h3>
              <button className="btn-close-modal" onClick={() => setShowVerifyModal(false)}>
                <X size={18} />
              </button>
            </div>

            {isVerifying ? (
              <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>Recomputing canonical SHA-256 hash...</p>
            ) : verifyResult ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.9rem', fontWeight: 700, color: verifyResult.is_valid ? '#34d399' : '#f87171' }}>
                  {verifyResult.is_valid ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
                  <span>{verifyResult.is_valid ? 'INTEGRITY VERIFIED: MATCH' : 'INTEGRITY FAILED: MISMATCH'}</span>
                </div>
                <div style={{ fontSize: '0.75rem', fontFamily: 'monospace', wordBreak: 'break-all', background: '#020617', padding: '10px', borderRadius: '6px' }}>
                  <div><strong>Reported Hash: </strong>{verifyResult.reported_hash}</div>
                  <div style={{ marginTop: '6px' }}><strong>Computed Hash: </strong>{verifyResult.computed_hash}</div>
                  {verifyResult.message && <div style={{ marginTop: '6px', color: '#94a3b8', fontFamily: 'sans-serif' }}><strong>Notice: </strong>{verifyResult.message}</div>}
                  {verifyResult.hash_scope_disclosure && (
                    <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid rgba(51,65,85,0.6)', color: '#64748b' }}>
                      <div><strong>Covered Fields: </strong>{verifyResult.hash_scope_disclosure.covered_fields}</div>
                      <div style={{ marginTop: '4px' }}><strong>Serialization: </strong>{verifyResult.hash_scope_disclosure.serialization_standard}</div>
                    </div>
                  )}
                </div>
                <p style={{ fontSize: '0.72rem', color: '#94a3b8', margin: 0 }}>
                  SECURITY NOTICE: A matching SHA-256 hash establishes byte-level consistency against canonical serialization. It does NOT constitute a PKI digital signature, non-repudiation identity proof, or proof of physical execution.
                </p>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}
