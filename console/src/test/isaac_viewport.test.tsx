import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { IsaacSimViewport3D } from '../components/DigitalTwin/IsaacSimViewport3D'
import { DigitalTwin } from '../components/DigitalTwin/DigitalTwin'
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

describe('NVIDIA Isaac Sim 3D Viewport & Camera Controls (Phase 2 & Phase 4)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the 3D viewport canvas, stage identifier, and live telemetry HUD', () => {
    render(
      <IsaacSimViewport3D
        plantState={mockPlantState}
        effectivePrimPaths={mockPrimPaths}
        scenarioId="scenario_a"
      />
    )

    // Viewport region & canvas
    expect(screen.getByTestId('isaac-viewport-3d')).toBeInTheDocument()
    expect(screen.getByTestId('isaac-3d-canvas')).toBeInTheDocument()

    // Omniverse stage header badge
    expect(screen.getByText(/NVIDIA ISAAC SIM 3D/i)).toBeInTheDocument()
    expect(screen.getByText('/World/IndustrialCell')).toBeInTheDocument()

    // HUD Telemetry
    expect(screen.getByTestId('isaac-hud-panel')).toBeInTheDocument()
    expect(screen.getByText(/VALVE B JOINT:/i)).toBeInTheDocument()
    expect(screen.getByText(/0.0° \(OPEN\)/i)).toBeInTheDocument()
    expect(screen.getByText(/SECTOR 4 ZONE:/i)).toBeInTheDocument()
    expect(screen.getByText(/CLEAR \(5.0m\)/i)).toBeInTheDocument()
  })

  it('provides camera controls: Fit Scene, Restore View, and presets', () => {
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

    const restoreBtn = screen.getByTestId('isaac-btn-restore-view')
    expect(restoreBtn).toBeInTheDocument()
    fireEvent.click(restoreBtn)

    // Preset buttons
    const topPreset = screen.getByRole('button', { name: /TOP/i })
    expect(topPreset).toBeInTheDocument()
    fireEvent.click(topPreset)

    const isoPreset = screen.getByRole('button', { name: /ISO/i })
    expect(isoPreset).toBeInTheDocument()
    fireEvent.click(isoPreset)
  })

  it('supports wheel zoom events on the viewport container with scroll isolation', () => {
    render(
      <IsaacSimViewport3D
        plantState={mockPlantState}
        effectivePrimPaths={mockPrimPaths}
        scenarioId="scenario_a"
      />
    )

    const viewport = screen.getByTestId('isaac-viewport-3d')
    const wheelEvent = new WheelEvent('wheel', { deltaY: -100, bubbles: true, cancelable: true })
    const preventDefaultSpy = vi.spyOn(wheelEvent, 'preventDefault')

    viewport.dispatchEvent(wheelEvent)
    expect(preventDefaultSpy).toHaveBeenCalled()
  })

  it('renders simulation transport controls when provided', () => {
    const onTogglePlay = vi.fn()
    const onStepForward = vi.fn()
    const onStepBack = vi.fn()

    render(
      <IsaacSimViewport3D
        plantState={mockPlantState}
        effectivePrimPaths={mockPrimPaths}
        isPlaying={false}
        onTogglePlay={onTogglePlay}
        onStepForward={onStepForward}
        onStepBack={onStepBack}
      />
    )

    const playBtn = screen.getByTestId('isaac-btn-play-pause')
    expect(playBtn).toBeInTheDocument()
    fireEvent.click(playBtn)
    expect(onTogglePlay).toHaveBeenCalledTimes(1)

    const fwdBtn = screen.getByTestId('isaac-btn-step-forward')
    fireEvent.click(fwdBtn)
    expect(onStepForward).toHaveBeenCalledTimes(1)

    const backBtn = screen.getByTestId('isaac-btn-step-back')
    fireEvent.click(backBtn)
    expect(onStepBack).toHaveBeenCalledTimes(1)
  })

  it('allows exporting OpenUSD stage (.usda) and downloading Isaac runner', () => {
    // Mock URL.createObjectURL and URL.revokeObjectURL
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-usd')
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

    render(
      <IsaacSimViewport3D
        plantState={mockPlantState}
        effectivePrimPaths={mockPrimPaths}
        scenarioId="scenario_safe"
      />
    )

    const exportBtn = screen.getByTestId('isaac-btn-export-usd')
    fireEvent.click(exportBtn)

    expect(createObjectURLSpy).toHaveBeenCalled()
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:mock-usd')
  })

  it('toggles cleanly between 3D Isaac Sim Viewport and 2D P&ID Schematic in DigitalTwin', () => {
    render(
      <DigitalTwin
        plantState={mockPlantState}
        activeStageIndex={0}
        scenarioId="scenario_a"
      />
    )

    // Initially 3D is active
    expect(screen.getByTestId('isaac-viewport-3d')).toBeInTheDocument()

    // Switch to 2D
    const toggle2D = screen.getByTestId('toggle-view-2d')
    fireEvent.click(toggle2D)

    // Switch back to 3D
    const toggle3D = screen.getByTestId('toggle-view-3d')
    fireEvent.click(toggle3D)

    expect(screen.getByTestId('isaac-viewport-3d')).toBeInTheDocument()
  })

  it('manages Presentation Camera Director modes with automatic framing and manual resume', () => {
    render(
      <IsaacSimViewport3D
        plantState={mockPlantState}
        effectivePrimPaths={mockPrimPaths}
        scenarioId="scenario_a"
      />
    )

    // Initially in AUTO director mode
    expect(screen.getByText(/DIRECTOR: AUTO/i)).toBeInTheDocument()
    expect(screen.getByText(/CELL 3D OVERVIEW/i)).toBeInTheDocument()

    // Switching preset triggers MANUAL mode with RESUME AUTO button
    const topPreset = screen.getByRole('button', { name: /TOP/i })
    fireEvent.click(topPreset)

    expect(screen.getByText(/DIRECTOR: MANUAL/i)).toBeInTheDocument()
    const resumeBtn = screen.getByRole('button', { name: /RESUME AUTO/i })
    expect(resumeBtn).toBeInTheDocument()

    // Clicking resume restores AUTO director mode
    fireEvent.click(resumeBtn)
    expect(screen.getByText(/DIRECTOR: AUTO/i)).toBeInTheDocument()
  })

  it('dynamically adapts camera director focus during Sector 4 breach and actuator lock', () => {
    const hazardState: DigitalTwinPlantState = {
      ...mockPlantState,
      human_zone: 'OCCUPIED',
      human_distance_m: 2.2,
      actuator_status: 'LOCKED',
      valve_b_state: 'BLOCKED',
      valve_b_angle_deg: 42.0,
    }

    render(
      <IsaacSimViewport3D
        plantState={hazardState}
        effectivePrimPaths={mockPrimPaths}
        scenarioId="scenario_hazard"
      />
    )

    // Director tracks Sector 4 hazard and worker breach
    expect(screen.getByText(/SECTOR 4 HAZARD & WORKER TRACK/i)).toBeInTheDocument()
    // HUD indicates breach and locked actuator
    expect(screen.getByText(/OCCUPIED \(2.2m\)/i)).toBeInTheDocument()
    expect(screen.getByText(/^LOCKED$/i)).toBeInTheDocument()
  })
})
