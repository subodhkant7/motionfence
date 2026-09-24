import React from 'react'
import { Wrench, ShieldAlert, CheckCircle2, XCircle, AlertCircle, Lock } from 'lucide-react'
import { RepairProposal } from '../../types'

interface RepairProposalsViewProps {
  repairs: RepairProposal[]
}

export const RepairProposalsView: React.FC<RepairProposalsViewProps> = ({ repairs }) => {
  return (
    <div className="console-card" style={{ marginTop: '20px' }}>
      <div className="console-card-header">
        <span className="console-card-title">
          <Wrench size={14} />
          <span>Non-Authoritative Safe Repair Proposals (Phase 2K Synthesizer)</span>
        </span>
        <span className="status-badge read-only" style={{ fontSize: '10px' }}>
          <Lock size={10} />
          <span>NON-AUTHORITATIVE (PROPOSED ONLY)</span>
        </span>
      </div>

      <div className="console-card-body">
        {/* Architectural Constraint Notice */}
        <div style={{ padding: '8px 12px', backgroundColor: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: 'var(--radius-sm)', fontSize: '11px', color: '#fbbf24', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ShieldAlert size={14} style={{ flexShrink: 0 }} />
          <span>
            <strong>Architectural Safety Invariant:</strong> Repair proposals are advisory recommendations synthesized in a detached sandbox. They carry ZERO production authority. There is strictly NO automatic application or 'Apply to Production' mechanism.
          </span>
        </div>

        {repairs.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
            No candidate repairs generated.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '12px' }}>
            {repairs.map((rep, idx) => {
              const isValidated = rep.repair_status === 'VALIDATED'
              const isInconclusive = rep.repair_status === 'INCONCLUSIVE'
              const isRejected = rep.repair_status === 'REJECTED'

              let badgeColor = 'var(--status-allow)'
              let badgeBg = 'var(--status-allow-bg)'
              let badgeBorder = 'var(--status-allow-border)'
              if (isInconclusive) {
                badgeColor = '#fbbf24'
                badgeBg = 'rgba(245, 158, 11, 0.12)'
                badgeBorder = 'var(--status-warning-border)'
              } else if (isRejected) {
                badgeColor = 'var(--status-deny)'
                badgeBg = 'var(--status-deny-bg)'
                badgeBorder = 'var(--status-deny-border)'
              }

              return (
                <div
                  key={idx}
                  style={{
                    backgroundColor: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '12px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span className="mono" style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 600 }}>
                      Target: {rep.target_field}
                    </span>
                    <span
                      style={{
                        fontSize: '10px',
                        fontWeight: 700,
                        color: badgeColor,
                        backgroundColor: badgeBg,
                        border: `1px solid ${badgeBorder}`,
                        padding: '2px 6px',
                        borderRadius: 'var(--radius-sm)',
                      }}
                    >
                      {rep.repair_status} {isInconclusive ? '(FAIL-CLOSED)' : ''}
                    </span>
                  </div>

                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                    Triggering Regression: <strong className="mono">{rep.regression_type}</strong>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', fontSize: '11px' }}>
                    <div style={{ padding: '6px 8px', backgroundColor: 'var(--bg-app)', borderRadius: 'var(--radius-sm)' }}>
                      <span style={{ color: 'var(--text-muted)' }}>Failing: </span>
                      <span className="mono" style={{ color: 'var(--status-deny)' }}>{JSON.stringify(rep.after_value)}</span>
                    </div>
                    <div style={{ padding: '6px 8px', backgroundColor: 'var(--bg-app)', borderRadius: 'var(--radius-sm)' }}>
                      <span style={{ color: 'var(--text-muted)' }}>Proposed Patch: </span>
                      <span className="mono" style={{ color: 'var(--status-allow)' }}>{JSON.stringify(rep.before_value)}</span>
                    </div>
                  </div>

                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    Rationale: {rep.safety_rationale}
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)', paddingTop: '6px', marginTop: '4px' }}>
                    <span>Status: <strong>PROPOSED</strong> (not applied)</span>
                    <span>Monotonicity: {isValidated ? 'VERIFIED' : 'REJECTED'}</span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
