import { DigitalTwinPlantState, PhysicalBackend } from './index'

export type StageStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'PASSED'
  | 'DENIED'
  | 'BLOCKED'
  | 'FAILED'
  | 'UNVERIFIED'
  | 'NOT_APPLICABLE'

export interface StageProposalInfo {
  action: string
  target: string
  rationale: string
  confidence?: number
  provider: string
  model: string
  rawProposalHash?: string
}

export interface StagePolicyInfo {
  decision: 'ALLOW' | 'DENY'
  rulesEvaluated: number
  ruleViolations: string[]
  reason: string
}

export interface StageAuthorizationInfo {
  status: 'SIGNED' | 'NOT_ISSUED' | 'INVALIDATED' | 'REVOKED'
  ticketId?: string
  plantHash?: string
  expiresInSeconds?: number
  algorithm?: string
}

export interface StageWorldChangeInfo {
  previousVersion: number
  newVersion: number
  driftDetected: boolean
  description: string
  sensorTrigger?: string
}

export interface StageRevalidationInfo {
  status: 'PASSED' | 'FAILED' | 'WORLD_STATE_CHANGED' | 'NOT_REACHED'
  expectedHash?: string
  actualHash?: string
  versionMatch: boolean
  barriersChecked: number
}

export interface StageExecutionInfo {
  status: 'ACTUATED' | 'LOCKED' | 'HARDWARE_FAULT' | 'NOT_REACHED'
  actuatorId: string
  commandedAngle?: number
  faultInjected?: string
  busVoltageV?: number
}

export interface StageVerificationInfo {
  status: 'VERIFIED' | 'VERIFICATION_FAILED' | 'UNVERIFIED' | 'NOT_REACHED'
  isVerified: boolean
  limitSwitchReadback?: string
  commandedState?: string
  sensorContradiction?: boolean
}

export interface StageRecoveryInfo {
  status: 'RECOVERED' | 'QUARANTINED' | 'FAILED' | 'NOT_APPLICABLE'
  quarantinedValve?: string
  recoveryPath?: string
  isPostRecoveryVerified?: boolean
  disclosureNotice?: string
}

export interface PresentationFrame {
  scenarioId: string
  executionId?: string
  stageIndex: number // 0 to 9
  stageKey:
    | 'observe'
    | 'evidence'
    | 'proposal'
    | 'policy'
    | 'authorization'
    | 'world_change'
    | 'revalidation'
    | 'execution'
    | 'verification'
    | 'recovery'
  stageLabel: string
  stageSubtitle: string
  stageStatus: StageStatus
  
  // Specific stage evidence cards
  proposal?: StageProposalInfo
  policy?: StagePolicyInfo
  authorization?: StageAuthorizationInfo
  worldChange?: StageWorldChangeInfo
  revalidation?: StageRevalidationInfo
  execution?: StageExecutionInfo
  verification?: StageVerificationInfo
  recovery?: StageRecoveryInfo

  // Physical digital twin state for this frame
  plantState: DigitalTwinPlantState

  // Camera preset recommendation for this frame
  cameraPreset: 'full' | 'valve_b' | 'safety_zone' | 'actuator' | 'recovery'

  // Provenance & audit
  provenanceMode: 'LIVE' | 'REPLAY' | 'SIMULATION'
  recordHash?: string
  timestamp?: number
}

export interface PresentationTimeline {
  scenarioId: string
  scenarioTitle: string
  overallOutcome: 'NOMINAL' | 'DENIED' | 'BLOCKED' | 'RECOVERED' | 'VERIFICATION_FAILED' | 'UNVERIFIED' | 'UNKNOWN'
  frames: PresentationFrame[]
}
