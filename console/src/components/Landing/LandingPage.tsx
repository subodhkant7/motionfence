import React, { useState, useEffect } from 'react'
import {
  ShieldCheck,
  ShieldAlert,
  Play,
  ArrowRight,
  ExternalLink,
  Cpu,
  Activity,
  Layers,
  Lock,
  RefreshCw,
  FileCheck2,
  AlertTriangle,
  ZapOff,
  BarChart2,
  FileCode,
  HelpCircle,
  Menu,
  X,
  CheckCircle2,
  Download,
  Eye,
} from 'lucide-react'
import { IsaacSimViewport3D } from '../DigitalTwin/IsaacSimViewport3D'
import { DigitalTwinPlantState, IsaacPrimPaths, BenchmarkReportData } from '../../types'
import { api } from '../../services/api'
import benchmarkFixture from '../../data/benchmark_report.json'
import './LandingPage.css'

interface LandingPageProps {
  onNavigate: (route: 'demo' | 'safety-lab' | 'console' | 'architecture') => void
  reducedMotion: boolean
  onToggleReducedMotion: () => void
}

const DEFAULT_PRIM_PATHS: IsaacPrimPaths = {
  worldPrim: '/World',
  cellPrim: '/World/IndustrialCell',
  valvePrim: '/World/IndustrialCell/ValveB',
  sensorPrim: '/World/IndustrialCell/SensorCluster',
  safetyZonePrim: '/World/IndustrialCell/Sector4SafetyZone',
}

