import { ExecutionMode, PhysicalBackend, ScenarioData } from './index'

export type SceneId =
  | 'intro'
  | 'safe'
  | 'denied'
  | 'toctou'
  | 'recovery'
  | 'telemetry'
  | 'evidence'
  | 'replay_assurance'
  | 'close'

export type DirectorState = 'IDLE' | 'STARTING' | 'RUNNING' | 'PAUSED' | 'ERROR' | 'COMPLETED'

export type SceneExecutionStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'VERIFIED'
  | 'DENIED'
  | 'BLOCKED'
  | 'VERIFICATION_FAILED'
  | 'RECOVERED'
  | 'COMPLETED'
  | 'UNVERIFIED'
  | 'UNKNOWN'
  | 'ERROR'

export interface SceneDefinition {
  id: SceneId
  sequenceNumber: number
  title: string
  subtitle: string
  narration: string
  scenarioId?: string
  executionMode: ExecutionMode
  physicalBackend: PhysicalBackend
  targetPanelId: string
  requiredPostcondition: string
  dwellTimeSeconds: number
  badgeLabel: string
  badgeType: 'allow' | 'deny' | 'warning' | 'info' | 'assurance'
  keyInsight: string
}

export interface DirectorProgress {
  currentSceneIndex: number
  state: DirectorState
  sceneStatus: SceneExecutionStatus
  completedScenes: SceneId[]
  errorMessage: string | null
  activeExecutionId: string | null
  dwellRemaining: number
  liveExecutionMode?: ExecutionMode
  scenarioData?: ScenarioData | null
}
