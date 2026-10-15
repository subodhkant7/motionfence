import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { LandingPage } from '../components/Landing/LandingPage'
import { App, resolveCurrentRoute } from '../App'
import { api } from '../services/api'
import benchmarkFixture from '../data/benchmark_report.json'

// Mock api methods
vi.mock('../services/api', () => ({
  api: {
    checkBackendStatus: vi.fn(),
    getScenarios: vi.fn(),
    getScenarioData: vi.fn(),
    getFirewallReport: vi.fn(),
    getRepairs: vi.fn(),
    getTrajectories: vi.fn(),
    getAssuranceReport: vi.fn(),
    getLatestBenchmarkReport: vi.fn(),
    getHealth: vi.fn(),
  },
}))

describe('MotionFence Public Website & Product Explainer Suite', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.checkBackendStatus).mockResolvedValue({ isLive: false } as any)
    vi.mocked(api.getScenarios).mockResolvedValue([])
    vi.mocked(api.getLatestBenchmarkReport).mockResolvedValue(benchmarkFixture as any)
  })

  it('renders hero message, eyebrow, and core product value proposition', () => {
    const onNavigate = vi.fn()
    const onToggleReducedMotion = vi.fn()

    render(
      <LandingPage
        onNavigate={onNavigate}
        reducedMotion={false}
        onToggleReducedMotion={onToggleReducedMotion}
      />
    )

    // Eyebrow and Headline
    expect(screen.getByText(/AI PROPOSALS. DETERMINISTIC SAFETY./i)).toBeInTheDocument()
    expect(
      screen.getByRole('heading', {
        name: /AI can propose the action. It shouldn't decide whether it's safe./i,
      })
    ).toBeInTheDocument()

    // Subheading
    expect(
      screen.getByText(/MotionFence is an experimental safety-assurance layer for AI-proposed industrial actions/i)
    ).toBeInTheDocument()

    // CTAs
    expect(screen.getByRole('button', { name: /Explore the Safety Lab/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Run Interactive Demo/i })).toBeInTheDocument()
  })

  it('triggers navigation when clicking hero and nav CTAs', () => {
    const onNavigate = vi.fn()
    render(
      <LandingPage
        onNavigate={onNavigate}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
      />
    )

    // Hero Safety Lab CTA
    const heroSafetyLabBtn = screen.getByRole('button', { name: /Explore the Safety Lab/i })
    fireEvent.click(heroSafetyLabBtn)
    expect(onNavigate).toHaveBeenCalledWith('safety-lab')

    // Hero Demo CTA
    const heroDemoBtn = screen.getByRole('button', { name: /Run Interactive Demo/i })
    fireEvent.click(heroDemoBtn)
    expect(onNavigate).toHaveBeenCalledWith('demo')

    // Nav Console button
    const navConsoleBtn = screen.getByRole('button', { name: /^Console$/i })
    fireEvent.click(navConsoleBtn)
    expect(onNavigate).toHaveBeenCalledWith('console')
  })

  it('renders the 6 tested failure classes in the problem section', () => {
    render(
      <LandingPage
        onNavigate={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
      />
    )

    expect(screen.getByText(/Worker in Safety Zone/i)).toBeInTheDocument()
    expect(screen.getByText(/Time-of-Check to Time-of-Use Drift/i)).toBeInTheDocument()
    expect(screen.getByText(/Contradictory \/ Stale Telemetry/i)).toBeInTheDocument()
    expect(screen.getByText(/Provider Outages & Prompt Injection/i)).toBeInTheDocument()
    expect(screen.getByText(/Mechanical Actuator Failure/i)).toBeInTheDocument()
    expect(screen.getByText(/Replay Attacks & Double-Spending/i)).toBeInTheDocument()
  })

  it('renders 6-stage architecture pipeline with failure branches', () => {
    render(
      <LandingPage
        onNavigate={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
      />
    )

    expect(screen.getByText('STAGE 01')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Propose' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Evaluate' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Revalidate' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Execute' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Verify' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Record' })).toBeInTheDocument()

    expect(screen.getByText(/Branch: Hazard → DENY/i)).toBeInTheDocument()
    expect(screen.getByText(/Branch: Drift → Ticket Invalidated/i)).toBeInTheDocument()
  })

  it('displays real benchmark metrics with explicit numerators and denominators', async () => {
    render(
      <LandingPage
        onNavigate={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
      />
    )

    expect(screen.getByText('0/12 (0.0%)')).toBeInTheDocument()
    expect(screen.getByText('0/2 (0.0%)')).toBeInTheDocument()
    expect(screen.getByText('20/20 (100.0%)')).toBeInTheDocument()
    expect(screen.getByText('0/4 (0.0%)')).toBeInTheDocument()
    // 7/7 is present for both Fail-Closed Coverage and Verification Coverage
    expect(screen.getAllByText('7/7 (100.0%)')).toHaveLength(2)

    // Separated latency profiles
    expect(screen.getByText(/Policy Engine Latency/i)).toBeInTheDocument()
    expect(screen.getByText(/Simulation Twin Latency/i)).toBeInTheDocument()
    expect(screen.getByText(/Total Wall-Clock Latency/i)).toBeInTheDocument()
  })

  it('renders simulator runtime disclosures and non-certification disclaimers', () => {
    render(
      <LandingPage
        onNavigate={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
      />
    )

    expect(screen.getByText(/Contract Simulator \(Browser Digital Twin\)/i)).toBeInTheDocument()
    expect(screen.getByText(/NVIDIA Isaac Sim Stage & Runner Export/i)).toBeInTheDocument()
    expect(screen.getByText(/Experimental Prototype \(Not Certified\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Cryptographic Hash Scope/i)).toBeInTheDocument()
  })

  it('toggles FAQ accordions when clicked', () => {
    render(
      <LandingPage
        onNavigate={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
      />
    )

    const faqQuestion = screen.getByText(/Why isn't the language model trusted to authorize actions\?/i)
    expect(faqQuestion).toBeInTheDocument()

    // Initially collapsed
    expect(screen.queryByText(/Generative AI models are probabilistic token predictors/i)).not.toBeInTheDocument()

    // Click to expand
    fireEvent.click(faqQuestion)
    expect(screen.getByText(/Generative AI models are probabilistic token predictors/i)).toBeInTheDocument()

    // Click to collapse
    fireEvent.click(faqQuestion)
    expect(screen.queryByText(/Generative AI models are probabilistic token predictors/i)).not.toBeInTheDocument()
  })

  it('toggles mobile navigation drawer', () => {
    render(
      <LandingPage
        onNavigate={vi.fn()}
        reducedMotion={false}
        onToggleReducedMotion={vi.fn()}
      />
    )

    const menuToggle = screen.getByLabelText(/Toggle Navigation Menu/i)
    fireEvent.click(menuToggle)

    // Check mobile drawer rendered with navigation options
    expect(screen.getByRole('button', { name: /^Public Safety Lab$/i })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^Interactive Demo$/i }).length).toBeGreaterThanOrEqual(2)
  })
})

describe('App Route Resolution & Backward Compatibility', () => {
  it('resolves home route on root path /', () => {
    delete (window as any).location
    window.location = new URL('http://localhost:3000/') as any
    expect(resolveCurrentRoute()).toBe('home')
  })

  it('resolves demo route on /demo and on ?director=1 query param', () => {
    delete (window as any).location
    window.location = new URL('http://localhost:3000/demo') as any
    expect(resolveCurrentRoute()).toBe('demo')

    window.location = new URL('http://localhost:3000/?director=1') as any
    expect(resolveCurrentRoute()).toBe('demo')
  })

  it('resolves safety-lab route on /safety-lab and on ?lab=1 query param', () => {
    delete (window as any).location
    window.location = new URL('http://localhost:3000/safety-lab') as any
    expect(resolveCurrentRoute()).toBe('safety-lab')

    window.location = new URL('http://localhost:3000/?lab=1') as any
    expect(resolveCurrentRoute()).toBe('safety-lab')
  })

  it('resolves console route on /console and on ?console=1 query param', () => {
    delete (window as any).location
    window.location = new URL('http://localhost:3000/console') as any
    expect(resolveCurrentRoute()).toBe('console')

    window.location = new URL('http://localhost:3000/?console=1') as any
    expect(resolveCurrentRoute()).toBe('console')
  })

  it('renders LandingPage by default when mounted at root URL /', async () => {
    delete (window as any).location
    window.location = new URL('http://localhost:3000/') as any

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText(/AI PROPOSALS. DETERMINISTIC SAFETY./i)).toBeInTheDocument()
    })
  })
})
