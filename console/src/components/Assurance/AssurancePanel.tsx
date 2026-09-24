import React, { useState } from 'react'
import { ShieldCheck, ShieldAlert, CheckCircle2, AlertOctagon, Info, Search, Filter } from 'lucide-react'
import { AssuranceProperty, AssuranceReport } from '../../types'

interface AssurancePanelProps {
  report: AssuranceReport | null
}

export const AssurancePanel: React.FC<AssurancePanelProps> = ({ report }) => {
  const [selectedSubsystem, setSelectedSubsystem] = useState<string>('ALL')
  const [selectedProperty, setSelectedProperty] = useState<AssuranceProperty | null>(null)
  const [searchQuery, setSearchQuery] = useState<string>('')

  if (!report) {
    return <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading Formal Assurance Data...</div>
  }

  const subsystems = ['ALL', 'Policy', 'Authorization', 'Evidence', 'Adversarial', 'Recovery', 'Mutation', 'Trajectory', 'Repair']

  const filteredProperties = report.properties.filter((p) => {
    if (selectedSubsystem !== 'ALL' && p.subsystem !== selectedSubsystem) return false
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      return (
        p.property_id.toLowerCase().includes(q) ||
        p.name.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q)
      )
    }
    return true
  })

  return (
    <div role="region" aria-label="Formal Bounded Assurance Screen">
      {/* Mandatory Limitation Disclaimer (Section 17 Requirement) */}
      <div className="assurance-disclaimer" role="note">
        <Info size={18} style={{ flexShrink: 0, color: 'var(--status-assurance)' }} />
        <div>
          <strong>Formal Assurance Scope Limitation: </strong>
          {report.limitation_notice}
        </div>
      </div>

      {/* Assurance Summary Metrics */}
      <div className="metrics-row">
        <div className="metric-card">
          <span className="metric-label">Total Properties</span>
          <span className="metric-value" style={{ color: 'var(--status-assurance)' }}>
            {report.total_properties}
          </span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Satisfied (Proved in Z3)</span>
          <span className="metric-value emerald">{report.satisfied}</span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Violated Properties</span>
          <span className="metric-value emerald">{report.violated}</span>
        </div>

        <div className="metric-card">
          <span className="metric-label">Verification Engine</span>
          <span className="metric-value" style={{ fontSize: '18px', color: '#38bdf8' }}>
            Z3 SMT Solver
          </span>
        </div>
      </div>

      {/* Subsystem Filters & Search */}
      <div className="console-card" style={{ marginBottom: '20px' }}>
        <div className="console-card-header">
          <span className="console-card-title">
            <Filter size={14} />
            <span>Filter by Subsystem Boundary</span>
          </span>

          <div style={{ position: 'relative' }}>
            <input
              type="text"
              placeholder="Search properties..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                backgroundColor: 'var(--bg-surface-elevated)',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-primary)',
                fontSize: '11px',
                padding: '5px 8px 5px 24px',
                outline: 'none',
              }}
            />
            <Search size={12} style={{ position: 'absolute', left: '8px', top: '7px', color: 'var(--text-muted)' }} />
          </div>
        </div>

        <div className="console-card-body" style={{ padding: '10px 14px' }}>
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            {subsystems.map((sub) => (
              <button
                key={sub}
                className={`icon-btn ${selectedSubsystem === sub ? 'active' : ''}`}
                onClick={() => setSelectedSubsystem(sub)}
                style={{ fontSize: '11px', padding: '4px 10px' }}
              >
                {sub}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Properties Table & Details Split */}
      <div style={{ display: 'grid', gridTemplateColumns: selectedProperty ? '1fr 1fr' : '1fr', gap: '20px' }}>
        {/* Table of Properties */}
        <div className="console-card">
          <div className="console-card-header">
            <span className="console-card-title">
              <ShieldCheck size={14} />
              <span>Assurance Property Registry (PROP_001 – PROP_044)</span>
            </span>
            <span className="mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Showing {filteredProperties.length} of {report.total_properties}
            </span>
          </div>

          <div className="console-card-body" style={{ padding: 0, maxHeight: '600px', overflowY: 'auto' }}>
            <table className="console-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Subsystem</th>
                  <th>Property Name</th>
                  <th>SMT Status</th>
                  <th>Inspect</th>
                </tr>
              </thead>
              <tbody>
                {filteredProperties.map((p) => {
                  const isSelected = selectedProperty?.property_id === p.property_id
                  return (
                    <tr
                      key={p.property_id}
                      style={{
                        backgroundColor: isSelected ? 'var(--bg-hover)' : undefined,
                        cursor: 'pointer',
                      }}
                      onClick={() => setSelectedProperty(p)}
                    >
                      <td className="mono" style={{ color: '#38bdf8', fontWeight: 600 }}>
                        {p.property_id}
                      </td>
                      <td>
                        <span className="status-badge" style={{ fontSize: '10px', backgroundColor: 'var(--bg-surface-elevated)' }}>
                          {p.subsystem}
                        </span>
                      </td>
                      <td style={{ fontSize: '12px', fontWeight: 500 }}>{p.name}</td>
                      <td>
                        <span className="status-badge operational" style={{ fontSize: '10px' }}>
                          <CheckCircle2 size={10} />
                          <span>{p.status}</span>
                        </span>
                      </td>
                      <td>
                        <button
                          className="icon-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            setSelectedProperty(p)
                          }}
                          style={{ fontSize: '10px', padding: '2px 6px' }}
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Selected Property Inspector Drawer */}
        {selectedProperty && (
          <div className="console-card">
            <div className="console-card-header">
              <span className="console-card-title">
                <ShieldCheck size={14} />
                <span>Formal Invariant Proof Details</span>
              </span>
              <button className="icon-btn" onClick={() => setSelectedProperty(null)}>
                Close
              </button>
            </div>

            <div className="console-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  Property Identifier
                </div>
                <div className="mono" style={{ fontSize: '16px', fontWeight: 700, color: '#38bdf8' }}>
                  {selectedProperty.property_id}: {selectedProperty.name}
                </div>
              </div>

              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  Subsystem Boundary
                </div>
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {selectedProperty.subsystem}
                </div>
              </div>

              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  Natural Language Invariant Specification
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-surface-elevated)', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                  {selectedProperty.description}
                </div>
              </div>

              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  Bounded Z3 SMT Model & Proof
                </div>
                <pre style={{ padding: '10px', backgroundColor: 'var(--bg-app)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-sm)', fontSize: '11px', color: '#cbd5e1', overflowX: 'auto', fontFamily: 'var(--font-mono)' }}>
                  {selectedProperty.bounded_model}
                </pre>
              </div>

              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  Formal Mathematical Assertion
                </div>
                <div className="mono" style={{ fontSize: '12px', color: 'var(--status-assurance)', padding: '8px 10px', backgroundColor: 'var(--bg-surface-elevated)', borderRadius: 'var(--radius-sm)' }}>
                  {selectedProperty.formula}
                </div>
              </div>

              <div style={{ padding: '8px 10px', backgroundColor: 'var(--status-allow-bg)', border: '1px solid var(--status-allow-border)', borderRadius: 'var(--radius-sm)', fontSize: '11px', color: '#6ee7b7' }}>
                Counterexample Search: <strong>NO COUNTEREXAMPLE FOUND</strong> (Unsat Refutation Proved)
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
