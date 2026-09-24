import React from 'react'
import { CheckCircle2, AlertTriangle, ShieldCheck, Database, FileText } from 'lucide-react'
import { EvidenceItem } from '../../types'

interface EvidenceInspectorProps {
  evidenceList: EvidenceItem[]
}

export const EvidenceInspector: React.FC<EvidenceInspectorProps> = ({ evidenceList }) => {
  return (
    <div className="console-card">
      <div className="console-card-header">
        <span className="console-card-title">
          <Database size={14} />
          <span>Active Evidence & Provenance</span>
        </span>
        <span className="mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          {evidenceList.length} ITEMS REGISTERED
        </span>
      </div>

      <div className="console-card-body">
        {/* Core Product Thesis Distinction Banner */}
        <div className="distinction-banner" role="region" aria-label="Evidence Epistemic Distinction">
          <div className="distinction-chain">
            <span className="chain-item">SOURCE EXISTS</span>
            <span className="chain-separator">≠</span>
            <span className="chain-item">SOURCE TRUSTWORTHY</span>
            <span className="chain-separator">≠</span>
            <span className="chain-item highlight">CLAIM SUPPORTED</span>
            <span className="chain-separator">≠</span>
            <span className="chain-item">AUTHORIZATION SUFFICIENT</span>
          </div>
        </div>

        {evidenceList.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
            No empirical evidence registered for this decision cycle.
          </p>
        ) : (
          <div className="evidence-card-list">
            {evidenceList.map((item, idx) => (
              <div key={item.id || idx} className="evidence-card">
                <div className="evidence-card-header">
                  <span className="evidence-id">{item.id}</span>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <span className="status-badge operational" style={{ fontSize: '10px' }}>
                      <CheckCircle2 size={10} />
                      <span>{item.source.toUpperCase()}</span>
                    </span>
                    <span
                      className="status-badge read-only"
                      style={{ fontSize: '10px' }}
                      title={`Target: ${item.target}`}
                    >
                      {item.target}
                    </span>
                  </div>
                </div>

                <div className="evidence-meta-row">
                  <span>
                    Confidence: <strong>{(item.confidence * 100).toFixed(0)}%</strong>
                  </span>
                  <span>•</span>
                  <span>Provenance: {item.provenance}</span>
                  <span>•</span>
                  <span>Trust: {item.trust_status || 'VERIFIED_FIRST_PARTY'}</span>
                </div>

                <div className="evidence-obs">
                  <strong>Observation:</strong> {JSON.stringify(item.observation)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
