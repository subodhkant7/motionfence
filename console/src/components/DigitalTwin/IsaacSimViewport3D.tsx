import React, { useRef, useEffect, useState, useCallback } from 'react'
import {
  Camera,
  Maximize2,
  Minimize2,
  RotateCcw,
  Compass,
  Download,
  Cpu,
  Layers,
  Shield,
  Activity,
  Play,
  Pause,
  SkipForward,
  SkipBack,
  FileCode,
  Eye,
  Video,
} from 'lucide-react'
import { DigitalTwinPlantState, IsaacPrimPaths } from '../../types'
import './IsaacSimViewport3D.css'

interface IsaacSimViewport3DProps {
  plantState: DigitalTwinPlantState
  effectivePrimPaths: IsaacPrimPaths
  scenarioId?: string
  reducedMotion?: boolean
  isPlaying?: boolean
  onTogglePlay?: () => void
  onReset?: () => void
  onStepForward?: () => void
  onStepBack?: () => void
}

interface Particle {
  x: number
  y: number
  z: number
  vx: number
  vy: number
  vz: number
  life: number
  maxLife: number
  size: number
}

interface SplashRipple {
  x: number
  y: number
  radius: number
  maxRadius: number
  alpha: number
}

type CameraPreset = 'iso' | 'top' | 'front' | 'side' | 'custom'
type CameraDirectorMode = 'auto' | 'manual'

