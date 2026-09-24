import React from 'react'
import { motion } from 'framer-motion'
import { Check, X, AlertTriangle, ArrowRight } from 'lucide-react'

export interface TimelineStage {
  index: number
  key: string
  label: string
  subtitle: string
  status: 'passed' | 'blocked' | 'warning' | 'active' | 'pending'
}

interface TimelineProps {
  stages: TimelineStage[]
  activeStageIndex: number
  onSelectStage: (index: number) => void
  reducedMotion: boolean
}

export const Timeline: React.FC<TimelineProps> = ({
  stages,
  activeStageIndex,
  onSelectStage,
  reducedMotion,
}) => {
  return (
    <div className="timeline-track-container" role="region" aria-label="10-Stage Lifecycle Pipeline">
      <div className="timeline-track">
        {stages.map((stage, idx) => {
          const isActive = idx === activeStageIndex
          const isPast = idx < activeStageIndex
          const isPending = idx > activeStageIndex

          let statusClass = 'pending'
          let statusText = 'WAIT'
          if (stage.status === 'blocked') {
            statusClass = 'blocked'
            statusText = 'BLOCKED'
          } else if (stage.status === 'warning') {
            statusClass = 'warning'
            statusText = 'FAILED'
          } else if (stage.status === 'passed' || isPast) {
            statusClass = 'pass'
            statusText = 'PASSED'
          } else if (isActive) {
            statusClass = 'pass'
            statusText = 'ACTIVE'
          }

          return (
            <React.Fragment key={stage.key}>
              <motion.div
                className={`timeline-node ${isActive ? 'active' : ''} ${isPast ? 'completed' : ''}`}
                onClick={() => onSelectStage(idx)}
                whileHover={reducedMotion ? {} : { scale: 1.02 }}
                whileTap={reducedMotion ? {} : { scale: 0.98 }}
                role="button"
                tabIndex={0}
                aria-pressed={isActive}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    onSelectStage(idx)
                  }
                }}
              >
                <span className="timeline-node-step">Stage 0{idx + 1}</span>
                <span className="timeline-node-name">{stage.label}</span>
                <span className={`timeline-node-status ${statusClass}`}>
                  {statusText}
                </span>
                <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                  {stage.subtitle}
                </span>
              </motion.div>

              {idx < stages.length - 1 && (
                <div
                  className="timeline-connector"
                  style={{
                    backgroundColor: isPast ? 'var(--status-allow)' : 'var(--border-default)',
                  }}
                />
              )}
            </React.Fragment>
          )
        })}
      </div>
    </div>
  )
}
