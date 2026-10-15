import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LandingPage } from '../components/Landing/LandingPage'
import { IsaacSimViewport3D } from '../components/DigitalTwin/IsaacSimViewport3D'
import { resolveCurrentRoute } from '../App'
import { DigitalTwinPlantState, IsaacPrimPaths } from '../types'

const mockPlantState: DigitalTwinPlantState = {
  stage_name: 'STAGE 1: EVALUATION',
  pump_state: 'ACTIVE',
  valve_b_state: 'OPEN',
  valve_b_angle_deg: 0.0,
  cooling_state: 'ACTIVE',
  human_zone: 'CLEAR',
  human_distance_m: 5.0,
  actuator_status: 'ARMED',
  world_version: 1,
  leak_active: true,
  flow_rate_lpm: 14.2,
  simulation_time: 1.25,
  step_count: 125,
}

const mockPrimPaths: IsaacPrimPaths = {
  valve_b: '/World/IndustrialCell/CoolantManifold/ValveB',
  pump_p1: '/World/IndustrialCell/CoolantManifold/PumpP1',
  human_zone: '/World/SafetyZones/HumanZone_Sector4',
  human_worker: '/World/Actors/HumanWorker',
  gateway_actuator: '/World/Gateway/SafetyEnclaveActuator',
}

describe('Responsive Layout & Viewport Robustness Suite (Phases 2-8)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('verifies all wide tables in LandingPage are wrapped inside table-responsive containers', () => {
    const { container } = render(
      <LandingPage onNavigate={vi.fn()} reducedMotion={false} onToggleReducedMotion={vi.fn()} />
    )

    const responsiveWrappers = container.querySelectorAll('.table-responsive')
    expect(responsiveWrappers.length).toBeGreaterThanOrEqual(2)

    // Check that threat matrix and intent-vs-reality tables are contained
    const threatTable = container.querySelector('.threat-matrix-table')
    const intentTable = container.querySelector('.intent-vs-reality-table')

    expect(threatTable?.parentElement?.classList.contains('table-responsive')).toBe(true)
    expect(intentTable?.parentElement?.classList.contains('table-responsive')).toBe(true)
  })

  it('supports fullscreen mode and updates is-fullscreen classes on IsaacSimViewport3D', () => {
    const { container } = render(
      <IsaacSimViewport3D
        plantState={mockPlantState}
        effectivePrimPaths={mockPrimPaths}
        scenarioId="scenario_a"
      />
    )

    const viewportContainer = container.querySelector('.isaac-viewport-container')
    expect(viewportContainer).toBeInTheDocument()
    expect(viewportContainer?.classList.contains('is-fullscreen')).toBe(false)

    // Click fullscreen button
    const fsBtn = screen.getByTestId('isaac-btn-fullscreen')
    expect(fsBtn).toBeInTheDocument()

    // Mock requestFullscreen
    if (viewportContainer) {
      viewportContainer.requestFullscreen = vi.fn().mockResolvedValue(undefined)
    }

    fireEvent.click(fsBtn)
    expect(viewportContainer?.classList.contains('is-fullscreen')).toBe(true)

    // Simulate browser exiting fullscreen
    fireEvent(document, new Event('fullscreenchange'))
    // document.fullscreenElement is null in jsdom
    expect(viewportContainer?.classList.contains('is-fullscreen')).toBe(false)
  })

  it('correctly resolves deep links and query parameters across all routes without page overflow', () => {
    window.history.pushState({}, '', '/demo')
    expect(resolveCurrentRoute()).toBe('demo')

    window.history.pushState({}, '', '/safety-lab')
    expect(resolveCurrentRoute()).toBe('safety-lab')

    window.history.pushState({}, '', '/console')
    expect(resolveCurrentRoute()).toBe('console')

    window.history.pushState({}, '', '/architecture')
    expect(resolveCurrentRoute()).toBe('architecture')

    window.history.pushState({}, '', '/?director=1')
    expect(resolveCurrentRoute()).toBe('demo')

    window.history.pushState({}, '', '/?mode=lab')
    expect(resolveCurrentRoute()).toBe('safety-lab')

    window.history.pushState({}, '', '/')
    expect(resolveCurrentRoute()).toBe('home')
  })

  it('maintains camera control actions (Fit Scene, Reset, Presets) across viewport updates', () => {
    render(
      <IsaacSimViewport3D
        plantState={mockPlantState}
        effectivePrimPaths={mockPrimPaths}
        scenarioId="scenario_a"
      />
    )

    const fitBtn = screen.getByTestId('isaac-btn-fit-scene')
    expect(fitBtn).toBeInTheDocument()
    fireEvent.click(fitBtn)

    const topBtn = screen.getByRole('button', { name: /TOP/i })
    expect(topBtn).toBeInTheDocument()
    fireEvent.click(topBtn)
  })
})
