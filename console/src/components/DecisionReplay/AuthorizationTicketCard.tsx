import React from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { KeyRound, ShieldAlert, CheckCircle2, Clock, Hash, Lock } from 'lucide-react'
import { AuthorizationTicket } from '../../types'

interface AuthorizationTicketCardProps {
  ticket?: AuthorizationTicket
  isInvalidated?: boolean
  invalidationReason?: string
  currentStage: number
  reducedMotion: boolean
}

export const AuthorizationTicketCard: React.FC<AuthorizationTicketCardProps> = ({
  ticket,
  isInvalidated = false,
  invalidationReason,
  currentStage,
  reducedMotion,
}) => {
  if (!ticket && currentStage < 4) {
    return (
      <div className="console-card">
        <div className="console-card-header">
          <span className="console-card-title">
            <KeyRound size={14} />
            <span>Cryptographic Authorization Ticket</span>
          </span>
          <span className="status-badge offline-replay">PENDING</span>
        </div>
        <div className="console-card-body" style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
          Ticket will be minted by SafetyEnclave after PolicyEngine ALLOW verdict.
        </div>
      </div>
    )
  }

  const effectiveTicket = ticket || {
    ticket_id: 'AT_7b19a08e1c4b',
    action_type: 'CLOSE_VALVE',
    target: 'valve_b',
    issued_at: Date.now() / 1000,
    expires_at: Date.now() / 1000 + 10.0,
    world_state_version: 1,
    world_state_hash: '9f83ac027b14d89a26ce4018274a1c5d9843bf029e',
    policy_version: '1.0.0',
    constraint_set_hash: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e464',
    evidence_context_hash: '7c4091a1820b411d95447a06c28f11b238e9a263d',
    nonce: 'n_a07b81c2',
  }

  // Animation variants
  const badgeVariants = {
    valid: { scale: 1, backgroundColor: 'rgba(16, 185, 129, 0.15)', borderColor: '#059669', color: '#10b981' },
    invalidated: { scale: [1, 1.08, 1], backgroundColor: 'rgba(239, 68, 68, 0.15)', borderColor: '#dc2626', color: '#ef4444' },
  }

  return (
    <div className="console-card">
      <div className="console-card-header">
        <span className="console-card-title">
          <KeyRound size={14} />
          <span>Safety Enclave Authorization Ticket</span>
        </span>

        <motion.div
          animate={isInvalidated ? 'invalidated' : 'valid'}
          variants={reducedMotion ? {} : badgeVariants}
          transition={{ duration: 0.3 }}
          className="status-badge"
          style={{
            border: '1px solid',
            fontWeight: 700,
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {isInvalidated ? (
            <>
              <ShieldAlert size={12} />
              <span>INVALIDATED</span>
            </>
          ) : (
            <>
              <CheckCircle2 size={12} />
              <span>VALID (SINGLE-USE)</span>
            </>
          )}
        </motion.div>
      </div>

      <div className="console-card-body">
        <div className="ticket-card" style={{ borderLeftColor: isInvalidated ? 'var(--status-deny)' : 'var(--status-allow)' }}>
          <div className="ticket-header">
            <div>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Authorization Credential ID
              </div>
              <div className="ticket-id">{effectiveTicket.ticket_id}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Authority
              </div>
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                HMAC-SHA256 (Enclave)
              </div>
            </div>
          </div>

          <div className="ticket-grid">
            <div>
              <span className="ticket-field-label">Action / Target</span>
              <div className="ticket-field-value" style={{ fontWeight: 600, color: '#38bdf8' }}>
                {effectiveTicket.action_type} &rarr; {effectiveTicket.target}
              </div>
            </div>

            <div>
              <span className="ticket-field-label">Bound World Version</span>
              <div className="ticket-field-value mono">v{effectiveTicket.world_state_version}</div>
            </div>

            <div>
              <span className="ticket-field-label">World State Hash</span>
              <div className="ticket-field-value mono" title={effectiveTicket.world_state_hash}>
                {effectiveTicket.world_state_hash ? `${effectiveTicket.world_state_hash.slice(0, 16)}...` : 'N/A'}
              </div>
            </div>

            <div>
              <span className="ticket-field-label">Policy Specification</span>
              <div className="ticket-field-value mono">v{effectiveTicket.policy_version}</div>
            </div>

            <div>
              <span className="ticket-field-label">Constraint Set Hash</span>
              <div className="ticket-field-value mono" title={effectiveTicket.constraint_set_hash}>
                {effectiveTicket.constraint_set_hash ? `${effectiveTicket.constraint_set_hash.slice(0, 16)}...` : 'N/A'}
              </div>
            </div>

            <div>
              <span className="ticket-field-label">Evidence Context Hash</span>
              <div className="ticket-field-value mono" title={effectiveTicket.evidence_context_hash}>
                {effectiveTicket.evidence_context_hash ? `${effectiveTicket.evidence_context_hash.slice(0, 16)}...` : 'N/A'}
              </div>
            </div>

            <div>
              <span className="ticket-field-label">Cryptographic Nonce</span>
              <div className="ticket-field-value mono">{effectiveTicket.nonce}</div>
            </div>

            <div>
              <span className="ticket-field-label">Single-Use Expiration</span>
              <div className="ticket-field-value mono">
                {effectiveTicket.expires_at ? `${effectiveTicket.expires_at.toFixed(2)}s (10.0s TTL)` : '10.0s'}
              </div>
            </div>
          </div>

          {/* If invalidated, show reason */}
          <AnimatePresence>
            {isInvalidated && (
              <motion.div
                initial={reducedMotion ? {} : { opacity: 0, height: 0 }}
                animate={reducedMotion ? {} : { opacity: 1, height: 'auto' }}
                exit={reducedMotion ? {} : { opacity: 0, height: 0 }}
                style={{
                  marginTop: '10px',
                  padding: '8px 12px',
                  backgroundColor: 'var(--status-deny-bg)',
                  border: '1px solid var(--status-deny-border)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '11px',
                  color: '#fca5a5',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <ShieldAlert size={14} style={{ flexShrink: 0 }} />
                <span>
                  <strong>Invalidation Cause:</strong> {invalidationReason || 'Execution-Time World State Drift Detected'}
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
