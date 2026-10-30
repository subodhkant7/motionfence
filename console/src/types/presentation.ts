import { DigitalTwinPlantState, ExecutionMode } from './index'

export type StageStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'PASSED'
  | 'DENIED'
  | 'BLOCKED'
  | 'FAILED'
  | 'UNVERIFIED'
  | 'NOT_APPLICABLE'
export type PresentationOutcome =
  | 'NOMINAL'
  | 'DENIED'
  | 'BLOCKED'
  | 'RECOVERED'
  | 'VERIFICATION_FAILED'
  | 'COMPLETED'
  | 'UNVERIFIED'
  | 'UNKNOWN'
  | 'ERROR'
export type PresentationPlantState = Omit<
  DigitalTwinPlantState,
  'world_version'
> & { world_version?: number }

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
  decision: 'ALLOW' | 'DENY' | 'UNKNOWN'
  rulesEvaluated?: number
  ruleViolations: string[]
  reason: string
}
export interface StageAuthorizationInfo {
  status: string
  ticketId?: string
  plantHash?: string
  expiresInSeconds?: number
  algorithm?: string
  validity: string
  consumption: string
}
export interface StageWorldChangeInfo {
  previousVersion?: number
  newVersion?: number
  driftDetected?: boolean
  description: string
  sensorTrigger?: string
}
export interface StageRevalidationInfo {
  status: string
  expectedHash?: string
  actualHash?: string
  versionMatch?: boolean
  barriersChecked?: number
}
export interface StageExecutionInfo {
  status: string
  actuatorId: string
  commandedAngle?: number
  faultInjected?: string
  busVoltageV?: number
  ticketValidity: string
  ticketConsumption: string
}
export interface StageVerificationInfo {
  status: string
  isVerified: boolean
  limitSwitchReadback?: string
  commandedState?: string
  sensorContradiction?: boolean
}
export interface StageRecoveryInfo {
  failureDetection: string
  containment: string
  quarantine: string
  proposal: string
  execution: string
  reportedOutcome: string
  componentStatus: string
  finalVerification: string
  status: string
  quarantinedValve?: string
  recoveryPath?: string
  isPostRecoveryVerified: boolean
  disclosureNotice?: string
}
export interface PresentationFrame {
  scenarioId: string
  stageIndex: number
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
  outcome: PresentationOutcome
  proposal?: StageProposalInfo
  policy?: StagePolicyInfo
  authorization?: StageAuthorizationInfo
  worldChange?: StageWorldChangeInfo
  revalidation?: StageRevalidationInfo
  execution?: StageExecutionInfo
  verification?: StageVerificationInfo
  recovery?: StageRecoveryInfo
  plantState: PresentationPlantState
  sourceSnapshotPath: string
  cameraPreset: 'full' | 'valve_b' | 'safety_zone' | 'actuator' | 'recovery'
  provenanceMode: ExecutionMode
  originalSourceMode: string
  inferenceProvider: string
  inferenceLabel: string
  physicalBackend: string
  recordHash?: string
  timestamp?: number
  evidenceTimestamp?: number
  sourcePaths: string[]
  evidenceIssues: string[]
}
export interface PresentationTimeline {
  scenarioId: string
  scenarioTitle: string
  overallOutcome: PresentationOutcome
  frames: PresentationFrame[]
}
