import React, { useRef, useEffect, useState, useLayoutEffect } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import {
  Camera,
  AlertTriangle,
  Layers,
} from 'lucide-react'
import { PresentationPlantState } from '../../types/presentation'
import './WebGLIndustrialPlant.css'

interface WebGLIndustrialPlantProps {
  plantState: PresentationPlantState
  cameraPreset?: 'full' | 'valve_b' | 'safety_zone' | 'actuator' | 'recovery'
  height?: number | string
  interactive?: boolean
  showHud?: boolean
  reducedMotion?: boolean
}

const PRESET_CONFIGS: Record<
  string,
  { pos: [number, number, number]; look: [number, number, number] }
> = {
  full: { pos: [6.2, 4.5, 7.2], look: [0.8, 1.0, 0.0] },
  valve_b: { pos: [1.8, 2.0, 2.6], look: [0.5, 1.2, 0.0] },
  safety_zone: { pos: [4.8, 3.2, 4.8], look: [2.5, 0.8, 0.5] },
  actuator: { pos: [1.2, 1.8, 1.8], look: [0.5, 1.4, 0.0] },
  recovery: { pos: [-1.2, 2.8, 4.2], look: [-0.5, 1.0, 0.0] },
}

export const WebGLIndustrialPlant: React.FC<WebGLIndustrialPlantProps> = ({
  plantState,
  cameraPreset = 'full',
  height = '100%',
  interactive = true,
  showHud = true,
  reducedMotion = false,
}) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [webglSupported, setWebglSupported] = useState<boolean>(true)
  const [activePreset, setActivePreset] = useState<string>(cameraPreset)
  const orbitingRef = useRef(false)

  // Internal 3D object references
  const sceneRef = useRef<THREE.Scene | null>(null)
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null)
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null)
  const controlsRef = useRef<OrbitControls | null>(null)
  
  // Transformable 3D meshes
  const valveWheelGroupRef = useRef<THREE.Group | null>(null)
  const workerGroupRef = useRef<THREE.Group | null>(null)
  const safetyZoneMeshRef = useRef<THREE.Mesh | null>(null)
  const safetyBeaconLightRef = useRef<THREE.PointLight | null>(null)
  const actuatorLedRef = useRef<THREE.Mesh | null>(null)
  const leakParticlesRef = useRef<THREE.Points | null>(null)

  // Target values for smooth interpolation
  const targetAngleDegRef = useRef<number>(0.0)
  const targetWorkerPosRef = useRef<[number, number, number]>([5.0, 0, 2.0])
  const targetCamPosRef = useRef<THREE.Vector3>(new THREE.Vector3(6.2, 4.5, 7.2))
  const targetCamLookRef = useRef<THREE.Vector3>(new THREE.Vector3(0.8, 1.0, 0.0))

  const stateRef = useRef(plantState)
  const motionRef = useRef(reducedMotion)
  useLayoutEffect(() => { stateRef.current = plantState; motionRef.current = reducedMotion }, [plantState, reducedMotion])

  // Update targets before paint so the next WebGL frame cannot retain an old state.
  useLayoutEffect(() => {
    // Valve angle
    if (typeof plantState.valve_b_angle_deg === 'number' && Number.isFinite(plantState.valve_b_angle_deg)) {
      targetAngleDegRef.current = plantState.valve_b_angle_deg
    } else {
      // Categorical valve geometry; no measured angle is inferred for the HUD.
      targetAngleDegRef.current = plantState.valve_b_state === 'CLOSED' ? 90 : 0
    }

    // Worker position based on distance / zone
    const isBreach =
      ['OCCUPIED', 'SECTOR_4_BREACH'].includes(plantState.human_zone) ||
      (typeof plantState.human_distance_m === 'number' && plantState.human_distance_m < 3.0)
    
    if (isBreach) {
      const dist = plantState.human_distance_m ?? 2.0
      targetWorkerPosRef.current = [dist, 0, 0.4]
    } else {
      targetWorkerPosRef.current = [5.0, 0, 2.0]
    }
  }, [plantState])

  // Update camera preset target
  useEffect(() => {
    setActivePreset(cameraPreset)
    const cfg = PRESET_CONFIGS[cameraPreset] || PRESET_CONFIGS.full
    targetCamPosRef.current.set(...cfg.pos)
    targetCamLookRef.current.set(...cfg.look)
  }, [cameraPreset])

  // Main Three.js Scene Setup
  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    // WebGL capability check
    try {
      const gl = canvas.getContext('webgl2') || canvas.getContext('webgl')
      if (!gl) {
        setWebglSupported(false)
        return
      }
    } catch {
      setWebglSupported(false)
      return
    }

    const width = container.clientWidth || 800
    const height = container.clientHeight || 500

    // Scene
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0a0f1a)
    scene.fog = new THREE.FogExp2(0x0a0f1a, 0.04)
    sceneRef.current = scene

    // Camera
    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 100)
    camera.position.set(6.2, 4.5, 7.2)
    cameraRef.current = camera

    // Renderer
    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      powerPreference: 'high-performance',
    })
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.1
    rendererRef.current = renderer

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.05
    controls.maxPolarAngle = Math.PI / 2 - 0.02 // Don't go below floor
    controls.minDistance = 1.2
    controls.maxDistance = 20
    controls.target.set(0.8, 1.0, 0.0)
    controlsRef.current = controls

    controls.addEventListener('start', () => { orbitingRef.current = true })
    controls.addEventListener('end', () => { orbitingRef.current = false })

    // -------------------------------------------------------------
    // LIGHTING
    // -------------------------------------------------------------
    const ambientLight = new THREE.AmbientLight(0x1e293b, 1.6)
    scene.add(ambientLight)

    const mainSun = new THREE.DirectionalLight(0xffffff, 2.2)
    mainSun.position.set(8, 12, 6)
    mainSun.castShadow = true
    mainSun.shadow.mapSize.width = 1024
    mainSun.shadow.mapSize.height = 1024
    mainSun.shadow.bias = -0.0005
    scene.add(mainSun)

    const blueFill = new THREE.DirectionalLight(0x0ea5e9, 0.8)
    blueFill.position.set(-6, 8, -4)
    scene.add(blueFill)

    // Floor Grid & Base
    const grid = new THREE.GridHelper(24, 24, 0x334155, 0x1e293b)
    grid.position.y = 0.001
    scene.add(grid)

    // Machinery Concrete Pad
    const padGeo = new THREE.BoxGeometry(7.0, 0.15, 4.5)
    const padMat = new THREE.MeshStandardMaterial({
      color: 0x1e293b,
      roughness: 0.8,
      metalness: 0.1,
    })
    const pad = new THREE.Mesh(padGeo, padMat)
    pad.position.set(0.5, 0.075, 0.0)
    pad.receiveShadow = true
    scene.add(pad)

    // Hazard Stripes on Pad Border
    const stripeGeo = new THREE.BoxGeometry(7.04, 0.02, 0.2)
    const stripeMat = new THREE.MeshBasicMaterial({ color: 0xfacc15 })
    const stripeFront = new THREE.Mesh(stripeGeo, stripeMat)
    stripeFront.position.set(0.5, 0.16, 2.2)
    scene.add(stripeFront)

    // -------------------------------------------------------------
    // STEEL PIPING MANIFOLD
    // -------------------------------------------------------------
    const pipeMat = new THREE.MeshStandardMaterial({
      color: 0x475569,
      metalness: 0.85,
      roughness: 0.2,
    })
    const flangeMat = new THREE.MeshStandardMaterial({
      color: 0x334155,
      metalness: 0.9,
      roughness: 0.3,
    })

    // Main Line Pipe (Horizontal from x = -2.5 to x = 3.5, y = 1.0)
    const mainPipeGeo = new THREE.CylinderGeometry(0.18, 0.18, 6.0, 24)
    const mainPipe = new THREE.Mesh(mainPipeGeo, pipeMat)
    mainPipe.rotation.z = Math.PI / 2
    mainPipe.position.set(0.5, 1.0, 0.0)
    mainPipe.castShadow = true
    scene.add(mainPipe)

    // Pipe Supports
    for (const xPos of [-1.8, 0.5, 2.8]) {
      const legGeo = new THREE.CylinderGeometry(0.06, 0.06, 0.9, 12)
      const leg = new THREE.Mesh(legGeo, flangeMat)
      leg.position.set(xPos, 0.525, 0.0)
      leg.castShadow = true
      scene.add(leg)
    }

    // Flange Rings
    const addFlange = (x: number) => {
      const fGeo = new THREE.CylinderGeometry(0.28, 0.28, 0.06, 20)
      const fMesh = new THREE.Mesh(fGeo, flangeMat)
      fMesh.rotation.z = Math.PI / 2
      fMesh.position.set(x, 1.0, 0.0)
      fMesh.castShadow = true
      scene.add(fMesh)
    }
    addFlange(-1.2)
    addFlange(-0.8)
    addFlange(0.0)
    addFlange(0.6)
    addFlange(1.6)

    // -------------------------------------------------------------
    // VALVE A: MANUAL GATE VALVE (Upstream Isolation at x = -1.0)
    // -------------------------------------------------------------
    const valveABodyGeo = new THREE.BoxGeometry(0.42, 0.42, 0.42)
    const valveABody = new THREE.Mesh(valveABodyGeo, flangeMat)
    valveABody.position.set(-1.0, 1.0, 0.0)
    valveABody.castShadow = true
    scene.add(valveABody)

    const valveAWheelGeo = new THREE.TorusGeometry(0.22, 0.03, 12, 24)
    const valveAWheel = new THREE.Mesh(
      valveAWheelGeo,
      new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.7 })
    )
    valveAWheel.rotation.x = Math.PI / 2
    valveAWheel.position.set(-1.0, 1.45, 0.0)
    scene.add(valveAWheel)

    // -------------------------------------------------------------
    // VALVE B: MOTORIZED ACTUATED VALVE (Primary Target at x = 0.3)
    // -------------------------------------------------------------
    const valveBGroup = new THREE.Group()
    valveBGroup.position.set(0.3, 1.0, 0.0)
    scene.add(valveBGroup)

    // Valve Body
    const valveBBody = new THREE.Mesh(
      new THREE.CylinderGeometry(0.26, 0.26, 0.48, 24),
      new THREE.MeshStandardMaterial({ color: 0x334155, metalness: 0.9, roughness: 0.25 })
    )
    valveBBody.rotation.z = Math.PI / 2
    valveBBody.castShadow = true
    valveBGroup.add(valveBBody)

    // Bonnet & Stem
    const bonnet = new THREE.Mesh(
      new THREE.CylinderGeometry(0.12, 0.16, 0.35, 16),
      flangeMat
    )
    bonnet.position.y = 0.3
    valveBGroup.add(bonnet)

    // Electric Rotary Actuator Housing (Industrial Yellow Box)
    const actuatorBox = new THREE.Mesh(
      new THREE.BoxGeometry(0.38, 0.45, 0.38),
      new THREE.MeshStandardMaterial({
        color: 0xeab308, // Safety yellow
        metalness: 0.3,
        roughness: 0.4,
      })
    )
    actuatorBox.position.y = 0.65
    actuatorBox.castShadow = true
    valveBGroup.add(actuatorBox)

    // Actuator Status LED Light
    const ledGeo = new THREE.SphereGeometry(0.04, 16, 16)
    const ledMat = new THREE.MeshBasicMaterial({ color: 0x22c55e })
    const led = new THREE.Mesh(ledGeo, ledMat)
    led.position.set(0.0, 0.75, 0.2)
    valveBGroup.add(led)
    actuatorLedRef.current = led

    // Valve Rotating Mechanism & Handwheel
    const wheelGroup = new THREE.Group()
    wheelGroup.position.set(0.0, 0.95, 0.0)
    valveBGroup.add(wheelGroup)
    valveWheelGroupRef.current = wheelGroup

    const wheelTorus = new THREE.Mesh(
      new THREE.TorusGeometry(0.26, 0.025, 12, 24),
      new THREE.MeshStandardMaterial({ color: 0xd97706, metalness: 0.6, roughness: 0.3 })
    )
    wheelTorus.rotation.x = Math.PI / 2
    wheelGroup.add(wheelTorus)

    // Wheel Spokes
    for (let s = 0; s < 4; s++) {
      const spoke = new THREE.Mesh(
        new THREE.CylinderGeometry(0.015, 0.015, 0.5, 8),
        flangeMat
      )
      spoke.rotation.z = Math.PI / 2
      spoke.rotation.y = (s * Math.PI) / 2
      wheelGroup.add(spoke)
    }

    // -------------------------------------------------------------
    // PUMP P1 & COOLING HEAT EXCHANGER (At x = -2.2)
    // -------------------------------------------------------------
    const pumpGeo = new THREE.CylinderGeometry(0.45, 0.45, 0.7, 24)
    const pumpMat = new THREE.MeshStandardMaterial({
      color: 0x0284c7, // Blue industrial motor
      metalness: 0.6,
      roughness: 0.3,
    })
    const pump = new THREE.Mesh(pumpGeo, pumpMat)
    pump.position.set(-2.2, 0.65, 0.0)
    pump.castShadow = true
    scene.add(pump)

    // Cooling loop coil (cyan tubes)
    const coilMat = new THREE.MeshStandardMaterial({
      color: 0x06b6d4,
      emissive: 0x0891b2,
      emissiveIntensity: 0.2,
      metalness: 0.7,
    })
    const coilGeo = new THREE.TorusGeometry(0.52, 0.04, 12, 32)
    const coil = new THREE.Mesh(coilGeo, coilMat)
    coil.position.set(-2.2, 0.65, 0.0)
    coil.rotation.x = Math.PI / 2
    scene.add(coil)

    // -------------------------------------------------------------
    // SAFETY ZONE CYLINDRICAL PERIMETER
    // -------------------------------------------------------------
    const zoneRadius = 2.4
    const zoneGeo = new THREE.CylinderGeometry(zoneRadius, zoneRadius, 0.06, 48)
    const zoneMat = new THREE.MeshBasicMaterial({
      color: 0x22c55e,
      transparent: true,
      opacity: 0.22,
      depthWrite: false,
    })
    const zoneMesh = new THREE.Mesh(zoneGeo, zoneMat)
    zoneMesh.position.set(0.8, 0.03, 0.0)
    scene.add(zoneMesh)
    safetyZoneMeshRef.current = zoneMesh

    // Warning perimeter ring border
    const ringGeo = new THREE.RingGeometry(zoneRadius - 0.05, zoneRadius + 0.05, 48)
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x22c55e,
      side: THREE.DoubleSide,
    })
    const ringMesh = new THREE.Mesh(ringGeo, ringMat)
    ringMesh.rotation.x = Math.PI / 2
    ringMesh.position.set(0.8, 0.065, 0.0)
    scene.add(ringMesh)

    // Safety Beacon PointLight
    const beacon = new THREE.PointLight(0x22c55e, 1.5, 6)
    beacon.position.set(0.8, 2.2, 0.0)
    scene.add(beacon)
    safetyBeaconLightRef.current = beacon

    // -------------------------------------------------------------
    // 3D HUMAN WORKER AVATAR
    // -------------------------------------------------------------
    const workerGroup = new THREE.Group()
    workerGroup.position.set(5.0, 0, 2.0)
    scene.add(workerGroup)
    workerGroupRef.current = workerGroup

    // Boots
    const bootMat = new THREE.MeshStandardMaterial({ color: 0x0f172a })
    for (const bX of [-0.1, 0.1]) {
      const boot = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.12, 0.22), bootMat)
      boot.position.set(bX, 0.06, 0.02)
      workerGroup.add(boot)
    }

    // Legs / Pants (Navy)
    const pantsMat = new THREE.MeshStandardMaterial({ color: 0x1e3a8a })
    const legs = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.65, 0.18), pantsMat)
    legs.position.set(0, 0.44, 0)
    legs.castShadow = true
    workerGroup.add(legs)

    // Torso with High-Vis Safety Vest (Orange + reflective stripes)
    const vestMat = new THREE.MeshStandardMaterial({
      color: 0xf97316,
      roughness: 0.5,
    })
    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.6, 0.22), vestMat)
    torso.position.set(0, 1.05, 0)
    torso.castShadow = true
    workerGroup.add(torso)

    // Head
    const headMat = new THREE.MeshStandardMaterial({ color: 0xfbd38d, roughness: 0.6 })
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 16), headMat)
    head.position.set(0, 1.48, 0)
    workerGroup.add(head)

    // Hard Hat (Bright Yellow)
    const hatMat = new THREE.MeshStandardMaterial({
      color: 0xfacc15,
      roughness: 0.3,
      metalness: 0.2,
    })
    const hat = new THREE.Mesh(new THREE.SphereGeometry(0.14, 16, 16), hatMat)
    hat.position.set(0, 1.54, 0)
    workerGroup.add(hat)
    const hatBrim = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.02, 16), hatMat)
    hatBrim.position.set(0, 1.5, 0)
    workerGroup.add(hatBrim)

    // -------------------------------------------------------------
    // LEAK VAPOR PARTICLE SYSTEM
    // -------------------------------------------------------------
    const leakCount = 120
    const leakPos = new Float32Array(leakCount * 3)
    for (let i = 0; i < leakCount; i++) {
      leakPos[i * 3 + 0] = 0.3 + (Math.random() - 0.5) * 0.2
      leakPos[i * 3 + 1] = 1.0 + Math.random() * 0.8
      leakPos[i * 3 + 2] = (Math.random() - 0.5) * 0.2
    }
    const leakGeo = new THREE.BufferGeometry()
    leakGeo.setAttribute('position', new THREE.BufferAttribute(leakPos, 3))
    const leakMat = new THREE.PointsMaterial({
      color: 0xe2e8f0,
      size: 0.08,
      transparent: true,
      opacity: 0.6,
      depthWrite: false,
    })
    const leakPoints = new THREE.Points(leakGeo, leakMat)
    scene.add(leakPoints)
    leakParticlesRef.current = leakPoints

    // -------------------------------------------------------------
    // ANIMATION & RENDER LOOP
    // -------------------------------------------------------------
    let animationFrameId: number
    const clock = new THREE.Clock()

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate)
      const elapsed = clock.getElapsedTime()

      const state = stateRef.current
      // Apply the selected discrete source state immediately. Rewind, scrubbing and
      // scenario changes must never animate an unrelated stroke or worker entry.
      if (valveWheelGroupRef.current) {
        valveWheelGroupRef.current.visible = ['OPEN', 'CLOSED'].includes(state.valve_b_state) || typeof state.valve_b_angle_deg === 'number'
        valveWheelGroupRef.current.rotation.y = targetAngleDegRef.current * Math.PI / 180
      }
      if (workerGroupRef.current) {
        workerGroupRef.current.visible = ['CLEAR', 'OCCUPIED', 'SECTOR_4_BREACH'].includes(state.human_zone)
        workerGroupRef.current.position.set(...targetWorkerPosRef.current)
      }
      const breached = ['OCCUPIED', 'SECTOR_4_BREACH'].includes(state.human_zone)
      const zoneColor = breached ? 0xef4444 : state.human_zone === 'CLEAR' ? 0x22c55e : 0x64748b
      if (safetyZoneMeshRef.current && safetyBeaconLightRef.current) {
        const material = safetyZoneMeshRef.current.material as THREE.MeshBasicMaterial
        material.color.setHex(zoneColor)
        material.opacity = breached && !motionRef.current ? 0.35 + Math.sin(elapsed * 8) * 0.15 : 0.2
        safetyBeaconLightRef.current.color.setHex(zoneColor)
      }
      if (actuatorLedRef.current) {
        const material = actuatorLedRef.current.material as THREE.MeshBasicMaterial
        material.color.setHex(state.actuator_status === 'LOCKED' ? 0xef4444 : state.actuator_status === 'HARDWARE_FAULT' ? 0xf59e0b : state.actuator_status === 'VERIFIED' ? 0x22c55e : 0x64748b)
      }

      // 5. Leak particle animation
      if (leakParticlesRef.current) {
        leakParticlesRef.current.visible = state.leak_active === true
        if (state.leak_active && !motionRef.current) {
          const pos = leakParticlesRef.current.geometry.attributes.position.array as Float32Array
          for (let i = 0; i < leakCount; i++) {
            pos[i * 3 + 1] += 0.015 // rise
            pos[i * 3 + 0] += (Math.random() - 0.5) * 0.008
            if (pos[i * 3 + 1] > 2.0) {
              pos[i * 3 + 1] = 1.0
              pos[i * 3 + 0] = 0.3 + (Math.random() - 0.5) * 0.15
            }
          }
          leakParticlesRef.current.geometry.attributes.position.needsUpdate = true
        }
      }

      // 6. Camera Director Lerp (only if user isn't actively orbiting)
      if (cameraRef.current && controlsRef.current && !orbitingRef.current) {
        if (motionRef.current) {
          cameraRef.current.position.copy(targetCamPosRef.current)
          controlsRef.current.target.copy(targetCamLookRef.current)
        } else {
          cameraRef.current.position.lerp(targetCamPosRef.current, 0.06)
          controlsRef.current.target.lerp(targetCamLookRef.current, 0.06)
        }
        controlsRef.current.update()
      } else if (controlsRef.current) {
        controlsRef.current.update()
      }

      // Expose the applied mesh state for visual regression checks.
      container.dataset.renderedValveRadians = valveWheelGroupRef.current?.visible ? String(valveWheelGroupRef.current.rotation.y) : 'UNKNOWN'
      container.dataset.renderedZone = state.human_zone
      renderer.render(scene, camera)
    }

    animate()

    // Resize Handler
    const handleResize = () => {
      if (!containerRef.current || !rendererRef.current || !cameraRef.current) return
      const w = containerRef.current.clientWidth
      const h = containerRef.current.clientHeight
      cameraRef.current.aspect = w / h
      cameraRef.current.updateProjectionMatrix()
      rendererRef.current.setSize(w, h)
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      cancelAnimationFrame(animationFrameId)
      controls.dispose()
      renderer.dispose()
    }
  }, [])

  // Camera preset click handler
  const handleSelectPreset = (preset: 'full' | 'valve_b' | 'safety_zone' | 'actuator' | 'recovery') => {
    setActivePreset(preset)
    const cfg = PRESET_CONFIGS[preset] || PRESET_CONFIGS.full
    targetCamPosRef.current.set(...cfg.pos)
    targetCamLookRef.current.set(...cfg.look)
  }

  const isZoneBreached =
    ['OCCUPIED', 'SECTOR_4_BREACH'].includes(plantState.human_zone) ||
    (typeof plantState.human_distance_m === 'number' && plantState.human_distance_m < 3.0)

  return (
    <div
      className="webgl-plant-container"
      ref={containerRef}
      data-source-state={JSON.stringify(plantState)}
      style={{ height, position: 'relative', overflow: 'hidden' }}
    >
      {!webglSupported ? (
        <div className="webgl-fallback-card">
          <AlertTriangle size={32} color="#f59e0b" />
          <h3>WebGL Hardware Acceleration Unavailable</h3>
          <p>Displaying procedural schematic representation of the physical plant state.</p>
          <div className="fallback-telemetry">
            <span>Valve B: {plantState.valve_b_state} ({plantState.valve_b_angle_deg ?? 'NOT_RECORDED'})</span>
            <span>Actuator: {plantState.actuator_status}</span>
            <span>Safety Zone: {plantState.human_zone}</span>
          </div>
        </div>
      ) : (
        <canvas ref={canvasRef} className="webgl-canvas" />
      )}

      {/* Floating Camera Preset Selector */}
      {interactive && webglSupported && (
        <div className="webgl-camera-presets-bar">
          <span className="preset-label">
            <Camera size={12} />
            <span>Framing:</span>
          </span>
          <button
            type="button"
            className={`preset-btn ${activePreset === 'full' ? 'active' : ''}`}
            onClick={() => handleSelectPreset('full')}
            title="Overview of complete industrial cell"
          >
            Overview
          </button>
          <button
            type="button"
            className={`preset-btn ${activePreset === 'valve_b' ? 'active' : ''}`}
            onClick={() => handleSelectPreset('valve_b')}
            title="Focus on Valve B isolation assembly"
          >
            Valve B
          </button>
          <button
            type="button"
            className={`preset-btn ${activePreset === 'safety_zone' ? 'active' : ''}`}
            onClick={() => handleSelectPreset('safety_zone')}
            title="Focus on human worker safety boundary"
          >
            Safety Zone
          </button>
          <button
            type="button"
            className={`preset-btn ${activePreset === 'actuator' ? 'active' : ''}`}
            onClick={() => handleSelectPreset('actuator')}
            title="Focus on actuator rotary mechanism and lock"
          >
            Actuator
          </button>
          <button
            type="button"
            className={`preset-btn ${activePreset === 'recovery' ? 'active' : ''}`}
            onClick={() => handleSelectPreset('recovery')}
            title="Focus on recovery manifold and pump"
          >
            Recovery
          </button>
        </div>
      )}

      {/* Floating Physical State Telemetry HUD */}
      {showHud && (
        <div className="webgl-hud-overlay">
          <div className="hud-badge angle-badge">
            <span className="hud-label">VALVE B ANGLE</span>
            <span className="hud-value">
              {typeof plantState.valve_b_angle_deg !== 'number' ? 'NOT_RECORDED' : `${plantState.valve_b_angle_deg.toFixed(1)}°`}
            </span>
          </div>

          <div className={`hud-badge zone-badge ${isZoneBreached ? 'danger' : plantState.human_zone === 'CLEAR' ? 'safe' : 'unknown'}`}>
            <span className="hud-label">SAFETY ZONE</span>
            <span className="hud-value">
              {plantState.human_zone}{typeof plantState.human_distance_m !== 'number' ? '' : ` (${plantState.human_distance_m}m)`}
            </span>
          </div>

          <div className={`hud-badge actuator-badge status-${plantState.actuator_status?.toLowerCase() || 'ready'}`}>
            <span className="hud-label">ACTUATOR</span>
            <span className="hud-value">{plantState.actuator_status || 'NOT_RECORDED'}</span>
          </div>

          <div className="hud-badge pressure-badge">
            <span className="hud-label">RECORDED TWIN PRESSURE</span>
            <span className="hud-value">{typeof plantState.pressure_psi !== 'number' ? 'NOT_RECORDED' : `${plantState.pressure_psi} PSI`}</span>
          </div>
        </div>
      )}

      {/* Footer Branding & Disclaimer */}
      <div className="webgl-footer-caption">
        <span className="engine-tag">
          <Layers size={11} />
          <span>Recorded simulation state · Worker placement and valve geometry are schematic</span>
        </span>
      </div>
    </div>
  )
}