export const LandingPage: React.FC<LandingPageProps> = ({
  onNavigate,
  reducedMotion,
  onToggleReducedMotion,
}) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [benchmarkReport, setBenchmarkReport] = useState<BenchmarkReportData>(benchmarkFixture as any)
  const [activeFaq, setActiveFaq] = useState<number | null>(null)

  // Simulation preview plant state
  const [previewPlantState] = useState<DigitalTwinPlantState>({
    stage_name: 'REPLAY_PREVIEW',
    world_version: 1,
    valve_b_state: 'OPEN',
    human_zone: 'CLEAR',
    cooling_state: 'ACTIVE',
    pump_state: 'INACTIVE',
    leak_active: true,
    flow_rate_lpm: 12.0,
    pressure_psi: 120.0,
    actuator_status: 'NOMINAL',
  })

  // Fetch latest benchmark report on mount
  useEffect(() => {
    async function loadReport() {
      const liveRep = await api.getLatestBenchmarkReport('expanded')
      if (liveRep && liveRep.metrics) {
        setBenchmarkReport(liveRep)
      }
    }
    loadReport()
  }, [])

  const toggleFaq = (index: number) => {
    setActiveFaq((prev) => (prev === index ? null : index))
  }

  const handleDownloadReport = () => {
    const blob = new Blob([JSON.stringify(benchmarkReport, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `motionfence-benchmark-v${benchmarkReport.benchmark_version || '1.1.0'}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const m = benchmarkReport.metrics

  return (
    <div className="landing-container">
      <div className="landing-grid-bg" aria-hidden="true" />

      {/* Navigation Header */}
      <header className="landing-nav" role="banner">
        <a href="#hero" className="landing-nav-brand" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
          <div className="brand-badge">
            <ShieldCheck size={16} />
            <span>MF-GATEWAY</span>
          </div>
          <span className="brand-name">MotionFence</span>
          <span className="brand-status-dot" title="Safety Kernel Active" />
        </a>

        <nav className="landing-nav-links" aria-label="Main Navigation">
          <a href="#problem" className="landing-nav-link">The Problem</a>
          <a href="#how-it-works" className="landing-nav-link">How It Works</a>
          <a href="#features" className="landing-nav-link">Features</a>
          <a href="#benchmark" className="landing-nav-link">Benchmark (20 Tests)</a>
          <a href="#architecture" className="landing-nav-link">Architecture</a>
          <a href="#faq" className="landing-nav-link">FAQ</a>
        </nav>

        <div className="landing-nav-actions">
          <button
            className="btn-nav-demo"
            onClick={() => onNavigate('demo')}
            id="nav-btn-demo"
            title="Launch Full 1-Click Interactive Demo"
          >
            <Play size={13} fill="currentColor" />
            <span>Interactive Demo</span>
          </button>

          <button
            className="btn-nav-safetylab"
            onClick={() => onNavigate('safety-lab')}
            id="nav-btn-safetylab"
            title="Open Public Safety Lab and Benchmark"
          >
            <ShieldCheck size={13} />
            <span>Safety Lab</span>
          </button>

          <button
            className="btn-nav-demo"
            onClick={() => onNavigate('console')}
            id="nav-btn-console"
            title="Open Judge Decision Replay Console"
            style={{ padding: '7px 11px', fontSize: '0.8rem', color: '#94a3b8' }}
          >
            <span>Console</span>
          </button>

          <button
            className="btn-nav-icon"
            onClick={onToggleReducedMotion}
            title={reducedMotion ? 'Reduced Motion: ON' : 'Reduced Motion: OFF'}
            aria-label="Toggle Reduced Motion"
          >
            {reducedMotion ? <ZapOff size={14} /> : <Eye size={14} />}
          </button>

          <a
            href="https://github.com/subodhkant7/motionfence"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-nav-icon"
            title="View Source on GitHub"
            aria-label="GitHub Repository"
          >
            <ExternalLink size={14} />
          </a>

          <button
            className="btn-mobile-menu-toggle"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle Navigation Menu"
          >
            {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
      </header>

      {/* Mobile Navigation Dropdown */}
      {mobileMenuOpen && (
        <div className="landing-mobile-nav open">
          <a href="#problem" onClick={() => setMobileMenuOpen(false)}>The Problem</a>
          <a href="#how-it-works" onClick={() => setMobileMenuOpen(false)}>How It Works</a>
          <a href="#features" onClick={() => setMobileMenuOpen(false)}>Features</a>
          <a href="#benchmark" onClick={() => setMobileMenuOpen(false)}>Benchmark & Metrics</a>
          <a href="#architecture" onClick={() => setMobileMenuOpen(false)}>Architecture</a>
          <a href="#faq" onClick={() => setMobileMenuOpen(false)}>FAQ</a>
          <button onClick={() => { setMobileMenuOpen(false); onNavigate('safety-lab'); }}>Public Safety Lab</button>
          <button onClick={() => { setMobileMenuOpen(false); onNavigate('demo'); }}>Interactive Demo</button>
          <button onClick={() => { setMobileMenuOpen(false); onNavigate('console'); }}>Judge Console</button>
        </div>
      )}

      {/* Hero Section */}
      <section className="landing-hero" id="hero">
        <div className="hero-content">
          <div className="hero-eyebrow">
            <span className="eyebrow-pulse" />
            <span>AI PROPOSALS. DETERMINISTIC SAFETY.</span>
          </div>

          <h1 className="hero-headline">
            AI can propose the action.{' '}
            <span className="hero-headline-highlight">It shouldn't decide whether it's safe.</span>
          </h1>

          <p className="hero-subheading">
            MotionFence is an experimental safety-assurance layer for AI-proposed industrial actions.
            It evaluates proposals against deterministic policies, revalidates state before execution,
            and checks the resulting physical outcome independently.
          </p>

          <div className="hero-cta-group">
            <button
              className="btn-hero-primary"
              onClick={() => onNavigate('safety-lab')}
              id="hero-cta-safetylab"
            >
              <ShieldCheck size={18} />
              <span>Explore the Safety Lab</span>
              <ArrowRight size={16} />
            </button>

            <button
              className="btn-hero-secondary"
              onClick={() => onNavigate('demo')}
              id="hero-cta-demo"
            >
              <Play size={16} fill="currentColor" />
              <span>Run Interactive Demo</span>
            </button>

            <a href="#architecture" className="btn-hero-tertiary">
              <span>Read Benchmark Methodology</span>
              <ArrowRight size={14} />
            </a>
          </div>

          <div className="hero-status-ribbon">
            <div className="ribbon-item">
              <span>Active Model:</span>
              <strong>Nemotron-3-Super 120B (Nebius)</strong>
            </div>
            <div className="ribbon-item">
              <span>Policy Kernel:</span>
              <strong>Deterministic Python Safety Enclave</strong>
            </div>
            <div className="ribbon-item">
              <span>Benchmark:</span>
              <strong>v1.1.0 (20 Adversarial Tests)</strong>
            </div>
          </div>
        </div>

        {/* Hero Visual Card: Contract Simulator Preview */}
        <div className="hero-visual-card">
          <div className="hero-visual-header">
            <div className="visual-badge">
              <Activity size={13} />
              <span>CONTRACT SIMULATOR · INDUSTRIAL CELL TWIN</span>
            </div>
            <span style={{ fontSize: '0.72rem', color: '#64748b', fontFamily: 'monospace' }}>
              REPLAY REVISION: v1
            </span>
          </div>

          <div className="hero-visual-body">
            <IsaacSimViewport3D
              plantState={previewPlantState}
              effectivePrimPaths={DEFAULT_PRIM_PATHS}
              scenarioId="safe_valve_operation"
              reducedMotion={reducedMotion}
            />
          </div>

          <div className="hero-visual-footer">
            <div className="preview-telemetry-item">
              <span className="preview-label">Valve B</span>
              <span className={`preview-val ${previewPlantState.valve_b_state === 'OPEN' ? 'danger' : 'safe'}`}>
                {previewPlantState.valve_b_state} (12.0 LPM)
              </span>
            </div>
            <div className="preview-telemetry-item">
              <span className="preview-label">Safety Zone</span>
              <span className={`preview-val ${previewPlantState.human_zone === 'CLEAR' ? 'safe' : 'danger'}`}>
                SECTOR 4 {previewPlantState.human_zone}
              </span>
            </div>
            <div className="preview-telemetry-item">
              <span className="preview-label">Cooling</span>
              <span className="preview-val safe">{previewPlantState.cooling_state}</span>
            </div>
            <button
              className="btn-nav-demo"
              onClick={() => onNavigate('demo')}
              style={{ fontSize: '0.76rem', padding: '5px 10px' }}
            >
              <span>Launch 3D Director</span>
              <ArrowRight size={12} />
            </button>
          </div>
        </div>
      </section>

      {/* Section 1: The Verification Gap in Physical AI (Problem) */}
      <section className="landing-section" id="problem">
        <div className="section-header">
          <div className="section-tag">
            <AlertTriangle size={13} />
            <span>The Verification Gap</span>
          </div>
          <h2 className="section-title">Generative AI plans actions. It cannot guarantee physical safety.</h2>
          <p className="section-subtitle">
            Language and multimodal models predict plausible tokens based on statistical likelihood.
            In industrial automation and robotics, equating a model's generated plan with authorization
            creates critical risks across the execution boundary.
          </p>
        </div>

        <div className="problem-comparison-box">
          <div className="problem-col">
            <div className="col-header flawed">
              <X size={14} />
              <span>Unverified AI Control (Flawed)</span>
            </div>
            <p>
              LLM agent generates an action sequence (e.g. "Close emergency isolation valve"). The command is directly
              transmitted to industrial hardware or robotics actuators. If human workers entered the cell, if sensor
              telemetry drifted, or if the model experienced a prompt injection or hallucination, catastrophic damage occurs.
            </p>
          </div>

          <div className="problem-col">
            <div className="col-header enforced">
              <CheckCircle2 size={14} />
              <span>MotionFence Runtime Authorization (Enforced)</span>
            </div>
            <p>
              The AI model remains completely unprivileged. Its output is treated as an untrusted proposal. MotionFence
              evaluates the proposal against deterministic policy invariants, issues an HMAC-signed single-use ticket,
              revalidates state at the hardware boundary (TOCTOU defense), and independently verifies the physical sensor outcome.
            </p>
          </div>
        </div>

        {/* 6 Failure Classes */}
        <div className="failure-classes-grid">
          <div className="failure-class-card">
            <div className="class-header">
              <span className="class-category-badge">HAZARD_ZONE_VIOLATION</span>
            </div>
            <h3 className="class-title">Worker in Safety Zone</h3>
            <p className="class-desc">
              Human operator enters restricted Sector 4 during proposal lifecycle. The AI suggests rapid valve isolation.
            </p>
            <div className="class-defense">
              Defense: Policy engine strictly DENIES actuation; zero tickets minted; valve preserved OPEN.
            </div>
          </div>

          <div className="failure-class-card">
            <div className="class-header">
              <span className="class-category-badge">TOCTOU_STATE_RACE</span>
            </div>
            <h3 className="class-title">Time-of-Check to Time-of-Use Drift</h3>
            <p className="class-desc">
              Plant state is safe when authorization is evaluated, but changes (cooling loop fails, pump starts) before the command reaches hardware.
            </p>
            <div className="class-defense">
              Defense: State-bound HMAC ticket invalidated at presentation barrier; execution blocked.
            </div>
          </div>

          <div className="failure-class-card">
            <div className="class-header">
              <span className="class-category-badge">EPISTEMIC_GROUNDING_FAILURE</span>
            </div>
            <h3 className="class-title">Contradictory / Stale Telemetry</h3>
            <p className="class-desc">
              Overhead camera detects a leak while pressure transducer contradicts, or evidence timestamp is stale.
            </p>
            <div className="class-defense">
              Defense: Safety enclave detects contradiction and fails closed with NEED_MORE_EVIDENCE.
            </div>
          </div>

          <div className="failure-class-card">
            <div className="class-header">
              <span className="class-category-badge">PROVIDER_DEGRADATION</span>
            </div>
            <h3 className="class-title">Provider Outages & Prompt Injection</h3>
            <p className="class-desc">
              Inference provider returns HTTP 503, times out after 5.0s, or intent contains adversarial prompt injections.
            </p>
            <div className="class-defense">
              Defense: Deterministic fallback fails closed; zero mutations; malformed payloads rejected.
            </div>
          </div>

          <div className="failure-class-card">
            <div className="class-header">
              <span className="class-category-badge">SILENT_MECHANICAL_FAILURE</span>
            </div>
            <h3 className="class-title">Mechanical Actuator Failure</h3>
            <p className="class-desc">
              Actuator command executes without error, but physical valve jams or stops at 60% partial stroke travel.
            </p>
            <div className="class-defense">
              Defense: Independent postcondition verifier detects discrepancy; marks FAILED and alerts.
            </div>
          </div>

          <div className="failure-class-card">
            <div className="class-header">
              <span className="class-category-badge">COMMAND_REPLAY_ATTACK</span>
            </div>
            <h3 className="class-title">Replay Attacks & Double-Spending</h3>
            <p className="class-desc">
              Network adversary captures valid authorization ticket and replays it, or attempts concurrent double-consumption.
            </p>
            <div className="class-defense">
              Defense: Single-use cryptographic nonce; subsequent presentations strictly rejected.
            </div>
          </div>
        </div>

        <div className="disclaimer-banner">
          <ShieldAlert size={18} style={{ flexShrink: 0, color: '#f59e0b' }} />
          <div>
            <strong>Synthetic Testing Boundary Disclosure:</strong> These failure modes represent bounded, reproducible
            adversarial test cases evaluated against ground-truth assertions in our synthetic industrial cell. They provide
            quantitative benchmarks of software safety boundaries, not an empirical proof that all real-world physical hazards have been eliminated.
          </div>
        </div>
      </section>

      {/* Section 2: How It Works (6-Stage Pipeline) */}
      <section className="landing-section" id="how-it-works">
        <div className="section-header">
          <div className="section-tag">
            <Cpu size={13} />
            <span>Architecture in Motion</span>
          </div>
          <h2 className="section-title">The Six-Stage Safety-Assurance Pipeline</h2>
          <p className="section-subtitle">
            Every AI-generated physical action must traverse six independent verification barriers before
            and after hardware execution. The AI is strictly a proposal generator, never the safety authority.
          </p>
        </div>

        <div className="pipeline-stages-container">
          <div className="pipeline-stage-card">
            <div className="stage-step-num">
              <span>STAGE 01</span>
              <Cpu size={14} />
            </div>
            <h3 className="stage-name">Propose</h3>
            <p className="stage-desc">
              Nebius Token Factory / Nemotron 120B model suggests an unprivileged action intent from sensor observations.
            </p>
            <div className="stage-failure-path">Fallback: Timeout / 503 → Fail Closed</div>
          </div>

          <div className="pipeline-stage-card">
            <div className="stage-step-num">
              <span>STAGE 02</span>
              <ShieldCheck size={14} />
            </div>
            <h3 className="stage-name">Evaluate</h3>
            <p className="stage-desc">
              Deterministic policy rules evaluate human safety zones, active cooling, pressure thresholds, and evidence provenance.
            </p>
            <div className="stage-failure-path">Branch: Hazard → DENY (0 Tickets)</div>
          </div>

          <div className="pipeline-stage-card">
            <div className="stage-step-num">
              <span>STAGE 03</span>
              <Lock size={14} />
            </div>
            <h3 className="stage-name">Revalidate</h3>
            <p className="stage-desc">
              Immediately before actuation, plant state hash and ticket freshness nonce are re-verified to prevent TOCTOU drift.
            </p>
            <div className="stage-failure-path">Branch: Drift → Ticket Invalidated</div>
          </div>

          <div className="pipeline-stage-card">
            <div className="stage-step-num">
              <span>STAGE 04</span>
              <Play size={14} />
            </div>
            <h3 className="stage-name">Execute</h3>
            <p className="stage-desc">
              Hardware endpoint validates HMAC authorization ticket and commands physical valve actuator in the synthetic cell.
            </p>
            <div className="stage-failure-path">Branch: Replay → Actuation Locked</div>
          </div>

          <div className="pipeline-stage-card">
            <div className="stage-step-num">
              <span>STAGE 05</span>
              <FileCheck2 size={14} />
            </div>
            <h3 className="stage-name">Verify</h3>
            <p className="stage-desc">
              Postcondition verifier independently queries physical sensors to confirm the valve reached required closed state.
            </p>
            <div className="stage-failure-path">Branch: Jam → Verification Failed</div>
          </div>

          <div className="pipeline-stage-card">
            <div className="stage-step-num">
              <span>STAGE 06</span>
              <FileCode size={14} />
            </div>
            <h3 className="stage-name">Record</h3>
            <p className="stage-desc">
              RFC 8785 Canonical JSON evidence bundle is assembled and cryptographically hashed with SHA-256 for auditability.
            </p>
            <div className="stage-failure-path">Integrity: Tamper-Evident SHA-256</div>
          </div>
        </div>

        <div style={{ textAlign: 'center', marginTop: '36px' }}>
          <button
            className="btn-hero-primary"
            onClick={() => onNavigate('demo')}
            style={{ margin: '0 auto' }}
          >
            <Play size={15} fill="currentColor" />
            <span>Watch Pipeline in 1-Click Interactive Demo</span>
            <ArrowRight size={14} />
          </button>
        </div>
      </section>

      {/* Section 3: Core Features */}
      <section className="landing-section" id="features">
        <div className="section-header">
          <div className="section-tag">
            <Layers size={13} />
            <span>Core Capabilities</span>
          </div>
          <h2 className="section-title">Engineered for Uncompromising Physical Assurance</h2>
          <p className="section-subtitle">
            Built from first principles to bridge the gap between stochastic reasoning and deterministic robotics safety.
          </p>
        </div>

        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-icon-wrapper">
              <ShieldCheck size={20} />
            </div>
            <h3 className="feature-title">Deterministic Safety Gate</h3>
            <p className="feature-desc">
              Policy rules written in pure Python enforce hard physical constraints. Model reasoning has zero privilege
              to bypass or mutate safety rules. All evaluations complete deterministically under 3 milliseconds.
            </p>
            <button className="feature-link" onClick={() => onNavigate('console')}>
              <span>View Policy Firewall</span>
              <ArrowRight size={13} />
            </button>
          </div>

          <div className="feature-card">
            <div className="feature-icon-wrapper">
              <RefreshCw size={20} />
            </div>
            <h3 className="feature-title">Execution-Time Revalidation</h3>
            <p className="feature-desc">
              Mitigates Time-of-Check to Time-of-Use (TOCTOU) races. Re-validates world state version, cooling status, and
              operator zones at the hardware barrier before allowing mechanical motion.
            </p>
            <button className="feature-link" onClick={() => onNavigate('demo')}>
              <span>Test TOCTOU Scenario</span>
              <ArrowRight size={13} />
            </button>
          </div>

          <div className="feature-card">
            <div className="feature-icon-wrapper">
              <Lock size={20} />
            </div>
            <h3 className="feature-title">Controlled Execution Boundary</h3>
            <p className="feature-desc">
              Separates generative planning from hardware actuation. Hardware endpoints require an HMAC-SHA256 authorization
              ticket with cryptographic state binding and single-use nonce.
            </p>
            <button className="feature-link" onClick={() => onNavigate('architecture')}>
              <span>Inspect Security Boundary</span>
              <ArrowRight size={13} />
            </button>
          </div>

          <div className="feature-card">
            <div className="feature-icon-wrapper">
              <FileCheck2 size={20} />
            </div>
            <h3 className="feature-title">Independent Outcome Verification</h3>
            <p className="feature-desc">
              Never equates command transmission with physical success. An independent verifier queries distinct telemetry
              transducers to confirm mechanical travel before declaring an operation complete.
            </p>
            <button className="feature-link" onClick={() => onNavigate('safety-lab')}>
              <span>Inspect Verification Logic</span>
              <ArrowRight size={13} />
            </button>
          </div>

          <div className="feature-card">
            <div className="feature-icon-wrapper">
              <BarChart2 size={20} />
            </div>
            <h3 className="feature-title">Public Safety Lab & Benchmark</h3>
            <p className="feature-desc">
              Evaluate 20 distinct ground-truth scenarios (9 canonical + 11 adversarial variants). Toggle between 100% offline
              deterministic replay and live Nebius Nemotron inference with complete metric calculations.
            </p>
            <button className="feature-link" onClick={() => onNavigate('safety-lab')}>
              <span>Open Public Safety Lab</span>
              <ArrowRight size={13} />
            </button>
          </div>

          <div className="feature-card">
            <div className="feature-icon-wrapper">
              <FileCode size={20} />
            </div>
            <h3 className="feature-title">Cryptographic Evidence Integrity</h3>
            <p className="feature-desc">
              Every decision and postcondition check generates an RFC 8785 Canonical JSON evidence bundle with SHA-256
              tamper detection, accompanied by unambiguous disclosures of cryptographic scope.
            </p>
            <button className="feature-link" onClick={() => onNavigate('safety-lab')}>
              <span>Verify Evidence Online</span>
              <ArrowRight size={13} />
            </button>
          </div>
        </div>
      </section>

      {/* Section 4: Real Benchmark & Metrics Dashboard */}
      <section className="landing-section" id="benchmark">
        <div className="section-header">
          <div className="section-tag">
            <BarChart2 size={13} />
            <span>Quantitative Safety Benchmark</span>
          </div>
          <h2 className="section-title">Empirical Benchmark Results (v1.1.0)</h2>
          <p className="section-subtitle">
            Ground-truth safety assertions evaluated across 20 distinct scenarios. Every metric features an explicit numerator
            and denominator. Zero denominators produce N/A. No artificial repetition padding.
          </p>
        </div>

        <div className="benchmark-card-container">
          <div className="benchmark-meta-strip">
            <div className="meta-group">
              <div className="meta-item">
                <span>Registry Version:</span>
                <strong>v{benchmarkReport.registry_version || '1.1.0'}</strong>
              </div>
              <div className="meta-item">
                <span>Evaluated Scenarios:</span>
                <strong>{benchmarkReport.total_scenarios_evaluated || 20} (9 Canonical + 11 Variants)</strong>
              </div>
              <div className="meta-item">
                <span>Execution Mode:</span>
                <strong>{benchmarkReport.execution_mode || 'DETERMINISTIC_REPLAY'}</strong>
              </div>
            </div>

            <div className="meta-item">
              <span>SHA-256 Artifact Hash:</span>
              <strong style={{ fontSize: '0.72rem' }}>
                {benchmarkReport.sha256_hash ? `${benchmarkReport.sha256_hash.slice(0, 16)}...` : '4297f7a463cb...'}
              </strong>
            </div>
          </div>

          {/* 6 Metric Highlight Cards */}
          <div className="metrics-summary-grid">
            <div className="metric-highlight-box">
              <div className="metric-name-row">
                <span className="metric-name">Unsafe Actuation Rate</span>
                <span className="metric-target-tag">Target: 0.0%</span>
              </div>
              <div className="metric-val-large safe">{m?.unsafe_actuation_rate?.formatted_value || '0/12 (0.0%)'}</div>
              <div className="metric-formula-sub">unsafe_actuations / total_unsafe_attempts</div>
            </div>

            <div className="metric-highlight-box">
              <div className="metric-name-row">
                <span className="metric-name">False-Verification Rate</span>
                <span className="metric-target-tag">Target: 0.0%</span>
              </div>
              <div className="metric-val-large safe">{m?.false_verification_rate?.formatted_value || '0/2 (0.0%)'}</div>
              <div className="metric-formula-sub">false_verifications / injected_failures</div>
            </div>

            <div className="metric-highlight-box">
              <div className="metric-name-row">
                <span className="metric-name">Scenario Pass Rate</span>
                <span className="metric-target-tag">Target: 100%</span>
              </div>
              <div className="metric-val-large safe">{m?.scenario_pass_rate?.formatted_value || '20/20 (100.0%)'}</div>
              <div className="metric-formula-sub">passed_scenarios / total_evaluated</div>
            </div>

            <div className="metric-highlight-box">
              <div className="metric-name-row">
                <span className="metric-name">False-Denial Rate</span>
                <span className="metric-target-tag">Target: 0.0%</span>
              </div>
              <div className="metric-val-large safe">{m?.false_denial_rate?.formatted_value || '0/4 (0.0%)'}</div>
              <div className="metric-formula-sub">denied_safe_ops / eligible_safe_ops</div>
            </div>

            <div className="metric-highlight-box">
              <div className="metric-name-row">
                <span className="metric-name">Fail-Closed Coverage</span>
                <span className="metric-target-tag">Target: 100%</span>
              </div>
              <div className="metric-val-large safe">{m?.fail_closed_coverage?.formatted_value || '7/7 (100.0%)'}</div>
              <div className="metric-formula-sub">safely_contained / dependency_failures</div>
            </div>

            <div className="metric-highlight-box">
              <div className="metric-name-row">
                <span className="metric-name">Verification Coverage</span>
                <span className="metric-target-tag">Target: 100%</span>
              </div>
              <div className="metric-val-large safe">{m?.verification_coverage?.formatted_value || '7/7 (100.0%)'}</div>
              <div className="metric-formula-sub">verified_actuations / total_executed</div>
            </div>
          </div>

          {/* Separated Latency Breakdown */}
          <div className="benchmark-latency-breakdown">
            <div className="latency-col">
              <span className="latency-title">Policy Engine Latency</span>
              <span className="latency-stats">
                {m?.policy_latency_summary?.median_ms ?? 0.40} ms{' '}
                <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
                  (p95: {m?.policy_latency_summary?.p95_ms ?? 2.75} ms)
                </span>
              </span>
              <span className="latency-context">Local deterministic policy constraint evaluation</span>
            </div>

            <div className="latency-col">
              <span className="latency-title">Simulation Twin Latency</span>
              <span className="latency-stats">
                {m?.simulation_latency_summary?.median_ms ?? 0.02} ms{' '}
                <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
                  (p95: {m?.simulation_latency_summary?.p95_ms ?? 0.08} ms)
                </span>
              </span>
              <span className="latency-context">In-memory synthetic industrial cell state transitions</span>
            </div>

            <div className="latency-col">
              <span className="latency-title">Total Wall-Clock Latency</span>
              <span className="latency-stats">
                {m?.latency_summary?.median_ms ?? 0.75} ms{' '}
                <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
                  (p95: {m?.latency_summary?.p95_ms ?? 3.09} ms)
                </span>
              </span>
              <span className="latency-context">Complete cycle: proposal + gate + reval + actuation + verifier</span>
            </div>
          </div>

          {/* Adversarial Threat Containment Table */}
          <div className="table-responsive">
            <table className="threat-matrix-table" aria-label="Adversarial Threat Containment Summary">
              <thead>
                <tr>
                  <th>Threat Category</th>
                  <th>Injected Attempts</th>
                  <th>Safely Contained</th>
                  <th>Leaked Actuations</th>
                  <th>Containment Status</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="threat-cat-tag">HAZARD_ZONE_VIOLATION</td>
                  <td>1</td>
                  <td>1</td>
                  <td>0</td>
                  <td style={{ color: '#10b981', fontWeight: 600 }}>100% CONTAINED</td>
                </tr>
                <tr>
                  <td className="threat-cat-tag">TOCTOU_STATE_RACE</td>
                  <td>4</td>
                  <td>4</td>
                  <td>0</td>
                  <td style={{ color: '#10b981', fontWeight: 600 }}>100% CONTAINED</td>
                </tr>
                <tr>
                  <td className="threat-cat-tag">EPISTEMIC_GROUNDING_FAILURE</td>
                  <td>3</td>
                  <td>3</td>
                  <td>0</td>
                  <td style={{ color: '#10b981', fontWeight: 600 }}>100% CONTAINED</td>
                </tr>
                <tr>
                  <td className="threat-cat-tag">PROVIDER_DEGRADATION</td>
                  <td>4</td>
                  <td>4</td>
                  <td>0</td>
                  <td style={{ color: '#10b981', fontWeight: 600 }}>100% CONTAINED</td>
                </tr>
                <tr>
                  <td className="threat-cat-tag">SILENT_MECHANICAL_FAILURE</td>
                  <td>2</td>
                  <td>2</td>
                  <td>0</td>
                  <td style={{ color: '#10b981', fontWeight: 600 }}>100% CONTAINED</td>
                </tr>
                <tr>
                  <td className="threat-cat-tag">COMMAND_REPLAY_ATTACK</td>
                  <td>2</td>
                  <td>2</td>
                  <td>0</td>
                  <td style={{ color: '#10b981', fontWeight: 600 }}>100% CONTAINED</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="benchmark-actions-row">
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <button
                className="btn-hero-primary"
                onClick={() => onNavigate('safety-lab')}
                id="btn-benchmark-run-lab"
              >
                <Play size={15} fill="currentColor" />
                <span>Run Benchmark in Safety Lab</span>
              </button>

              <button
                className="btn-hero-secondary"
                onClick={handleDownloadReport}
                id="btn-download-benchmark-json"
              >
                <Download size={15} />
                <span>Download Canonical JSON Report</span>
              </button>
            </div>

            <span style={{ fontSize: '0.8rem', color: '#64748b', fontFamily: 'monospace' }}>
              Build ID: {benchmarkReport.build_id || 'motionfence-milestone-safety-lab-hardened'}
            </span>
          </div>
        </div>
      </section>

      {/* Section 5: Architecture and Methodology */}
      <section className="landing-section" id="architecture">
        <div className="section-header">
          <div className="section-tag">
            <Layers size={13} />
            <span>Technical Methodology</span>
          </div>
          <h2 className="section-title">Authoritative Safety Boundaries</h2>
          <p className="section-subtitle">
            Rigorous separation of concerns: generative AI models propose unprivileged intents, while deterministic
            enclaves authorize and verify physical state changes.
          </p>
        </div>

        <div className="architecture-diagram-wrapper">
          <h3 style={{ fontSize: '1.2rem', color: '#ffffff', marginBottom: '8px' }}>
            System Boundary Architecture
          </h3>
          <p style={{ fontSize: '0.9rem', color: '#94a3b8' }}>
            The MotionFence security model separates components by authorization privilege:
          </p>

          <div className="arch-layers-grid">
            <div className="arch-layer-card">
              <span className="layer-tag untrusted">UNTRUSTED LAYER</span>
              <h4 className="layer-title">Inference Provider</h4>
              <p className="layer-desc">
                Nebius Token Factory / Nemotron 120B. Possesses ZERO authorization or execution privileges.
                Proposals are treated as untrusted JSON input.
              </p>
            </div>

            <div className="arch-layer-card">
              <span className="layer-tag enclave">AUTHORITATIVE GATE</span>
              <h4 className="layer-title">Policy & Revalidator</h4>
              <p className="layer-desc">
                Pure deterministic Python enclave. Evaluates human zone limits, pressure thresholds, and evidence provenance.
                Issues state-bound HMAC-signed tickets.
              </p>
            </div>

            <div className="arch-layer-card">
              <span className="layer-tag boundary">EXECUTION BOUNDARY</span>
              <h4 className="layer-title">Synthetic Plant Twin</h4>
              <p className="layer-desc">
                Contract Simulator / OpenUSD digital twin. Actuation primitives strictly require a valid, unexpired,
                unplayed HMAC ticket before mutating state.
              </p>
            </div>

            <div className="arch-layer-card">
              <span className="layer-tag audit">AUDIT & VERIFICATION</span>
              <h4 className="layer-title">Independent Verifier</h4>
              <p className="layer-desc">
                Queries physical sensor observations post-actuation. Generates RFC 8785 Canonical JSON evidence bundles
                with SHA-256 tamper-evident integrity.
              </p>
            </div>
          </div>

          {/* Architectural Intent vs Empirical Behavior Table */}
          <h4 style={{ fontSize: '1rem', color: '#f8fafc', marginTop: '36px', marginBottom: '12px' }}>
            Architectural Intent vs. Empirically Verified Synthetic Behavior
          </h4>

          <div className="table-responsive">
            <table className="intent-vs-reality-table" aria-label="Architectural Intent vs Empirical Behavior">
              <thead>
                <tr>
                  <th style={{ width: '22%' }}>Safety Feature</th>
                  <th style={{ width: '39%' }}>Architectural Intent</th>
                  <th style={{ width: '39%' }}>Empirically Verified Synthetic Behavior</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>Worker Hazard Protection</strong></td>
                  <td>Prevent physical actuation when human operators occupy dangerous machinery zones.</td>
                  <td>Verified: Sector 4 occupied state strictly yields DENY and blocks valve mutation across 100% of benchmark runs.</td>
                </tr>
                <tr>
                  <td><strong>TOCTOU Drift Mitigation</strong></td>
                  <td>Ensure authorizations expire immediately if physical plant conditions shift before execution.</td>
                  <td>Verified: Plant state hash and freshness nonce mismatches successfully invalidate tickets at presentation barrier.</td>
                </tr>
                <tr>
                  <td><strong>Mechanical Verification</strong></td>
                  <td>Detect silent actuator motor jams or broken linkage rods in industrial machinery.</td>
                  <td>Verified: Injected actuator partial-stroke and no-op faults are caught with 0% false verification rate.</td>
                </tr>
                <tr>
                  <td><strong>Cryptographic Auditability</strong></td>
                  <td>Provide tamper-evident evidence logs of all agent proposals and safety enforcement actions.</td>
                  <td>Verified: RFC 8785 Canonical JSON serialization with SHA-256 integrity verification detects arbitrary byte tampering.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Section 6: Transparent Runtime and Limitations */}
      <section className="landing-section" id="limitations">
        <div className="section-header">
          <div className="section-tag">
            <AlertTriangle size={13} />
            <span>Honest Disclosures</span>
          </div>
          <h2 className="section-title">Transparent Runtime & Simulator Disclosures</h2>
          <p className="section-subtitle">
            Clear technical boundaries distinguishing hosted simulation capabilities from physical industrial deployment.
          </p>
        </div>

        <div className="runtime-disclosure-grid">
          <div className="disclosure-card">
            <div className="disclosure-header">
              <Activity size={18} color="#38bdf8" />
              <span>Contract Simulator (Browser Digital Twin)</span>
            </div>
            <p>
              The hosted 3D experience in this application runs our deterministic Contract Simulator. It simulates industrial
              valves, fluid dynamics, pressure transducers, and worker hazard zones in the browser. It is not a live streaming
              session of native NVIDIA Isaac Sim running in Cloud Run.
            </p>
          </div>

          <div className="disclosure-card">
            <div className="disclosure-header">
              <Download size={18} color="#818cf8" />
              <span>NVIDIA Isaac Sim Stage & Runner Export</span>
            </div>
            <p>
              For users with compatible Linux/Windows RTX workstations, MotionFence exports complete OpenUSD scene specs
              (<code>/api/isaac/scene.usda</code>) and a standalone Python runner script (<code>/api/isaac/runner.py</code>) to
              execute identical scenarios in native NVIDIA Isaac Sim.
            </p>
          </div>

          <div className="disclosure-card">
            <div className="disclosure-header">
              <ShieldAlert size={18} color="#f59e0b" />
              <span>Experimental Prototype (Not Certified)</span>
            </div>
            <p>
              MotionFence is an experimental software research prototype demonstrating runtime safety gates for physical AI.
              It is NOT an IEC 61508 or ISO 13849 certified industrial safety controller and must not be used to directly control
              hazardous physical machinery without certified physical interlocks.
            </p>
          </div>

          <div className="disclosure-card">
            <div className="disclosure-header">
              <Lock size={18} color="#10b981" />
              <span>Cryptographic Hash Scope</span>
            </div>
            <p>
              The SHA-256 hash published with evidence bundles establishes byte-level consistency against RFC 8785 canonical
              JSON serialization. It provides tamper detection against retroactive record mutation; it does NOT constitute a PKI
              digital signature or cryptographic proof of physical real-world actuation.
            </p>
          </div>
        </div>
      </section>

      {/* Section 7: Frequently Asked Questions (FAQ) */}
      <section className="landing-section" id="faq">
        <div className="section-header">
          <div className="section-tag">
            <HelpCircle size={13} />
            <span>Common Questions</span>
          </div>
          <h2 className="section-title">Frequently Asked Questions</h2>
          <p className="section-subtitle">
            Engineering-focused explanations regarding MotionFence's design, verification, and limits.
          </p>
        </div>

        <div className="faq-list">
          {[
            {
              q: 'What is MotionFence?',
              a: 'MotionFence is an experimental deterministic runtime authorization and safety-assurance layer for AI-proposed industrial actions. It sits between probabilistic generative AI agents and industrial execution endpoints to evaluate, revalidate, and verify physical actions.',
            },
            {
              q: "Why isn't the language model trusted to authorize actions?",
              a: 'Generative AI models are probabilistic token predictors. They are susceptible to prompt injection, hallucinated actuator parameters, out-of-context commands, and training distribution shift. Industrial safety requires formal, deterministic invariants that cannot be overridden by conversational reasoning.',
            },
            {
              q: 'What happens when upstream inference fails or times out?',
              a: 'MotionFence operates under a strict fail-closed security posture. If the model provider times out (5.0s budget), returns an HTTP 500/503 outage, or emits malformed JSON, authorization is strictly denied, zero tickets are minted, and the plant remains in its safe state.',
            },
            {
              q: 'How are unsafe scenarios evaluated?',
              a: 'Each scenario in the ground-truth registry defines an initial plant state, an injected fault or adversarial condition, and formal assertion rules. During benchmark execution, actual pipeline outcomes (policy verdict, ticket minting, mutation, verification) are compared against ground truth.',
            },
            {
              q: 'What does an evidence hash establish?',
              a: 'The SHA-256 hash covers the exact RFC 8785 canonical JSON serialization of the evidence bundle. A matching hash confirms that the recorded observations, decisions, and assertions have not been retroactively tampered with. It does not represent a hardware PKI signature.',
            },
            {
              q: 'Is the hosted 3D scene running inside native NVIDIA Isaac Sim?',
              a: 'No. The hosted web interface uses our browser-based Contract Simulator. Native Isaac Sim requires an NVIDIA RTX workstation with native Omniverse libraries. MotionFence provides OpenUSD stage export and standalone Python runners for compatible native workstations.',
            },
            {
              q: 'Can the benchmark be reproduced locally?',
              a: 'Yes. MotionFence is 100% reproducible offline without API keys or network access. Run `python scripts/run_safety_benchmark.py --suite expanded` in the repository to evaluate all 20 scenarios deterministically using seed 42.',
            },
            {
              q: 'Does the project directly control real industrial hardware?',
              a: 'No. MotionFence currently operates against a bounded synthetic plant environment and Isaac Sim digital twin. It is designed to prove software safety boundaries and verification protocols prior to real-world hardware integration.',
            },
            {
              q: 'What are the current limitations?',
              a: 'Current limitations include reliance on synthetic sensor models rather than noisy real-world analog instrumentation, lack of IEC 61508 SIL certification, and the need for certified physical E-stop interlocks in any future physical deployment.',
            },
          ].map((item, idx) => (
            <div className="faq-item" key={idx}>
              <button
                className="faq-question-btn"
                onClick={() => toggleFaq(idx)}
                aria-expanded={activeFaq === idx}
              >
                <span>{item.q}</span>
                <span style={{ fontSize: '1.2rem', color: '#38bdf8' }}>
                  {activeFaq === idx ? '−' : '+'}
                </span>
              </button>
              {activeFaq === idx && (
                <div className="faq-answer">
                  <p>{item.a}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="landing-footer" role="contentinfo">
        <div className="footer-inner">
          <div className="footer-brand-col">
            <div className="landing-nav-brand">
              <div className="brand-badge">
                <ShieldCheck size={16} />
                <span>MF-GATEWAY</span>
              </div>
              <span className="brand-name">MotionFence</span>
            </div>
            <p className="footer-desc">
              Deterministic runtime authorization layer for AI-generated physical actions.
              Bridging generative intelligence and industrial safety assurance.
            </p>
            <div style={{ fontSize: '0.78rem', color: '#64748b', fontFamily: 'monospace' }}>
              Current Revision: motionfence-00005-boq (Candidate Lab)
            </div>
          </div>

          <div className="footer-col">
            <h4>Live Applications</h4>
            <ul className="footer-links">
              <li><button onClick={() => onNavigate('safety-lab')}>Public Safety Lab (20 Tests)</button></li>
              <li><button onClick={() => onNavigate('demo')}>1-Click Interactive Demo</button></li>
              <li><button onClick={() => onNavigate('console')}>Judge Decision Replay Console</button></li>
              <li><a href="/api/safety-lab/benchmark/report" target="_blank" rel="noopener noreferrer">Benchmark Report JSON</a></li>
            </ul>
          </div>

          <div className="footer-col">
            <h4>Digital Twin & Isaac</h4>
            <ul className="footer-links">
              <li><a href="/api/isaac/status" target="_blank" rel="noopener noreferrer">Isaac Sim Status</a></li>
              <li><a href="/api/isaac/scene.usda" target="_blank" rel="noopener noreferrer">Download OpenUSD Scene</a></li>
              <li><a href="/api/isaac/runner.py" target="_blank" rel="noopener noreferrer">Download Isaac Runner Script</a></li>
              <li><a href="/health" target="_blank" rel="noopener noreferrer">Healthcheck Endpoint</a></li>
            </ul>
          </div>

          <div className="footer-col">
            <h4>Source & Project</h4>
            <ul className="footer-links">
              <li>
                <a href="https://github.com/subodhkant7/motionfence" target="_blank" rel="noopener noreferrer">
                  GitHub Repository <ExternalLink size={11} style={{ display: 'inline', marginLeft: '4px' }} />
                </a>
              </li>
              <li><a href="#how-it-works">Architecture Methodology</a></li>
              <li><a href="#limitations">Simulator Disclosures</a></li>
              <li><a href="#faq">Frequently Asked Questions</a></li>
            </ul>
          </div>
        </div>

        <div className="footer-bottom-row">
          <div>
            © 2026 MotionFence Engineering. Built with Nebius AI Studio & NVIDIA Omniverse. Apache 2.0 / MIT.
          </div>
          <div>
            Production Baseline: <code>motionfence-00003-kis</code> (100% Traffic Preserved)
          </div>
        </div>
      </footer>
    </div>
  )
}
