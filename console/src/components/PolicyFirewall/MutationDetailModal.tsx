import React from 'react'
import { X, ShieldAlert, CheckCircle2, AlertOctagon, Terminal } from 'lucide-react'
import { MutationItem } from '../../types'

interface MutationDetailModalProps {
  mutation: MutationItem
  onClose: () => void
}

export const MutationDetailModal: React.FC<MutationDetailModalProps> = ({ mutation, onClose }) => {
  const mut = mutation.mutation
  const cex = mutation.counterexample
  const isRejected = mutation.firewall_decision === 'REJECT'

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="console-card-header">
          <span className="console-card-title">
            <Terminal size={14} />
            <span>Policy Mutation Attack Drill-Down: {mut.mutation_id}</span>
          </span>
          <button className="icon-btn" onClick={onClose} aria-label="Close Drill-Down">
            <X size={14} />
          </button>
        </div>

        <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Header Summary */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', backgroundColor: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)' }}>
            <div>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Mutation Type
              </div>
              <div className="mono" style={{ fontSize: '14px', fontWeight: 700, color: '#38bdf8' }}>
                {mut.mutation_type}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Firewall Decision
              </div>
              <span className={`status-badge ${isRejected ? 'status-deny' : 'operational'}`}>
                {mutation.firewall_decision} (DETECTED)
              </span>
            </div>
          </div>

          {/* Description */}
          <div style={{ fontSize: '12px', color: 'var(--text-primary)' }}>
            {mut.description}
          </div>

          {/* Before vs After Policy Value */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
              Parameter Modification Diff
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
              <div style={{ padding: '10px', backgroundColor: 'var(--bg-app)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>BASELINE VALUE</div>
                <div className="mono" style={{ fontSize: '12px', color: 'var(--status-allow)', marginTop: '2px' }}>
                  {JSON.stringify(mut.before_value)}
                </div>
              </div>
              <div style={{ padding: '10px', backgroundColor: 'var(--bg-app)', border: '1px solid var(--status-deny-border)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>MUTATED ATTACK VALUE</div>
                <div className="mono" style={{ fontSize: '12px', color: 'var(--status-deny)', marginTop: '2px' }}>
                  {JSON.stringify(mut.after_value)}
                </div>
              </div>
            </div>
          </div>

          {/* Decisions Comparison */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
              Authorization Verdict Shift
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '10px', backgroundColor: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', fontSize: '12px' }}>
              <div>
                Baseline: <span className="mono" style={{ color: 'var(--status-deny)', fontWeight: 700 }}>{cex?.baseline_decision || 'DENY'}</span>
              </div>
              <span style={{ color: 'var(--text-muted)' }}>&rarr;</span>
              <div>
                Mutated: <span className="mono" style={{ color: 'var(--status-allow)', fontWeight: 700 }}>{cex?.mutated_decision || 'ALLOW'}</span>
              </div>
              <span style={{ color: 'var(--text-muted)' }}>•</span>
              <div>
                Regression: <span className="mono" style={{ color: '#fbbf24', fontWeight: 600 }}>{mutation.regression_type}</span>
              </div>
            </div>
          </div>

          {/* Minimized Counterexample Scenario */}
          {cex && (
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                Minimized Causal Counterexample Scenario
              </div>
              <pre style={{ padding: '10px', backgroundColor: 'var(--bg-app)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-sm)', fontSize: '11px', color: '#cbd5e1', overflowX: 'auto', fontFamily: 'var(--font-mono)' }}>
                {JSON.stringify(cex.minimized_scenario, null, 2)}
              </pre>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                Explanation: {cex.explanation}
              </div>
            </div>
          )}

          {/* Interaction Type (Phase 2K) */}
          {mutation.interaction_type && (
            <div style={{ padding: '8px 10px', backgroundColor: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', fontSize: '11px', display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>Combinatorial Interaction Type:</span>
              <span className="mono" style={{ color: '#38bdf8', fontWeight: 700 }}>
                {mutation.interaction_type}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
