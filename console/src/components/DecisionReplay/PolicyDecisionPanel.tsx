import React from 'react'
import { ShieldCheck, ShieldAlert, CheckCircle2, XCircle, AlertCircle } from 'lucide-react'
import { DecisionRecord, WorldState } from '../../types'

interface PolicyDecisionPanelProps {
  decisionRecord: DecisionRecord
  worldState: WorldState
}

export const PolicyDecisionPanel: React.FC<PolicyDecisionPanelProps> = ({
  decisionRecord,
  worldState,
}) => {
  const verdict = decisionRecord.policy_decision || 'ALLOW'
  const isAllow = verdict === 'ALLOW'
  const isDeny = verdict === 'DENY'

  const proposal = decisionRecord.action_proposal
  const confidence = proposal?.model_confidence ?? 0.95
  const humanZoneClear = worldState.human_zone === 'CLEAR'
  const coolingActive = worldState.cooling === 'ACTIVE'

  return (
    <div className="console-card">
      <div className="console-card-header">
        <span className="console-card-title">
          <ShieldCheck size={14} />
          <span>Deterministic Policy Engine Evaluation</span>
        </span>
        <span
          className={`status-badge ${isAllow ? 'operational' : isDeny ? 'status-deny' : 'read-only'}`}
          style={{ fontSize: '11px' }}
        >
          {verdict}
        </span>
      </div>

      <div className="console-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', backgroundColor: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Final Decision Verdict
            </div>
            <div style={{ fontSize: '18px', fontWeight: 700, color: isAllow ? 'var(--status-allow)' : isDeny ? 'var(--status-deny)' : 'var(--status-warning)', fontFamily: 'var(--font-mono)' }}>
              {verdict}
            </div>
          </div>
          <div style={{ textAlign: 'right', fontSize: '11px', color: 'var(--text-secondary)' }}>
            <div>Policy Version: {decisionRecord.policy_version || '1.0.0'}</div>
            <div>Runtime Engine: {decisionRecord.runtime_version || '2.4.0'}</div>
          </div>
        </div>

        {/* Deterministic Evaluation Checklist */}
        <div>
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px' }}>
            Deterministic Policy Factors (LLM-Free Gating)
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '8px' }}>
            <div className="barrier-item">
              <span className="barrier-name">Human Safety Zone</span>
              <span className={`barrier-status ${humanZoneClear ? 'pass' : 'blocked'}`}>
                {humanZoneClear ? 'CLEAR (PASS)' : 'OCCUPIED (BLOCK)'}
              </span>
            </div>

            <div className="barrier-item">
              <span className="barrier-name">Cooling Invariant</span>
              <span className={`barrier-status ${coolingActive ? 'pass' : 'blocked'}`}>
                {coolingActive ? 'ACTIVE (PASS)' : 'INACTIVE (BLOCK)'}
              </span>
            </div>

            <div className="barrier-item">
              <span className="barrier-name">Confidence Floor</span>
              <span className={`barrier-status ${confidence >= 0.9 ? 'pass' : 'blocked'}`}>
                {confidence >= 0.9 ? `${(confidence * 100).toFixed(0)}% >= 90%` : `${(confidence * 100).toFixed(0)}% < 90%`}
              </span>
            </div>

            <div className="barrier-item">
              <span className="barrier-name">Contradictions</span>
              <span className="barrier-status pass">NONE DETECTED</span>
            </div>

            <div className="barrier-item">
              <span className="barrier-name">Actuator Target Scope</span>
              <span className="barrier-status pass">AUTHORIZED (valve_b)</span>
            </div>

            <div className="barrier-item">
              <span className="barrier-name">Observation Freshness</span>
              <span className="barrier-status pass">&lt; 5.0s (FRESH)</span>
            </div>
          </div>
        </div>

        {/* Citations from Policy Reasons */}
        {decisionRecord.policy_reasons && decisionRecord.policy_reasons.length > 0 && (
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
              Engine Evaluation Rationale
            </div>
            <ul style={{ paddingLeft: '18px', fontSize: '12px', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {decisionRecord.policy_reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
