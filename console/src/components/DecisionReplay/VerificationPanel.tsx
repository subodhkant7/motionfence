import React from 'react'
import { CheckCircle2, AlertTriangle, Cpu, Activity } from 'lucide-react'
import { ExecutionResult, VerificationResult } from '../../types'

interface VerificationPanelProps {
  executionResult?: ExecutionResult
  verificationResult?: VerificationResult
  isBlockedBeforeExecution?: boolean
}

export const VerificationPanel: React.FC<VerificationPanelProps> = ({
  executionResult,
  verificationResult,
  isBlockedBeforeExecution = false,
}) => {
  if (isBlockedBeforeExecution) {
    return (
      <div className="console-card">
        <div className="console-card-header">
          <span className="console-card-title">
            <Cpu size={14} />
            <span>Independent Post-Action Verification</span>
          </span>
          <span className="status-badge read-only">NOT REACHED</span>
        </div>
        <div className="console-card-body" style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
          Actuation was safely aborted by execution-time revalidation. Actuator was not commanded, so post-action physical verification was bypassed.
        </div>
      </div>
    )
  }

  const isFailed = verificationResult?.status === 'VERIFICATION_FAILED'
  const isVerified = verificationResult?.status === 'VERIFIED'

  return (
    <div className="console-card">
      <div className="console-card-header">
        <span className="console-card-title">
          <Cpu size={14} />
          <span>Independent Post-Action Physical Verification</span>
        </span>
        <span
          className={`status-badge ${isVerified ? 'operational' : isFailed ? 'status-deny' : 'read-only'}`}
        >
          {isVerified ? 'VERIFIED' : isFailed ? 'VERIFICATION FAILED' : 'PENDING'}
        </span>
      </div>

      <div className="console-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {/* Execution Summary */}
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', backgroundColor: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', fontSize: '12px' }}>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Actuator Action: </span>
            <span className="mono" style={{ color: '#38bdf8' }}>
              {executionResult?.executed_action || 'CLOSE_VALVE'} &rarr; {executionResult?.target || 'valve_b'}
            </span>
          </div>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Electrical Signal: </span>
            <span className="mono" style={{ color: 'var(--status-allow)' }}>ENERGIZED (24VDC)</span>
          </div>
        </div>

        {/* State Comparison: Commanded vs Observed */}
        <div>
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px' }}>
            Commanded State vs. Observed Physical Sensor State
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px' }}>
            <div style={{ padding: '12px', backgroundColor: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Commanded Postcondition (Expected)
              </div>
              <div className="mono" style={{ fontSize: '16px', fontWeight: 700, color: 'var(--text-primary)', marginTop: '4px' }}>
                VALVE_B = CLOSED
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                Desired state: Full isolation of leaking coolant manifold.
              </div>
            </div>

            <div style={{ padding: '12px', backgroundColor: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', border: `1px solid ${isFailed ? 'var(--status-deny-border)' : 'var(--status-allow-border)'}` }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Empirical Sensor Postcondition (Observed)
              </div>
              <div className="mono" style={{ fontSize: '16px', fontWeight: 700, color: isFailed ? 'var(--status-deny)' : 'var(--status-allow)', marginTop: '4px' }}>
                {isFailed ? 'VALVE_B = OPEN' : 'VALVE_B = CLOSED'}
              </div>
              <div style={{ fontSize: '11px', color: isFailed ? '#fca5a5' : '#6ee7b7', marginTop: '4px' }}>
                {isFailed
                  ? 'Limit switch indicates mechanical travel mismatch. Stroke uncompleted.'
                  : 'Independent limit switches confirm full physical seat closure.'}
              </div>
            </div>
          </div>
        </div>

        {isFailed && (
          <div style={{ padding: '8px 12px', backgroundColor: 'var(--status-deny-bg)', border: '1px solid var(--status-deny-border)', borderRadius: 'var(--radius-sm)', fontSize: '11px', color: '#fca5a5', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertTriangle size={14} style={{ flexShrink: 0 }} />
            <span>
              <strong>Physical Safety Violation Detected:</strong> Actuator reported signal success but physical state remains unverified. Triggering autonomous containment and component quarantine.
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
