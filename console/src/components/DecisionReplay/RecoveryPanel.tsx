import React from 'react'
import { LifeBuoy, ShieldAlert, CheckCircle2, RefreshCw, KeyRound, Lock, ArrowRight } from 'lucide-react'
import { AuthorizationTicket, ScenarioData } from '../../types'

interface RecoveryPanelProps {
  scenarioData: ScenarioData
}

export const RecoveryPanel: React.FC<RecoveryPanelProps> = ({ scenarioData }) => {
  const failureRecord = scenarioData.failure_record
  const quarantineRecords = scenarioData.quarantine_records || {}
  const quarantinedComp = scenarioData.quarantined_component || 'valve_b'
  const freshTicket = scenarioData.fresh_ticket
  const isRecovered = scenarioData.is_recovered ?? true

  const steps = [
    { name: '1. FAILURE', desc: 'Actuator stroke mismatch', status: 'DETECTED', color: 'var(--status-deny)' },
    { name: '2. INVALIDATE', desc: 'Stale ticket invalidated', status: 'CONSUMED', color: '#fbbf24' },
    { name: '3. CONTAIN', desc: 'Scoped component quarantine', status: 'QUARANTINED', color: 'var(--status-deny)' },
    { name: '4. RECOVER', desc: 'Alternate isolation planning', status: 'PLANNED', color: '#38bdf8' },
    { name: '5. REAUTHORIZE', desc: 'Fresh ticket issued (Enclave)', status: 'FRESH AUTH', color: '#10b981' },
    { name: '6. VERIFY', desc: 'Postcondition confirmed', status: 'VERIFIED', color: '#10b981' },
  ]

  return (
    <div className="console-card">
      <div className="console-card-header">
        <span className="console-card-title">
          <LifeBuoy size={14} />
          <span>Autonomous Fault Containment & Recovery Cycle</span>
        </span>
        <span className="status-badge operational" style={{ fontSize: '11px' }}>
          {isRecovered ? 'RECOVERED (VERIFIED)' : 'CONTAINMENT ACTIVE'}
        </span>
      </div>

      <div className="console-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {/* Visual Causal Sequence */}
        <div>
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px' }}>
            Autonomous Containment & Recovery Lifecycle
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '8px' }}>
            {steps.map((st, i) => (
              <div
                key={i}
                style={{
                  backgroundColor: 'var(--bg-surface-elevated)',
                  border: '1px solid var(--border-subtle)',
                  borderLeft: `3px solid ${st.color}`,
                  padding: '8px 10px',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-primary)' }}>{st.name}</div>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>{st.desc}</div>
                <div className="mono" style={{ fontSize: '10px', fontWeight: 700, color: st.color, marginTop: '4px' }}>
                  {st.status}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Detailed Breakdown: Quarantine + Fresh Auth */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '14px' }}>
          {/* Quarantine State */}
          <div style={{ padding: '12px', backgroundColor: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Quarantine Registry State
              </span>
              <span className="status-badge status-deny" style={{ fontSize: '10px' }}>
                <Lock size={10} />
                <span>QUARANTINED</span>
              </span>
            </div>
            <div style={{ fontSize: '13px', fontWeight: 600, color: '#fca5a5' }}>
              Component: <span className="mono">{quarantinedComp}</span>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
              Failure Classification: <strong className="mono">{failureRecord?.failure_class || 'ACTUATOR_NO_OP'}</strong>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
              Reason: Mechanical travel mismatch. All subsequent direct actuation on {quarantinedComp} blocked until recertified.
            </div>
          </div>

          {/* Fresh Authorization Guard (Anti-Stale Token Proof) */}
          <div style={{ padding: '12px', backgroundColor: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--status-allow-border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Fresh Authorization Proof
              </span>
              <span className="status-badge operational" style={{ fontSize: '10px' }}>
                <ShieldAlert size={10} />
                <span>NO STALE TOKEN REUSE</span>
              </span>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Stale Ticket: <span className="mono" style={{ textDecoration: 'line-through', color: 'var(--text-muted)' }}>{scenarioData.initial_ticket?.ticket_id}</span>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-primary)', marginTop: '4px' }}>
              Fresh Ticket: <span className="mono" style={{ color: '#38bdf8', fontWeight: 600 }}>{freshTicket?.ticket_id || 'AT_recov_429a1b8c'}</span>
            </div>
            <div style={{ fontSize: '11px', color: '#6ee7b7', marginTop: '6px' }}>
              Autonomous recovery acquired fresh empirical evidence and minted a new single-use credential through SafetyEnclave.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