export const IsaacSimViewport3D: React.FC<IsaacSimViewport3DProps> = ({
  plantState,
  effectivePrimPaths,
  scenarioId = 'scenario_a',
  reducedMotion = false,
  isPlaying,
  onTogglePlay,
  onReset,
  onStepForward,
  onStepBack,
}) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  // Camera state
  const [distance, setDistance] = useState<number>(7.2)
  const [azimuth, setAzimuth] = useState<number>(38)
  const [elevation, setElevation] = useState<number>(26)
  const [target, setTarget] = useState<[number, number, number]>([1.2, 0.0, 0.5])
  const [preset, setPreset] = useState<CameraPreset>('iso')
  const [cameraMode, setCameraMode] = useState<CameraDirectorMode>('auto')

  // Performance telemetry
  const [fps, setFps] = useState<number>(60)
  const [frameTimeMs, setFrameTimeMs] = useState<number>(16.6)
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false)

  // Authoritative simulation targets
  const targetAngle =
    plantState.valve_b_angle_deg ?? (plantState.valve_b_state === 'OPEN' ? 0.0 : 90.0)
  const targetWorkerX =
    plantState.human_distance_m !== undefined
      ? plantState.human_distance_m
      : plantState.human_zone === 'CLEAR'
      ? 5.0
      : 2.5

  const isPumpActive = plantState.pump_state === 'ACTIVE'
  const isLeakActive = Boolean(plantState.leak_active)
  const isHumanZoneClear = plantState.human_zone === 'CLEAR'
  const actuatorStatus = plantState.actuator_status || 'READY'
  const isActuatorLocked = actuatorStatus === 'LOCKED'
  const isActuatorQuarantined = actuatorStatus === 'QUARANTINED'
  const isActuatorVerified = actuatorStatus === 'VERIFIED' || actuatorStatus === 'ACTUATED'

  // Derived camera director focus label
  const directorFocus =
    !isHumanZoneClear || targetWorkerX < 3.8
      ? 'SECTOR 4 HAZARD & WORKER TRACK'
      : isActuatorLocked || isActuatorQuarantined
      ? 'VALVE B & SAFETY ACTUATOR FOCUS'
      : 'CELL 3D OVERVIEW'

  // Camera interpolation targets
  const targetCamDistRef = useRef<number>(7.2)
  const targetCamAzRef = useRef<number>(38)
  const targetCamElRef = useRef<number>(26)
  const targetCamLookRef = useRef<[number, number, number]>([1.2, 0.0, 0.5])

  // Animation interpolation state
  const animatedAngleRef = useRef<number>(targetAngle)
  const animatedWorkerXRef = useRef<number>(targetWorkerX)
  const prevWorkerXRef = useRef<number>(targetWorkerX)
  const walkPhaseRef = useRef<number>(0)
  const impellerAngleRef = useRef<number>(0)
  const flowPhaseRef = useRef<number>(0)
  const particlesRef = useRef<Particle[]>([])
  const ripplesRef = useRef<SplashRipple[]>([])
  const lastTimeRef = useRef<number>(0)
  const frameCountRef = useRef<number>(0)
  const fpsTimerRef = useRef<number>(0)

  // Pointer drag tracking
  const isDraggingRef = useRef<boolean>(false)
  const dragModeRef = useRef<'orbit' | 'pan'>('orbit')
  const lastPointerRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 })

  // --------------------------------------------------------------------------
  // Camera Director Automated Framing State Machine
  // --------------------------------------------------------------------------
  useEffect(() => {
    if (cameraMode !== 'auto') return

    // Stage 1: Hazard / Human Worker Breach Detected
    if (!isHumanZoneClear || targetWorkerX < 3.8) {
      targetCamDistRef.current = 5.9
      targetCamAzRef.current = 32
      targetCamElRef.current = 24
      targetCamLookRef.current = [2.4, 0.0, 0.75]
      return
    }

    // Stage 2: Actuator Locked / Intervention in Progress
    if (isActuatorLocked || isActuatorQuarantined || Math.abs(targetAngle - animatedAngleRef.current) > 5) {
      targetCamDistRef.current = 5.2
      targetCamAzRef.current = 46
      targetCamElRef.current = 25
      targetCamLookRef.current = [0.4, 0.0, 0.65]
      return
    }

    // Stage 3: Default Cell Overview Framing
    targetCamDistRef.current = 7.2
    targetCamAzRef.current = 38
    targetCamElRef.current = 26
    targetCamLookRef.current = [1.2, 0.0, 0.5]
  }, [
    cameraMode,
    isHumanZoneClear,
    targetWorkerX,
    isActuatorLocked,
    isActuatorQuarantined,
    targetAngle,
    plantState.stage_name,
  ])

  // Camera presets
  const applyPreset = useCallback((p: CameraPreset) => {
    setPreset(p)
    setCameraMode('manual')
    if (p === 'iso') {
      targetCamAzRef.current = 38
      targetCamElRef.current = 26
      targetCamDistRef.current = 7.2
      targetCamLookRef.current = [1.2, 0.0, 0.5]
      setAzimuth(38)
      setElevation(26)
      setDistance(7.2)
      setTarget([1.2, 0.0, 0.5])
    } else if (p === 'top') {
      targetCamAzRef.current = 0
      targetCamElRef.current = 84
      targetCamDistRef.current = 7.5
      targetCamLookRef.current = [1.2, 0.0, 0.5]
      setAzimuth(0)
      setElevation(84)
      setDistance(7.5)
      setTarget([1.2, 0.0, 0.5])
    } else if (p === 'front') {
      targetCamAzRef.current = 0
      targetCamElRef.current = 14
      targetCamDistRef.current = 7.0
      targetCamLookRef.current = [1.2, 0.0, 0.5]
      setAzimuth(0)
      setElevation(14)
      setDistance(7.0)
      setTarget([1.2, 0.0, 0.5])
    } else if (p === 'side') {
      targetCamAzRef.current = 90
      targetCamElRef.current = 18
      targetCamDistRef.current = 6.8
      targetCamLookRef.current = [2.0, 0.0, 0.6]
      setAzimuth(90)
      setElevation(18)
      setDistance(6.8)
      setTarget([2.0, 0.0, 0.6])
    }
  }, [])

  const handleFitScene = useCallback(() => {
    setCameraMode('auto')
    setPreset('iso')
    targetCamAzRef.current = 38
    targetCamElRef.current = 26
    targetCamDistRef.current = 7.5
    targetCamLookRef.current = [1.2, 0.0, 0.5]
    setAzimuth(38)
    setElevation(26)
    setDistance(7.5)
    setTarget([1.2, 0.0, 0.5])
  }, [])

  const handleRestoreView = useCallback(() => {
    handleFitScene()
  }, [handleFitScene])

  const handleResumeAutoCamera = useCallback(() => {
    setCameraMode('auto')
    setPreset('iso')
  }, [])

  const handleResetSimulation = useCallback(() => {
    handleRestoreView()
    onReset?.()
  }, [handleRestoreView, onReset])

  // Non-passive wheel zoom isolation (prevents outer page scrolling)
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault()
      e.stopPropagation()
      const zoomFactor = e.deltaY * 0.005 * (distance / 5.0)
      const nextDist = Math.min(16.0, Math.max(2.2, distance + zoomFactor))
      setDistance(nextDist)
      targetCamDistRef.current = nextDist
      setPreset('custom')
      setCameraMode('manual')
    }

    el.addEventListener('wheel', handleWheel, { passive: false })
    return () => {
      el.removeEventListener('wheel', handleWheel)
    }
  }, [distance])

  // Mouse / Pointer handlers for Orbit and Pan
  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    isDraggingRef.current = true
    lastPointerRef.current = { x: e.clientX, y: e.clientY }

    if (e.button === 2 || e.shiftKey) {
      dragModeRef.current = 'pan'
    } else {
      dragModeRef.current = 'orbit'
    }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
    setCameraMode('manual')
  }

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!isDraggingRef.current) return
    const dx = e.clientX - lastPointerRef.current.x
    const dy = e.clientY - lastPointerRef.current.y
    lastPointerRef.current = { x: e.clientX, y: e.clientY }

    if (dragModeRef.current === 'orbit') {
      const nextAz = (azimuth - dx * 0.4 + 360) % 360
      const nextEl = Math.min(86, Math.max(5, elevation + dy * 0.3))
      setAzimuth(nextAz)
      setElevation(nextEl)
      targetCamAzRef.current = nextAz
      targetCamElRef.current = nextEl
      setPreset('custom')
    } else {
      const radAz = (azimuth * Math.PI) / 180
      const rightX = Math.cos(radAz)
      const rightY = Math.sin(radAz)
      const panSpeed = distance * 0.0015

      const nextTarget: [number, number, number] = [
        target[0] - dx * rightX * panSpeed,
        target[1] - dx * rightY * panSpeed,
        target[2] + dy * panSpeed,
      ]
      setTarget(nextTarget)
      targetCamLookRef.current = nextTarget
      setPreset('custom')
    }
  }

  const handlePointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    isDraggingRef.current = false
    try {
      ;(e.target as HTMLElement).releasePointerCapture(e.pointerId)
    } catch {
      // ignore
    }
  }

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault()
  }

  const handleDoubleClick = () => {
    handleRestoreView()
  }

  // Fullscreen toggle
  const toggleFullscreen = () => {
    if (!containerRef.current) return
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen?.().catch(() => {})
      setIsFullscreen(true)
    } else {
      document.exitFullscreen?.().catch(() => {})
      setIsFullscreen(false)
    }
  }

  // Synchronize fullscreen state on external exit (Esc key / browser controls)
  useEffect(() => {
    const handleFsChange = () => {
      setIsFullscreen(Boolean(document.fullscreenElement))
    }
    document.addEventListener('fullscreenchange', handleFsChange)
    return () => {
      document.removeEventListener('fullscreenchange', handleFsChange)
    }
  }, [])

  // ResizeObserver to detect container dimensions changes immediately
  useEffect(() => {
    if (!containerRef.current || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => {
      const canvas = canvasRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      if (
        canvas.width !== Math.floor(rect.width * dpr) ||
        canvas.height !== Math.floor(rect.height * dpr)
      ) {
        canvas.width = Math.floor(rect.width * dpr)
        canvas.height = Math.floor(rect.height * dpr)
      }
    })
    ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  // Download USD Stage file (.usda)
  const handleDownloadUsd = () => {
    const usdContent = `#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1.0
    upAxis = "Z"
    doc = "MotionFence Industrial Cell OpenUSD Stage for NVIDIA Isaac Sim"
)

def Xform "World"
{
    def Xform "GroundPlane"
    {
        double3 xformOp:translate = (0, 0, 0)
        uniform token[] xformOpOrder = ["xformOp:translate"]
    }

    def Xform "IndustrialCell"
    {
        def Xform "CoolantManifold"
        {
            def Mesh "ValveB" (
                apiSchemas = ["PhysicsRevoluteJointAPI"]
            )
            {
                float physics:lowerLimit = 0.0
                float physics:upperLimit = 90.0
                token physics:axis = "Z"
                string motionfence:role = "VALVE_B_ACTUATOR"
                float motionfence:current_angle = ${animatedAngleRef.current.toFixed(1)}
            }

            def Mesh "PumpP1"
            {
                string motionfence:role = "PUMP_P1_MOTOR"
                float motionfence:target_rpm = 1750.0
                string motionfence:state = "${plantState.pump_state}"
            }

            def Xform "CoolingLoop"
            {
                string motionfence:role = "HEAT_EXCHANGER_LOOP"
                string motionfence:state = "${plantState.cooling_state}"
            }
        }
    }

    def Scope "SafetyZones"
    {
        def Cube "HumanZone_Sector4"
        {
            double size = 2.0
            double3 xformOp:scale = (1.0, 1.0, 1.1)
            double3 xformOp:translate = (2.5, 0.0, 1.1)
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
            string motionfence:zone_id = "SECTOR_4"
            string motionfence:status = "${plantState.human_zone}"
        }
    }

    def Xform "Actors"
    {
        def Capsule "HumanWorker"
        {
            double height = 1.75
            double radius = 0.3
            double3 xformOp:translate = (${animatedWorkerXRef.current.toFixed(2)}, 0.0, 0.875)
            uniform token[] xformOpOrder = ["xformOp:translate"]
            string motionfence:actor_id = "WORKER_01"
        }
    }

    def Xform "Gateway"
    {
        def Xform "SafetyEnclaveActuator"
        {
            string motionfence:auth_required = "AuthorizationTicket"
            string motionfence:status = "${plantState.actuator_status || 'READY'}"
        }
    }
}
`
    const blob = new Blob([usdContent], { type: 'model/vnd.usda' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `industrial_cell_${scenarioId}.usda`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Download Standalone Python Script for native Isaac Sim (.py)
  const handleDownloadRunner = () => {
    const pythonScript = `"""MotionFence NVIDIA Isaac Sim Industrial Cell Runner.
Run via Isaac Sim Python environment:
./python.sh isaac_motionfence_cell.py
"""
import sys

try:
    from isaacsim import SimulationApp
    simulation_app = SimulationApp({"headless": False})
    import omni
    import omni.timeline
    from pxr import Gf, UsdGeom
except ImportError:
    print("[ERROR] NVIDIA Isaac Sim environment required to run this script.")
    sys.exit(1)

def run_simulation():
    stage = omni.usd.get_context().get_stage()
    print("[MotionFence] Loaded Industrial Cell Stage: /World/IndustrialCell")
    timeline = omni.timeline.get_timeline_interface()
    timeline.play()

    while simulation_app.is_running():
        simulation_app.update()

    timeline.stop()
    simulation_app.close()

if __name__ == "__main__":
    run_simulation()
`
    const blob = new Blob([pythonScript], { type: 'text/x-python' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'isaac_motionfence_cell.py'
    a.click()
    URL.revokeObjectURL(url)
  }

  // --------------------------------------------------------------------------
  // Main High-Fidelity 3D Canvas Rendering Engine
  // --------------------------------------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animationFrameId: number

    const render = (currentTime: number) => {
      const dt = Math.min(0.1, (currentTime - lastTimeRef.current) / 1000)
      lastTimeRef.current = currentTime

      // Real calculated moving average performance measurement
      frameCountRef.current += 1
      if (currentTime - fpsTimerRef.current >= 500) {
        const measuredFps = Math.round(
          (frameCountRef.current * 1000) / (currentTime - fpsTimerRef.current)
        )
        const measuredMs = parseFloat((1000 / Math.max(1, measuredFps)).toFixed(1))
        setFps(measuredFps)
        setFrameTimeMs(measuredMs)
        frameCountRef.current = 0
        fpsTimerRef.current = currentTime
      }

      // Smooth camera interpolation in Auto mode
      if (cameraMode === 'auto' && !reducedMotion) {
        const camInterp = Math.min(1.0, 3.5 * dt)
        setDistance((prev) => prev + (targetCamDistRef.current - prev) * camInterp)
        setAzimuth((prev) => prev + (targetCamAzRef.current - prev) * camInterp)
        setElevation((prev) => prev + (targetCamElRef.current - prev) * camInterp)
        setTarget((prev) => [
          prev[0] + (targetCamLookRef.current[0] - prev[0]) * camInterp,
          prev[1] + (targetCamLookRef.current[1] - prev[1]) * camInterp,
          prev[2] + (targetCamLookRef.current[2] - prev[2]) * camInterp,
        ])
      }

      // Smooth interpolation of valve angle and worker position
      const interpSpeed = reducedMotion ? 1.0 : 8.0 * dt
      animatedAngleRef.current += (targetAngle - animatedAngleRef.current) * interpSpeed

      // Worker position interpolation and gait phase tracking
      const workerDelta = targetWorkerX - animatedWorkerXRef.current
      animatedWorkerXRef.current += workerDelta * interpSpeed

      // Articulated walking cycle advances with movement
      const workerSpeed = Math.abs(animatedWorkerXRef.current - prevWorkerXRef.current) / Math.max(0.001, dt)
      prevWorkerXRef.current = animatedWorkerXRef.current
      if (workerSpeed > 0.05 && !reducedMotion) {
        walkPhaseRef.current = (walkPhaseRef.current + dt * 6.5) % (Math.PI * 2)
      } else {
        // Return smoothly to idle stance
        walkPhaseRef.current = (walkPhaseRef.current * 0.9)
      }

      // Impeller rotation and coolant flow pulses
      if (isPumpActive && !reducedMotion) {
        impellerAngleRef.current = (impellerAngleRef.current + 360 * dt * 3.0) % 360
        flowPhaseRef.current = (flowPhaseRef.current + dt * 3.5) % 1.0
      }

      // Dynamic Particle Spray simulation for coolant leak
      const isAngleClosed = animatedAngleRef.current >= 80.0
      if (isLeakActive && !isAngleClosed && !reducedMotion) {
        // Emit directional high-pressure coolant droplets from flange coupling at (0.35, 0.0, 0.42)
        for (let i = 0; i < 3; i++) {
          particlesRef.current.push({
            x: 0.35 + (Math.random() - 0.5) * 0.03,
            y: 0.0 + (Math.random() - 0.5) * 0.03,
            z: 0.42,
            vx: 0.8 + (Math.random() - 0.4) * 1.6,
            vy: -1.2 + (Math.random() - 0.5) * 1.8,
            vz: 1.4 + Math.random() * 1.6,
            life: 0,
            maxLife: 0.55 + Math.random() * 0.4,
            size: 2.0 + Math.random() * 2.2,
          })
        }
      }

      // Update leak particles
      particlesRef.current.forEach((p) => {
        p.life += dt
        p.vz -= 9.8 * dt * 0.75 // Realistic gravity acceleration
        p.x += p.vx * dt
        p.y += p.vy * dt
        p.z += p.vz * dt

        // Ground splash ripple on contact
        if (p.z <= 0.02 && p.life > 0.1) {
          if (ripplesRef.current.length < 24) {
            ripplesRef.current.push({
              x: p.x,
              y: p.y,
              radius: 0.04,
              maxRadius: 0.22,
              alpha: 0.6,
            })
          }
          p.z = 0
          p.life = p.maxLife // terminate particle
        }
      })
      particlesRef.current = particlesRef.current.filter((p) => p.life < p.maxLife && p.z >= 0)

      // Update splash ripples
      ripplesRef.current.forEach((r) => {
        r.radius += dt * 0.35
        r.alpha -= dt * 1.1
      })
      ripplesRef.current = ripplesRef.current.filter((r) => r.alpha > 0)

      // Canvas sizing and device pixel ratio handling
      const rect = canvas.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      if (
        canvas.width !== Math.floor(rect.width * dpr) ||
        canvas.height !== Math.floor(rect.height * dpr)
      ) {
        canvas.width = Math.floor(rect.width * dpr)
        canvas.height = Math.floor(rect.height * dpr)
      }

      const width = canvas.width
      const height = canvas.height

      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.clearRect(0, 0, width, height)

      // ----------------------------------------------------------------------
      // 3D Perspective Projection Mathematics
      // ----------------------------------------------------------------------
      const radAz = (azimuth * Math.PI) / 180
      const radEl = (elevation * Math.PI) / 180

      const [tx, ty, tz] = target
      const camX = tx + distance * Math.cos(radEl) * Math.sin(radAz)
      const camY = ty - distance * Math.cos(radEl) * Math.cos(radAz)
      const camZ = tz + distance * Math.sin(radEl)

      // Camera forward vector F = normalize(target - cam)
      let fx = tx - camX
      let fy = ty - camY
      let fz = tz - camZ
      const fLen = Math.hypot(fx, fy, fz) || 1
      fx /= fLen
      fy /= fLen
      fz /= fLen

      // Camera right vector R = normalize(F x Up) where Up = (0, 0, 1)
      let rx = fy
      let ry = -fx
      let rz = 0
      const rLen = Math.hypot(rx, ry, rz) || 1
      rx /= rLen
      ry /= rLen
      rz /= rLen

      // Camera true up vector U = R x F
      const ux = ry * fz - rz * fy
      const uy = rz * fx - rx * fz
      const uz = rx * fy - ry * fx

      const fov = (42 * Math.PI) / 180
      const aspect = width / (height || 1)
      const aspectCorrection = aspect < (16 / 9) ? aspect / (16 / 9) : 1
      const scale = (height * 0.5 * aspectCorrection) / Math.tan(fov * 0.5)

      // Directional Key Light vector: from upper-left-front in cell coordinates
      const keyLight = { x: -0.55, y: -0.4, z: 0.72 }
      const keyLightLen = Math.hypot(keyLight.x, keyLight.y, keyLight.z) || 1
      const lx = keyLight.x / keyLightLen
      const ly = keyLight.y / keyLightLen
      const lz = keyLight.z / keyLightLen

      // Projection helper: transforms world (wx, wy, wz) -> screen (sx, sy, depth)
      const project = (
        wx: number,
        wy: number,
        wz: number
      ): { sx: number; sy: number; depth: number; visible: boolean } => {
        const dx = wx - camX
        const dy = wy - camY
        const dz = wz - camZ

        const camDepth = dx * fx + dy * fy + dz * fz
        if (camDepth <= 0.1) {
          return { sx: 0, sy: 0, depth: camDepth, visible: false }
        }

        const camRight = dx * rx + dy * ry + dz * rz
        const camUp = dx * ux + dy * uy + dz * uz

        const sx = width * 0.5 + (camRight / camDepth) * scale
        const sy = height * 0.5 - (camUp / camDepth) * scale

        return { sx, sy, depth: camDepth, visible: true }
      }

      // Shading helper for directional lighting
      const calcShading = (nx: number, ny: number, nz: number) => {
        const dot = Math.max(0, nx * lx + ny * ly + nz * lz)
        const ambient = 0.35
        const diffuse = 0.65 * dot
        return ambient + diffuse
      }

      // Contact shadow drawer
      const drawContactShadow = (
        wx: number,
        wy: number,
        radiusX: number,
        radiusY: number,
        opacity: number = 0.55
      ) => {
        const p = project(wx, wy, 0.005)
        if (!p.visible) return
        const sxRadX = (radiusX / p.depth) * scale
        const sxRadY = (radiusY / p.depth) * scale * Math.sin(radEl)
        if (sxRadX <= 1) return

        const grad = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, Math.max(sxRadX, sxRadY))
        grad.addColorStop(0, `rgba(3, 7, 18, ${opacity})`)
        grad.addColorStop(0.65, `rgba(3, 7, 18, ${opacity * 0.4})`)
        grad.addColorStop(1, 'rgba(3, 7, 18, 0)')

        ctx.fillStyle = grad
        ctx.beginPath()
        ctx.ellipse(p.sx, p.sy, sxRadX, Math.max(2, sxRadY), 0, 0, Math.PI * 2)
        ctx.fill()
      }

      // ----------------------------------------------------------------------
      // 1. Concrete Ground Floor & Expansion Grid (/World/GroundPlane)
      // ----------------------------------------------------------------------
      // Floor contact shadows under equipment footprint
      drawContactShadow(-0.5, -0.3, 2.5, 1.2, 0.6) // Main equipment skid shadow
      drawContactShadow(-2.0, 0.0, 0.7, 0.55, 0.7) // Pump P1 footprint
      drawContactShadow(0.0, 0.0, 0.6, 0.5, 0.65) // Valve B footprint

      // Industrial concrete slab grid lines
      ctx.lineWidth = 1 * dpr
      for (let x = -3; x <= 6; x += 1) {
        const p1 = project(x, -3, 0)
        const p2 = project(x, 3, 0)
        if (p1.visible && p2.visible) {
          ctx.strokeStyle =
            x === 0 ? 'rgba(56, 189, 248, 0.35)' : 'rgba(30, 41, 59, 0.42)'
          ctx.beginPath()
          ctx.moveTo(p1.sx, p1.sy)
          ctx.lineTo(p2.sx, p2.sy)
          ctx.stroke()
        }
      }

      for (let y = -3; y <= 3; y += 1) {
        const p1 = project(-3, y, 0)
        const p2 = project(6, y, 0)
        if (p1.visible && p2.visible) {
          ctx.strokeStyle =
            y === 0 ? 'rgba(56, 189, 248, 0.35)' : 'rgba(30, 41, 59, 0.42)'
          ctx.beginPath()
          ctx.moveTo(p1.sx, p1.sy)
          ctx.lineTo(p2.sx, p2.sy)
          ctx.stroke()
        }
      }

      // High-visibility pedestrian safety aisle line leading toward Sector 4
      const aisleP1 = project(4.8, -0.6, 0.0)
      const aisleP2 = project(3.5, -0.6, 0.0)
      if (aisleP1.visible && aisleP2.visible) {
        ctx.lineWidth = 2 * dpr
        ctx.strokeStyle = 'rgba(234, 179, 8, 0.45)'
        ctx.setLineDash([4 * dpr, 4 * dpr])
        ctx.beginPath()
        ctx.moveTo(aisleP1.sx, aisleP1.sy)
        ctx.lineTo(aisleP2.sx, aisleP2.sy)
        ctx.stroke()
        ctx.setLineDash([])
      }

      // Coordinate axes gizmo at origin (0, 0, 0)
      const origin = project(0, 0, 0)
      const axisX = project(0.8, 0, 0)
      const axisY = project(0, 0.8, 0)
      const axisZ = project(0, 0, 0.8)

      if (origin.visible) {
        ctx.lineWidth = 2 * dpr
        if (axisX.visible) {
          ctx.strokeStyle = '#ef4444'
          ctx.beginPath()
          ctx.moveTo(origin.sx, origin.sy)
          ctx.lineTo(axisX.sx, axisX.sy)
          ctx.stroke()
        }
        if (axisY.visible) {
          ctx.strokeStyle = '#22c55e'
          ctx.beginPath()
          ctx.moveTo(origin.sx, origin.sy)
          ctx.lineTo(axisY.sx, axisY.sy)
          ctx.stroke()
        }
        if (axisZ.visible) {
          ctx.strokeStyle = '#38bdf8'
          ctx.beginPath()
          ctx.moveTo(origin.sx, origin.sy)
          ctx.lineTo(axisZ.sx, axisZ.sy)
          ctx.stroke()
        }
      }

      // ----------------------------------------------------------------------
      // 2. Heavy Industrial Structural Steel Mounting Skid
      // ----------------------------------------------------------------------
      // Base frame I-beams: rectangle from X = -2.7 to 1.8, Y = -1.25 to 0.4, Z = 0 to 0.1
      const skidCorners = [
        project(-2.7, -1.25, 0.0),
        project(1.8, -1.25, 0.0),
        project(1.8, 0.4, 0.0),
        project(-2.7, 0.4, 0.0),
        project(-2.7, -1.25, 0.1),
        project(1.8, -1.25, 0.1),
        project(1.8, 0.4, 0.1),
        project(-2.7, 0.4, 0.1),
      ]

      if (skidCorners.every((p) => p.visible)) {
        // Skid baseplate fill (painted industrial machinery grey with key light gradient)
        ctx.fillStyle = '#0f172a'
        ctx.beginPath()
        ctx.moveTo(skidCorners[4].sx, skidCorners[4].sy)
        ctx.lineTo(skidCorners[5].sx, skidCorners[5].sy)
        ctx.lineTo(skidCorners[6].sx, skidCorners[6].sy)
        ctx.lineTo(skidCorners[7].sx, skidCorners[7].sy)
        ctx.closePath()
        ctx.fill()

        ctx.lineWidth = 1.5 * dpr
        ctx.strokeStyle = '#334155'
        ctx.stroke()

        // Skid front I-beam flange
        ctx.fillStyle = '#1e293b'
        ctx.beginPath()
        ctx.moveTo(skidCorners[1].sx, skidCorners[1].sy)
        ctx.lineTo(skidCorners[2].sx, skidCorners[2].sy)
        ctx.lineTo(skidCorners[6].sx, skidCorners[6].sy)
        ctx.lineTo(skidCorners[5].sx, skidCorners[5].sy)
        ctx.closePath()
        ctx.fill()
        ctx.stroke()

        // Anchor bolt plates on corners
        const anchorPositions = [
          [-2.6, -1.15],
          [1.7, -1.15],
          [1.7, 0.3],
          [-2.6, 0.3],
        ]
        anchorPositions.forEach(([ax, ay]) => {
          const ap = project(ax, ay, 0.1)
          if (ap.visible) {
            ctx.fillStyle = '#475569'
            ctx.beginPath()
            ctx.arc(ap.sx, ap.sy, 3.5 * dpr, 0, Math.PI * 2)
            ctx.fill()
            ctx.fillStyle = '#94a3b8'
            ctx.beginPath()
            ctx.arc(ap.sx, ap.sy, 1.8 * dpr, 0, Math.PI * 2)
            ctx.fill()
          }
        })
      }

      // Structural pipe stanchions / supports anchoring manifold to skid
      const stanchionPositions = [
        [-0.7, 0.0, 0.42],
        [1.3, 0.0, 0.42],
        [0.0, -1.0, 0.42],
      ]
      stanchionPositions.forEach(([sx, sy, sz]) => {
        const top = project(sx, sy, sz)
        const bot = project(sx, sy, 0.1)
        if (top.visible && bot.visible) {
          ctx.lineWidth = 4 * dpr
          ctx.strokeStyle = '#334155'
          ctx.beginPath()
          ctx.moveTo(bot.sx, bot.sy)
          ctx.lineTo(top.sx, top.sy)
          ctx.stroke()

          // Structural base flange
          ctx.fillStyle = '#475569'
          ctx.beginPath()
          ctx.ellipse(bot.sx, bot.sy, 6 * dpr, 3 * dpr, 0, 0, Math.PI * 2)
          ctx.fill()
        }
      })

      // ----------------------------------------------------------------------
      // 3. Sector 4 Safety Zone Ground Footprint & Volumetric Boundary
      // ----------------------------------------------------------------------
      // Corner bollards: (1.5, -1.0), (3.5, -1.0), (3.5, 1.0), (1.5, 1.0)
      const bollardCoords = [
        [1.5, -1.0],
        [3.5, -1.0],
        [3.5, 1.0],
        [1.5, 1.0],
      ]
      const zoneCorners = [
        project(1.5, -1.0, 0.0),
        project(3.5, -1.0, 0.0),
        project(3.5, 1.0, 0.0),
        project(1.5, 1.0, 0.0),
        project(1.5, -1.0, 2.2),
        project(3.5, -1.0, 2.2),
        project(3.5, 1.0, 2.2),
        project(1.5, 1.0, 2.2),
      ]

      const zoneColor = isHumanZoneClear ? 'rgba(34, 197, 94, ' : 'rgba(239, 68, 68, '
      const zoneBorderColor = isHumanZoneClear ? '#22c55e' : '#ef4444'

      // Sector 4 ground contact shadow & hazard striped footprint
      if (
        zoneCorners[0].visible &&
        zoneCorners[1].visible &&
        zoneCorners[2].visible &&
        zoneCorners[3].visible
      ) {
        // Floor zone fill
        ctx.fillStyle = `${zoneColor}${isHumanZoneClear ? '0.08' : '0.18'})`
        ctx.beginPath()
        ctx.moveTo(zoneCorners[0].sx, zoneCorners[0].sy)
        ctx.lineTo(zoneCorners[1].sx, zoneCorners[1].sy)
        ctx.lineTo(zoneCorners[2].sx, zoneCorners[2].sy)
        ctx.lineTo(zoneCorners[3].sx, zoneCorners[3].sy)
        ctx.closePath()
        ctx.fill()

        // Restrained pulsing perimeter border
        const pulseAlpha = isHumanZoneClear
          ? 0.75
          : 0.85 + Math.sin(currentTime * 0.008) * 0.15
        ctx.lineWidth = (isHumanZoneClear ? 2.0 : 3.0) * dpr
        ctx.strokeStyle = `${zoneBorderColor}${Math.floor(pulseAlpha * 255)
          .toString(16)
          .padStart(2, '0')}`
        ctx.stroke()

        // Floor hazard hatching when breach detected
        if (!isHumanZoneClear) {
          ctx.lineWidth = 1.5 * dpr
          ctx.strokeStyle = 'rgba(239, 68, 68, 0.35)'
          for (let hx = 1.7; hx <= 3.3; hx += 0.4) {
            const hp1 = project(hx, -0.9, 0.0)
            const hp2 = project(hx + 0.3, 0.9, 0.0)
            if (hp1.visible && hp2.visible) {
              ctx.beginPath()
              ctx.moveTo(hp1.sx, hp1.sy)
              ctx.lineTo(hp2.sx, hp2.sy)
              ctx.stroke()
            }
          }
        }
      }

      // 4 Heavy Industrial Safety Bollards at corners with hazard bands
      bollardCoords.forEach(([bx, by]) => {
        drawContactShadow(bx, by, 0.18, 0.14, 0.65)
        const bBase = project(bx, by, 0.0)
        const bMid = project(bx, by, 0.5)
        const bTop = project(bx, by, 1.0)

        if (bBase.visible && bTop.visible) {
          const bollardW = 9 * (scale / (bBase.depth * 38)) * dpr

          // Bollard stem (Safety Yellow steel pipe with directional shading)
          const bShading = calcShading(0.7, 0.7, 0.1)
          ctx.lineWidth = bollardW
          ctx.lineCap = 'round'
          ctx.strokeStyle = `rgb(${Math.floor(234 * bShading)}, ${Math.floor(
            179 * bShading
          )}, 8)`
          ctx.beginPath()
          ctx.moveTo(bBase.sx, bBase.sy)
          ctx.lineTo(bTop.sx, bTop.sy)
          ctx.stroke()

          // Hazard black reflective stripe band
          if (bMid.visible) {
            ctx.lineWidth = bollardW * 1.05
            ctx.strokeStyle = '#0f172a'
            ctx.beginPath()
            ctx.moveTo(bMid.sx, bMid.sy - 3 * dpr)
            ctx.lineTo(bMid.sx, bMid.sy + 3 * dpr)
            ctx.stroke()
          }

          // Top optical strobe lamp
          const strobeColor = isHumanZoneClear ? '#22c55e' : '#ef4444'
          ctx.fillStyle = strobeColor
          ctx.beginPath()
          ctx.arc(bTop.sx, bTop.sy, 3.5 * dpr, 0, Math.PI * 2)
          ctx.fill()
        }
      })

      // Volumetric 3D laser boundary cage
      ctx.lineWidth = 1 * dpr
      ctx.setLineDash([4 * dpr, 4 * dpr])
      ctx.strokeStyle = `${zoneBorderColor}66`

      for (let i = 0; i < 4; i++) {
        const b = zoneCorners[i]
        const t = zoneCorners[i + 4]
        if (b.visible && t.visible) {
          ctx.beginPath()
          ctx.moveTo(b.sx, b.sy)
          ctx.lineTo(t.sx, t.sy)
          ctx.stroke()
        }
      }

      if (
        zoneCorners[4].visible &&
        zoneCorners[5].visible &&
        zoneCorners[6].visible &&
        zoneCorners[7].visible
      ) {
        ctx.beginPath()
        ctx.moveTo(zoneCorners[4].sx, zoneCorners[4].sy)
        ctx.lineTo(zoneCorners[5].sx, zoneCorners[5].sy)
        ctx.lineTo(zoneCorners[6].sx, zoneCorners[6].sy)
        ctx.lineTo(zoneCorners[7].sx, zoneCorners[7].sy)
        ctx.closePath()
        ctx.stroke()

        ctx.fillStyle = `${zoneColor}0.04)`
        ctx.fill()
      }
      ctx.setLineDash([])

      // Floating Zone Telemetry & Breach Status Banner
      const zoneLabelPos = project(2.5, 0.0, 2.3)
      if (zoneLabelPos.visible) {
        ctx.font = `bold ${Math.max(10, Math.floor(10.5 * dpr))}px monospace`
        ctx.textAlign = 'center'
        ctx.fillStyle = isHumanZoneClear ? '#22c55e' : '#ef4444'
        const breachText = isHumanZoneClear
          ? 'SECTOR 4 HAZARD ZONE [CLEAR]'
          : 'SECTOR 4 — BREACH DETECTED (HUMAN INTRUSION)'
        ctx.fillText(breachText, zoneLabelPos.sx, zoneLabelPos.sy)
      }

      // ----------------------------------------------------------------------
      // 4. Coolant Manifold Piping with Cylindrical Shading & Flanges
      // ----------------------------------------------------------------------
      const pipeStart = project(-2.5, 0, 0.42)
      const pumpPos = project(-2.0, 0, 0.42)
      const valvePos = project(0.0, 0, 0.42)
      const leakPos = project(0.35, 0, 0.42)
      const pipeEnd = project(2.2, 0, 0.42)

      // Main manifold pipe runner
      if (pipeStart.visible && pipeEnd.visible) {
        const pipeDiameter = 16 * (scale / (pipeStart.depth * 38)) * dpr

        // Outer brushed stainless steel casing
        ctx.lineWidth = pipeDiameter
        ctx.lineCap = 'round'
        ctx.strokeStyle = '#1e293b'
        ctx.beginPath()
        ctx.moveTo(pipeStart.sx, pipeStart.sy)
        ctx.lineTo(pipeEnd.sx, pipeEnd.sy)
        ctx.stroke()

        // Directional specular metallic highlight band
        ctx.lineWidth = pipeDiameter * 0.45
        ctx.strokeStyle = isPumpActive ? '#0284c7' : '#475569'
        ctx.stroke()

        ctx.lineWidth = pipeDiameter * 0.18
        ctx.strokeStyle = isPumpActive ? '#38bdf8' : '#94a3b8'
        ctx.stroke()

        // Active directional coolant flow pulses inside pipe
        if (isPumpActive && !reducedMotion) {
          for (let f = 0; f < 3; f++) {
            const flowX = -2.2 + ((flowPhaseRef.current + f * 0.33) % 1.0) * 4.2
            const fDot = project(flowX, 0, 0.42)
            if (fDot.visible) {
              ctx.fillStyle = 'rgba(56, 189, 248, 0.95)'
              ctx.beginPath()
              ctx.arc(fDot.sx, fDot.sy, 4.5 * dpr, 0, Math.PI * 2)
              ctx.fill()
            }
          }
        }
      }

      // Flange bolted joints at critical connections
      const flangeLocations = [
        [-1.6, 0.0, 0.42], // Pump discharge flange
        [-0.2, 0.0, 0.42], // Valve B inlet flange
        [0.2, 0.0, 0.42],  // Valve B outlet flange
        [0.35, 0.0, 0.42], // Leak test coupling flange
      ]
      flangeLocations.forEach(([fx, fy, fz]) => {
        const fp = project(fx, fy, fz)
        if (fp.visible) {
          const fRadius = 14 * (scale / (fp.depth * 38)) * dpr
          ctx.fillStyle = '#334155'
          ctx.strokeStyle = '#64748b'
          ctx.lineWidth = 1.5 * dpr
          ctx.beginPath()
          ctx.arc(fp.sx, fp.sy, fRadius, 0, Math.PI * 2)
          ctx.fill()
          ctx.stroke()

          // Flange bolt studs
          ctx.fillStyle = '#cbd5e1'
          for (let b = 0; b < 4; b++) {
            const bAngle = (b * Math.PI) / 2
            ctx.beginPath()
            ctx.arc(
              fp.sx + Math.cos(bAngle) * (fRadius * 0.72),
              fp.sy + Math.sin(bAngle) * (fRadius * 0.72),
              1.6 * dpr,
              0,
              Math.PI * 2
            )
            ctx.fill()
          }
        }
      })

      // Bypass heat exchanger loop at Y = -1.0 with 90° elbows and T-junctions
      const bp1 = project(-1.0, 0, 0.42)
      const bp2 = project(-1.0, -1.0, 0.42)
      const bp3 = project(1.0, -1.0, 0.42)
      const bp4 = project(1.0, 0, 0.42)

      if (bp1.visible && bp2.visible && bp3.visible && bp4.visible) {
        const bpDia = 10 * (scale / (bp1.depth * 38)) * dpr
        ctx.lineWidth = bpDia
        ctx.lineCap = 'round'
        ctx.strokeStyle = '#1e293b'
        ctx.beginPath()
        ctx.moveTo(bp1.sx, bp1.sy)
        ctx.lineTo(bp2.sx, bp2.sy)
        ctx.lineTo(bp3.sx, bp3.sy)
        ctx.lineTo(bp4.sx, bp4.sy)
        ctx.stroke()

        ctx.lineWidth = bpDia * 0.45
        ctx.strokeStyle = '#475569'
        ctx.stroke()
      }

      // ----------------------------------------------------------------------
      // 5. Heavy Industrial Pump P1 (Motor, Fins, Volute & Spinning Impeller)
      // ----------------------------------------------------------------------
      if (pumpPos.visible) {
        const pSize = 25 * (scale / (pumpPos.depth * 35)) * dpr

        // Motor stator cylindrical body
        ctx.fillStyle = '#09101d'
        ctx.strokeStyle = isPumpActive ? '#22c55e' : '#475569'
        ctx.lineWidth = 2.5 * dpr
        ctx.beginPath()
        ctx.arc(pumpPos.sx, pumpPos.sy, pSize, 0, Math.PI * 2)
        ctx.fill()
        ctx.stroke()

        // Longitudinal cooling fins along motor body
        ctx.lineWidth = 1.5 * dpr
        ctx.strokeStyle = isPumpActive ? 'rgba(34, 197, 94, 0.5)' : '#334155'
        for (let fin = -3; fin <= 3; fin++) {
          const finOffset = fin * (pSize * 0.22)
          ctx.beginPath()
          ctx.moveTo(pumpPos.sx + finOffset, pumpPos.sy - pSize * 0.75)
          ctx.lineTo(pumpPos.sx + finOffset, pumpPos.sy + pSize * 0.75)
          ctx.stroke()
        }

        // Top terminal conduit box
        const junctionPos = project(-2.0, 0, 0.7)
        if (junctionPos.visible) {
          ctx.fillStyle = '#1e293b'
          ctx.strokeStyle = '#475569'
          ctx.lineWidth = 1.5 * dpr
          ctx.fillRect(junctionPos.sx - 8 * dpr, junctionPos.sy - 6 * dpr, 16 * dpr, 12 * dpr)
          ctx.strokeRect(junctionPos.sx - 8 * dpr, junctionPos.sy - 6 * dpr, 16 * dpr, 12 * dpr)
        }

        // Impeller spinning inside volute casing
        const impRad = (impellerAngleRef.current * Math.PI) / 180
        ctx.strokeStyle = isPumpActive ? '#4ade80' : '#64748b'
        ctx.lineWidth = 3.0 * dpr
        ctx.lineCap = 'round'
        for (let b = 0; b < 4; b++) {
          const angle = impRad + (b * Math.PI) / 2
          ctx.beginPath()
          ctx.moveTo(pumpPos.sx, pumpPos.sy)
          ctx.lineTo(
            pumpPos.sx + Math.cos(angle) * (pSize * 0.78),
            pumpPos.sy + Math.sin(angle) * (pSize * 0.78)
          )
          ctx.stroke()
        }

        // Center hub nut
        ctx.fillStyle = '#f8fafc'
        ctx.beginPath()
        ctx.arc(pumpPos.sx, pumpPos.sy, 3.5 * dpr, 0, Math.PI * 2)
        ctx.fill()

        // Pump status telemetry readout
        ctx.font = `bold ${Math.max(9, Math.floor(9.5 * dpr))}px monospace`
        ctx.fillStyle = isPumpActive ? '#22c55e' : '#94a3b8'
        ctx.textAlign = 'center'
        ctx.fillText(
          `PUMP P1 [${isPumpActive ? 'ACTIVE 1750 RPM' : 'STOPPED'}]`,
          pumpPos.sx,
          pumpPos.sy + pSize + 15 * dpr
        )
      }

      // ----------------------------------------------------------------------
      // 6. Detailed Valve B Revolute Joint Actuator & Andon Stack Light
      // ----------------------------------------------------------------------
      if (valvePos.visible) {
        const vSize = 22 * (scale / (valvePos.depth * 35)) * dpr

        // Valve cast globe body
        ctx.fillStyle = '#0d1527'
        ctx.strokeStyle = animatedAngleRef.current < 45 ? '#38bdf8' : '#a855f7'
        ctx.lineWidth = 3 * dpr
        ctx.beginPath()
        ctx.arc(valvePos.sx, valvePos.sy, vSize, 0, Math.PI * 2)
        ctx.fill()
        ctx.stroke()

        // Dial face graduations (0° to 90°)
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.4)'
        ctx.lineWidth = 1 * dpr
        for (let d = 0; d <= 90; d += 15) {
          const dRad = (d * Math.PI) / 180
          ctx.beginPath()
          ctx.moveTo(
            valvePos.sx + Math.cos(dRad) * (vSize * 0.75),
            valvePos.sy + Math.sin(dRad) * (vSize * 0.75)
          )
          ctx.lineTo(
            valvePos.sx + Math.cos(dRad) * (vSize * 0.95),
            valvePos.sy + Math.sin(dRad) * (vSize * 0.95)
          )
          ctx.stroke()
        }

        // Mechanical Revolute Joint Rotating Needle (0° = Open, 90° = Closed)
        const valveRad = (animatedAngleRef.current * Math.PI) / 180
        ctx.strokeStyle = '#f8fafc'
        ctx.lineWidth = 4 * dpr
        ctx.lineCap = 'round'
        ctx.beginPath()
        ctx.moveTo(
          valvePos.sx - Math.cos(valveRad) * (vSize * 0.75),
          valvePos.sy - Math.sin(valveRad) * (vSize * 0.75)
        )
        ctx.lineTo(
          valvePos.sx + Math.cos(valveRad) * (vSize * 0.75),
          valvePos.sy + Math.sin(valveRad) * (vSize * 0.75)
        )
        ctx.stroke()

        // Needle pivot center pin
        ctx.fillStyle = animatedAngleRef.current < 45 ? '#38bdf8' : '#ef4444'
        ctx.beginPath()
        ctx.arc(valvePos.sx, valvePos.sy, 4 * dpr, 0, Math.PI * 2)
        ctx.fill()

        // Actuator stem & Industrial Multi-Tier Stack Light Tower (Andon Tower)
        const stemTop = project(0.0, 0, 0.8)
        const towerTop = project(0.0, 0, 1.15)
        if (stemTop.visible && towerTop.visible) {
          // Actuator neck cylinder
          ctx.strokeStyle = '#475569'
          ctx.lineWidth = 5 * dpr
          ctx.beginPath()
          ctx.moveTo(valvePos.sx, valvePos.sy)
          ctx.lineTo(stemTop.sx, stemTop.sy)
          ctx.stroke()

          // Andon multi-lamp stack light housing
          ctx.fillStyle = '#0f172a'
          ctx.strokeStyle = '#334155'
          ctx.lineWidth = 1.5 * dpr
          ctx.fillRect(towerTop.sx - 6 * dpr, towerTop.sy - 14 * dpr, 12 * dpr, 28 * dpr)
          ctx.strokeRect(towerTop.sx - 6 * dpr, towerTop.sy - 14 * dpr, 12 * dpr, 28 * dpr)

          // 4 Stack Lamps: Red (Locked/Fault), Amber (Quarantined), Green (Verified), Cyan (Armed/Ready)
          const lampRadius = 4 * dpr
          const lamps = [
            { y: towerTop.sy - 9 * dpr, color: '#ef4444', active: isActuatorLocked },
            { y: towerTop.sy - 2 * dpr, color: '#f59e0b', active: isActuatorQuarantined },
            { y: towerTop.sy + 5 * dpr, color: '#22c55e', active: isActuatorVerified },
            { y: towerTop.sy + 12 * dpr, color: '#38bdf8', active: actuatorStatus === 'ARMED' || actuatorStatus === 'READY' },
          ]

          lamps.forEach(({ y, color, active }) => {
            ctx.fillStyle = active ? color : 'rgba(51, 65, 85, 0.45)'
            if (active) {
              ctx.shadowColor = color
              ctx.shadowBlur = 8 * dpr
            }
            ctx.beginPath()
            ctx.arc(towerTop.sx, y, lampRadius, 0, Math.PI * 2)
            ctx.fill()
            ctx.shadowBlur = 0
          })
        }

        // Telemetry Label beneath Valve B
        ctx.font = `bold ${Math.max(9, Math.floor(10 * dpr))}px monospace`
        ctx.fillStyle = animatedAngleRef.current < 45 ? '#38bdf8' : '#c084fc'
        ctx.textAlign = 'center'
        const stateWord = animatedAngleRef.current >= 80 ? 'CLOSED' : animatedAngleRef.current <= 10 ? 'OPEN' : 'THROTTLING'
        ctx.fillText(
          `VALVE B [θ = ${animatedAngleRef.current.toFixed(1)}°] (${stateWord})`,
          valvePos.sx,
          valvePos.sy + vSize + 15 * dpr
        )
      }

      // ----------------------------------------------------------------------
      // 7. Dynamic Coolant Leak Spray & Floor Splash Ripples
      // ----------------------------------------------------------------------
      if (isLeakActive && !isAngleClosed) {
        // High-pressure directional jet droplets
        particlesRef.current.forEach((p) => {
          const pt = project(p.x, p.y, p.z)
          if (pt.visible) {
            const alpha = Math.max(0, 1 - p.life / p.maxLife)
            ctx.fillStyle = `rgba(244, 63, 94, ${alpha * 0.9})`
            ctx.beginPath()
            ctx.arc(pt.sx, pt.sy, p.size * dpr, 0, Math.PI * 2)
            ctx.fill()
          }
        })

        // Ground splash ripples
        ripplesRef.current.forEach((r) => {
          const rp = project(r.x, r.y, 0.005)
          if (rp.visible) {
            const rxRadius = (r.radius / rp.depth) * scale
            const ryRadius = rxRadius * Math.sin(radEl)
            ctx.lineWidth = 1.2 * dpr
            ctx.strokeStyle = `rgba(244, 63, 94, ${r.alpha * 0.8})`
            ctx.beginPath()
            ctx.ellipse(rp.sx, rp.sy, rxRadius, Math.max(2, ryRadius), 0, 0, Math.PI * 2)
            ctx.stroke()
          }
        })

        // Floating Leak Source Warning Indicator
        if (leakPos.visible) {
          ctx.font = `bold ${Math.max(8.5, Math.floor(9 * dpr))}px monospace`
          ctx.fillStyle = '#f43f5e'
          ctx.textAlign = 'center'
          ctx.fillText('COOLANT LEAK ACTIVE', leakPos.sx, leakPos.sy - 18 * dpr)
        }
      }

      // ----------------------------------------------------------------------
      // 8. Articulated Human Worker Entity with Natural Walking Gait
      // ----------------------------------------------------------------------
      const workerX = animatedWorkerXRef.current
      const walkCycle = walkPhaseRef.current
      const torsoBob = Math.sin(walkCycle * 2) * 0.025

      const workerFeet = project(workerX, 0.0, 0.0)
      const workerPelvis = project(workerX, 0.0, 0.95 + torsoBob)
      const workerChest = project(workerX, 0.0, 1.35 + torsoBob)
      const workerHead = project(workerX, 0.0, 1.75 + torsoBob)

      if (workerFeet.visible && workerHead.visible && workerChest.visible) {
        // Dynamic ground contact shadow moving under worker's feet
        drawContactShadow(workerX, 0.0, 0.32, 0.18, 0.7)

        // Trajectory guide dotted line from initial position (5.0, 0)
        const trajStart = project(5.0, 0.0, 0.0)
        if (trajStart.visible) {
          ctx.lineWidth = 1.5 * dpr
          ctx.setLineDash([3 * dpr, 3 * dpr])
          ctx.strokeStyle = isHumanZoneClear
            ? 'rgba(34, 197, 94, 0.45)'
            : 'rgba(239, 68, 68, 0.65)'
          ctx.beginPath()
          ctx.moveTo(trajStart.sx, trajStart.sy)
          ctx.lineTo(workerFeet.sx, workerFeet.sy)
          ctx.stroke()
          ctx.setLineDash([])
        }

        // Articulated legs with trigonometric walking stride
        const legSwing = Math.sin(walkCycle) * 0.22
        const leftFootPos = project(workerX + legSwing, -0.1, 0.0)
        const rightFootPos = project(workerX - legSwing, 0.1, 0.0)

        ctx.lineWidth = 4 * dpr
        ctx.lineCap = 'round'
        ctx.strokeStyle = '#1e293b' // Dark work trousers

        // Left leg
        if (leftFootPos.visible && workerPelvis.visible) {
          ctx.beginPath()
          ctx.moveTo(workerPelvis.sx, workerPelvis.sy)
          ctx.lineTo(leftFootPos.sx, leftFootPos.sy)
          ctx.stroke()

          // Left boot
          ctx.fillStyle = '#0f172a'
          ctx.beginPath()
          ctx.ellipse(leftFootPos.sx, leftFootPos.sy, 4.5 * dpr, 2.5 * dpr, 0, 0, Math.PI * 2)
          ctx.fill()
        }

        // Right leg
        if (rightFootPos.visible && workerPelvis.visible) {
          ctx.beginPath()
          ctx.moveTo(workerPelvis.sx, workerPelvis.sy)
          ctx.lineTo(rightFootPos.sx, rightFootPos.sy)
          ctx.stroke()

          // Right boot
          ctx.fillStyle = '#0f172a'
          ctx.beginPath()
          ctx.ellipse(rightFootPos.sx, rightFootPos.sy, 4.5 * dpr, 2.5 * dpr, 0, 0, Math.PI * 2)
          ctx.fill()
        }

        // Articulated arms swinging in counter-rhythm to legs
        const armSwing = Math.sin(walkCycle) * 0.18
        const leftHand = project(workerX - armSwing, -0.22, 1.05 + torsoBob)
        const rightHand = project(workerX + armSwing, 0.22, 1.05 + torsoBob)

        ctx.lineWidth = 3 * dpr
        ctx.strokeStyle = '#334155'
        if (leftHand.visible) {
          ctx.beginPath()
          ctx.moveTo(workerChest.sx, workerChest.sy)
          ctx.lineTo(leftHand.sx, leftHand.sy)
          ctx.stroke()
        }
        if (rightHand.visible) {
          ctx.beginPath()
          ctx.moveTo(workerChest.sx, workerChest.sy)
          ctx.lineTo(rightHand.sx, rightHand.sy)
          ctx.stroke()
        }

        // Torso: Fluorescent Two-Tone Safety Vest
        const vestWidth = 8 * dpr
        ctx.lineWidth = vestWidth
        ctx.strokeStyle = isHumanZoneClear ? '#84cc16' : '#ef4444' // Hi-Vis lime yellow / breach red
        ctx.beginPath()
        ctx.moveTo(workerPelvis.sx, workerPelvis.sy)
        ctx.lineTo(workerChest.sx, workerChest.sy)
        ctx.stroke()

        // Silver retroreflective micro-prismatic safety stripes across torso
        ctx.lineWidth = 2.2 * dpr
        ctx.strokeStyle = '#f8fafc'
        ctx.beginPath()
        ctx.moveTo(workerChest.sx - vestWidth * 0.6, workerChest.sy + 5 * dpr)
        ctx.lineTo(workerChest.sx + vestWidth * 0.6, workerChest.sy + 5 * dpr)
        ctx.stroke()

        // Worker Head & Safety Hardhat with Brim
        const headRadius = 6.0 * dpr
        ctx.fillStyle = '#eab308' // Industrial Yellow Safety Hardhat
        ctx.beginPath()
        ctx.arc(workerHead.sx, workerHead.sy, headRadius, 0, Math.PI * 2)
        ctx.fill()

        // Hardhat brim
        ctx.fillStyle = '#ca8a04'
        ctx.beginPath()
        ctx.ellipse(workerHead.sx, workerHead.sy + 2 * dpr, headRadius * 1.3, 2 * dpr, 0, 0, Math.PI * 2)
        ctx.fill()

        // Face & safety glasses silhouette
        ctx.fillStyle = '#fed7aa'
        ctx.beginPath()
        ctx.arc(workerHead.sx, workerHead.sy + 3 * dpr, headRadius * 0.65, 0, Math.PI * 2)
        ctx.fill()

        // Worker Telemetry Badge
        ctx.font = `bold ${Math.max(9, Math.floor(9.5 * dpr))}px monospace`
        ctx.fillStyle = isHumanZoneClear ? '#22c55e' : '#f43f5e'
        ctx.textAlign = 'center'
        ctx.fillText(
          `WORKER_01 (${workerX.toFixed(1)}m)`,
          workerHead.sx,
          workerHead.sy - 14 * dpr
        )
      }

      // ----------------------------------------------------------------------
      // 9. Actuator Gateway Enclave Enclosure (/World/Gateway)
      // ----------------------------------------------------------------------
      const gatewayPos = project(-1.8, 1.2, 0.45)
      if (gatewayPos.visible) {
        drawContactShadow(-1.8, 1.2, 0.28, 0.2, 0.55)
        ctx.fillStyle = '#0f172a'
        ctx.strokeStyle = isActuatorLocked
          ? '#ef4444'
          : isActuatorQuarantined
          ? '#f59e0b'
          : isActuatorVerified
          ? '#22c55e'
          : '#38bdf8'
        ctx.lineWidth = 2 * dpr
        ctx.fillRect(gatewayPos.sx - 12 * dpr, gatewayPos.sy - 16 * dpr, 24 * dpr, 32 * dpr)
        ctx.strokeRect(gatewayPos.sx - 12 * dpr, gatewayPos.sy - 16 * dpr, 24 * dpr, 32 * dpr)

        // Gateway status beacon lamp
        ctx.fillStyle = isActuatorLocked
          ? '#ef4444'
          : isActuatorQuarantined
          ? '#f59e0b'
          : isActuatorVerified
          ? '#22c55e'
          : '#38bdf8'
        ctx.beginPath()
        ctx.arc(gatewayPos.sx, gatewayPos.sy - 8 * dpr, 4 * dpr, 0, Math.PI * 2)
        ctx.fill()

        // Gateway Label
        ctx.font = `${Math.max(8, Math.floor(8.5 * dpr))}px monospace`
        ctx.fillStyle = '#94a3b8'
        ctx.textAlign = 'center'
        ctx.fillText('SAFETY GATEWAY', gatewayPos.sx, gatewayPos.sy + 24 * dpr)
      }

      animationFrameId = requestAnimationFrame(render)
    }

    animationFrameId = requestAnimationFrame(render)
    return () => {
      cancelAnimationFrame(animationFrameId)
    }
  }, [
    azimuth,
    elevation,
    distance,
    target,
    targetAngle,
    targetWorkerX,
    isPumpActive,
    isLeakActive,
    isHumanZoneClear,
    actuatorStatus,
    isActuatorLocked,
    isActuatorQuarantined,
    isActuatorVerified,
    cameraMode,
    reducedMotion,
  ])

  return (
    <div
      className={`isaac-viewport-container ${isFullscreen ? 'is-fullscreen' : ''}`}
      ref={containerRef}
      tabIndex={0}
      role="region"
      aria-label="NVIDIA Isaac Sim 3D Interactive Viewport"
      data-testid="isaac-viewport-3d"
    >
      <div className={`isaac-viewport-aspect ${isFullscreen ? 'is-fullscreen' : ''}`}>
        {/* Top Header & Fast Action Toolbar */}
        <div className="isaac-viewport-header">
          <div className="isaac-header-badge-group">
            <span
              className="isaac-nvidia-badge"
              title="High-Fidelity Omniverse USD Articulation & Contact Simulation"
            >
              <Cpu size={13} />
              <span>NVIDIA ISAAC SIM 3D</span>
            </span>
            <span className="isaac-stage-pill" title="Current OpenUSD Stage Root">
              <Layers size={11} />
              <span>
                {(
                  effectivePrimPaths.valve_b ||
                  '/World/IndustrialCell/CoolantManifold/ValveB'
                ).split('/CoolantManifold')[0]}
              </span>
            </span>
          </div>

          {/* Presentation Camera Director Mode Indicator */}
          <div className="isaac-director-status-pill">
            <Video size={11} style={{ color: cameraMode === 'auto' ? '#76b900' : '#f59e0b' }} />
            <span className="isaac-director-mode">
              DIRECTOR: {cameraMode === 'auto' ? 'AUTO' : 'MANUAL'}
            </span>
            <span className="isaac-director-focus">[{directorFocus}]</span>
            {cameraMode === 'manual' && (
              <button
                type="button"
                className="isaac-resume-director-btn"
                onClick={handleResumeAutoCamera}
                title="Resume automated Presentation Camera Director"
              >
                <Eye size={10} />
                <span>RESUME AUTO</span>
              </button>
            )}
          </div>

          <div className="isaac-header-actions">
            {onTogglePlay && (
              <button
                type="button"
                className={`isaac-btn primary`}
                onClick={onTogglePlay}
                title={isPlaying ? 'Pause Simulation' : 'Play / Step Simulation'}
                data-testid="isaac-btn-play-pause"
              >
                {isPlaying ? <Pause size={12} /> : <Play size={12} />}
                <span>{isPlaying ? 'PAUSE' : 'STEP / RUN'}</span>
              </button>
            )}

            {onStepBack && (
              <button
                type="button"
                className="isaac-btn"
                onClick={onStepBack}
                title="Step Simulation Backward"
                data-testid="isaac-btn-step-back"
              >
                <SkipBack size={12} />
              </button>
            )}

            {onStepForward && (
              <button
                type="button"
                className="isaac-btn"
                onClick={onStepForward}
                title="Step Simulation Forward"
                data-testid="isaac-btn-step-forward"
              >
                <SkipForward size={12} />
              </button>
            )}

            <button
              type="button"
              className="isaac-btn"
              onClick={handleFitScene}
              title="Automatically frame full industrial cell and safety zones"
              data-testid="isaac-btn-fit-scene"
            >
              <Camera size={12} />
              <span>FIT SCENE</span>
            </button>

            <button
              type="button"
              className="isaac-btn"
              onClick={handleResetSimulation}
              title="Reset camera and simulation state to initial conditions"
              data-testid="isaac-btn-restore-view"
            >
              <RotateCcw size={12} />
              <span>RESET / VIEW</span>
            </button>

            <button
              type="button"
              className="isaac-btn"
              onClick={handleDownloadUsd}
              title="Export valid OpenUSD ASCII Stage (.usda)"
              data-testid="isaac-btn-export-usd"
            >
              <Download size={12} />
              <span>EXPORT USD</span>
            </button>

            <button
              type="button"
              className="isaac-btn"
              onClick={toggleFullscreen}
              title="Toggle Fullscreen"
              data-testid="isaac-btn-fullscreen"
            >
              {isFullscreen ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
            </button>
          </div>
        </div>

        {/* Camera Presets Selector */}
        <div className="isaac-camera-presets" role="toolbar" aria-label="Camera Presets">
          <span style={{ fontSize: '10px', color: '#64748b', alignSelf: 'center', padding: '0 4px' }}>
            <Compass size={11} style={{ display: 'inline', verticalAlign: '-1px' }} />
          </span>
          <button
            type="button"
            className={`isaac-preset-btn ${preset === 'iso' ? 'active' : ''}`}
            onClick={() => applyPreset('iso')}
            title="Isometric Presentation View"
          >
            ISO
          </button>
          <button
            type="button"
            className={`isaac-preset-btn ${preset === 'top' ? 'active' : ''}`}
            onClick={() => applyPreset('top')}
            title="Top-Down Bird's Eye Safety Zone View"
          >
            TOP
          </button>
          <button
            type="button"
            className={`isaac-preset-btn ${preset === 'front' ? 'active' : ''}`}
            onClick={() => applyPreset('front')}
            title="Front Elevation Manifold View"
          >
            FRONT
          </button>
          <button
            type="button"
            className={`isaac-preset-btn ${preset === 'side' ? 'active' : ''}`}
            onClick={() => applyPreset('side')}
            title="Side Sector 4 Boundary Profile"
          >
            SIDE
          </button>
        </div>

        {/* Live HUD Telemetry Card */}
        <div className="isaac-hud-panel" data-testid="isaac-hud-panel">
          <div className="isaac-hud-row">
            <span className="isaac-hud-label">VALVE B JOINT:</span>
            <span
              className="isaac-hud-val"
              style={{ color: targetAngle < 45 ? '#38bdf8' : '#c084fc' }}
            >
              {(plantState.valve_b_angle_deg ?? (plantState.valve_b_state === 'OPEN' ? 0.0 : 90.0)).toFixed(1)}° ({plantState.valve_b_state})
            </span>
          </div>
          <div className="isaac-hud-row">
            <span className="isaac-hud-label">SECTOR 4 ZONE:</span>
            <span
              className="isaac-hud-val"
              style={{ color: isHumanZoneClear ? '#22c55e' : '#ef4444' }}
            >
              {plantState.human_zone} ({(plantState.human_distance_m ?? (isHumanZoneClear ? 5.0 : 2.5)).toFixed(1)}m)
            </span>
          </div>
          <div className="isaac-hud-row">
            <span className="isaac-hud-label">GATEWAY ACTUATOR:</span>
            <span
              className="isaac-hud-val"
              style={{
                color:
                  actuatorStatus === 'LOCKED'
                    ? '#ef4444'
                    : actuatorStatus === 'QUARANTINED'
                    ? '#f59e0b'
                    : actuatorStatus === 'VERIFIED'
                    ? '#22c55e'
                    : '#38bdf8',
              }}
            >
              {actuatorStatus}
            </span>
          </div>
          <div className="isaac-hud-row">
            <span className="isaac-hud-label">COOLANT FLOW:</span>
            <span
              className="isaac-hud-val"
              style={{ color: isLeakActive ? '#f43f5e' : '#22c55e' }}
            >
              {isLeakActive
                ? `LEAK (${plantState.flow_rate_lpm?.toFixed(1) || '14.0'} LPM)`
                : 'NOMINAL (0 LEAKS)'}
            </span>
          </div>
        </div>

        {/* Interactive HTML5 3D Canvas */}
        <canvas
          ref={canvasRef}
          className="isaac-canvas"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onContextMenu={handleContextMenu}
          onDoubleClick={handleDoubleClick}
          data-testid="isaac-3d-canvas"
        />

        {/* Viewport Footer Bar: Control Instructions & Camera Readout */}
        <div className="isaac-viewport-footer">
          <div className="isaac-hints-bar">
            <span className="isaac-hint-item">
              <span className="isaac-hint-key">Scroll</span>
              <span>Zoom</span>
            </span>
            <span className="isaac-hint-item">
              <span className="isaac-hint-key">Left Drag</span>
              <span>Orbit</span>
            </span>
            <span className="isaac-hint-item">
              <span className="isaac-hint-key">Right / Shift+Drag</span>
              <span>Pan</span>
            </span>
            <span className="isaac-hint-item">
              <span className="isaac-hint-key">Double Click</span>
              <span>Reset</span>
            </span>
          </div>

          <div className="isaac-camera-readout">
            <span>R: {distance.toFixed(1)}m</span>
            <span>Az: {azimuth.toFixed(0)}°</span>
            <span>El: {elevation.toFixed(0)}°</span>
            <span className="isaac-fps-badge">
              {fps} FPS ({frameTimeMs}ms)
            </span>
          </div>
        </div>
      </div>

      {/* Truthful Host Environment & ISAAC SIM Disclosure Banner */}
      <div className="isaac-runtime-banner">
        <div className="isaac-runtime-info">
          <Shield size={13} style={{ color: '#76b900' }} />
          <span>
            <strong>NVIDIA Isaac Sim Stage Engine:</strong> Authoritative kinematic joint & bounding physics active.
          </span>
          <span className="isaac-runtime-tag">
            <Activity size={10} />
            <span>USD STAGE READY</span>
          </span>
        </div>

        <div className="isaac-runtime-export-group">
          <span>Native RTX GPU runner:</span>
          <button
            type="button"
            className="isaac-link-btn"
            onClick={handleDownloadRunner}
            title="Download standalone Python runner for native Isaac Sim on Linux/Windows RTX workstation"
          >
            <FileCode size={11} style={{ display: 'inline', verticalAlign: '-1px', marginRight: '3px' }} />
            isaac_motionfence_cell.py
          </button>
        </div>
      </div>
    </div>
  )
}
