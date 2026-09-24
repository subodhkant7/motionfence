import React from 'react'
import { ShieldCheck, ShieldAlert, CheckCircle2, XCircle } from 'lucide-react'

interface RevalidationBarriersProps {
  isBlocked?: boolean
  failedBarrier?: string
  status?: string
}

export const RevalidationBarriers: React.FC<RevalidationBarriersProps> = ({
  isBlocked = false,
  failedBarrier = 'world version',
  status = 'VALID',
}) => {
  const barriers = [
    { id: 'expiry', name: '1. Ticket Expiry', isPass: true, desc: 'Current time < Ticket expiration' },
    { id: 'action', name: '2. Action Type Match', isPass: true, desc: 'Proposal action == Ticket action' },
    { id: 'target', name: '3. Target Match', isPass: true, desc: 'Proposal target == Ticket target' },
    {
      id: 'world_version',
      name: '4. World Version Match',
      isPass: !isBlocked || failedBarrier !== 'world version',
      desc: isBlocked ? 'Issuance v1 ≠ Execution v2 (DRIFT)' : 'Issuance v1 == Execution v1',
    },
    {
      id: 'world_hash',
      name: '5. World State Hash',
      isPass: !isBlocked,
      desc: isBlocked ? 'Physical state mutated post-authorization' : 'Cryptographic hash identical',
    },
    { id: 'policy_version', name: '6. Policy Version Match', isPass: true, desc: 'Active policy version matches ticket' },
    { id: 'constraint_hash', name: '7. Constraint Set Hash', isPass: true, desc: 'Active safety constraints unaltered' },
    { id: 'evidence_hash', name: '8. Evidence Context Hash', isPass: true, desc: 'Empirical sensor evidence unmodified' },
    { id: 'context_hash', name: '9. Full Context Hash', isPass: !isBlocked, desc: isBlocked ? 'Context drift detected' : 'Context SHA-256 verified' },
  ]

  return (
    <div className="console-card">
      <div className="console-card-header">
        <span className="console-card-title">
          <ShieldAlert size={14} />
          <span>Execution-Time Revalidation (TOCTOU Defense)</span>
        </span>
        <span
          className={`status-badge ${isBlocked ? 'status-deny' : 'operational'}`}
          style={{ fontSize: '11px' }}
        >
          {isBlocked ? 'BLOCKED BEFORE EXECUTION' : 'ALL BARRIERS PASSED'}
        </span>
      </div>

      <div className="console-card-body">
        <div style={{ marginBottom: '12px', fontSize: '12px', color: isBlocked ? '#fca5a5' : '#6ee7b7', backgroundColor: isBlocked ? 'var(--status-deny-bg)' : 'var(--status-allow-bg)', border: `1px solid ${isBlocked ? 'var(--status-deny-border)' : 'var(--status-allow-border)'}`, padding: '8px 12px', borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          {isBlocked ? <XCircle size={16} /> : <CheckCircle2 size={16} />}
          <span>
            {isBlocked
              ? 'SAFETY INTERCEPTION: World state modified between authorization and actuation. Actuator was NEVER reached.'
              : 'VERIFIED: All 9 cryptographic and environmental barriers passed. Actuator execution authorized.'}
          </span>
        </div>

        <div className="barriers-grid">
          {barriers.map((b) => (
            <div
              key={b.id}
              className="barrier-item"
              style={{
                borderLeftColor: b.isPass ? 'var(--status-allow)' : 'var(--status-deny)',
                borderLeftWidth: '3px',
              }}
            >
              <div>
                <div className="barrier-name">{b.name}</div>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{b.desc}</div>
              </div>
              <span className={`barrier-status ${b.isPass ? 'pass' : 'blocked'}`}>
                {b.isPass ? 'PASS' : 'FAIL'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
