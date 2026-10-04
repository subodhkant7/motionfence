import React, { useState, useEffect } from 'react'
import { Header } from './components/Header'
import { DecisionReplay } from './components/DecisionReplay/DecisionReplay'
import { PolicyFirewall } from './components/PolicyFirewall/PolicyFirewall'
import { TrajectoryViewer } from './components/Trajectories/TrajectoryViewer'
import { AssurancePanel } from './components/Assurance/AssurancePanel'
import {
  AssuranceReport,
  DynamicTrajectoryData,
  FirewallReport,
  RepairProposal,
  ScenarioData,
  ScenarioMeta,
  ViewMode,
} from './types'
import { api } from './services/api'

export const App: React.FC = () => {
  const [currentView, setCurrentView] = useState<ViewMode>('replay')
  const [isLiveBackend, setIsLiveBackend] = useState<boolean>(false)
  const [reducedMotion, setReducedMotion] = useState<boolean>(false)

  // Scenarios state
  const [scenarios, setScenarios] = useState<ScenarioMeta[]>([])
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('scenario_a')
  const [scenarioData, setScenarioData] = useState<ScenarioData | null>(null)

  // Other views data
  const [firewallReport, setFirewallReport] = useState<FirewallReport | null>(null)
  const [repairs, setRepairs] = useState<RepairProposal[]>([])
  const [trajectories, setTrajectories] = useState<DynamicTrajectoryData[]>([])
  const [assuranceReport, setAssuranceReport] = useState<AssuranceReport | null>(null)

  // Initialize data on mount
  useEffect(() => {
    async function init() {
      const status = await api.checkBackendStatus()
      setIsLiveBackend(status.isLive)

      const scList = await api.getScenarios()
      setScenarios(scList)
      if (scList.length > 0) {
        setSelectedScenarioId(scList[0].id)
      }

      const fw = await api.getFirewallReport()
      setFirewallReport(fw)

      const reps = await api.getRepairs()
      setRepairs(reps)

      const trajs = await api.getTrajectories()
      setTrajectories(trajs)

      const ass = await api.getAssuranceReport()
      setAssuranceReport(ass)
    }

    init()
  }, [])

  // Load scenario data on scenario change
  useEffect(() => {
    async function loadScenario() {
      if (selectedScenarioId) {
        const data = await api.getScenarioData(selectedScenarioId)
        setScenarioData(data)
      }
    }
    loadScenario()
  }, [selectedScenarioId])

  // Reduced motion toggle effect
  const handleToggleReducedMotion = () => {
    setReducedMotion((prev) => {
      const next = !prev
      if (next) {
        document.body.classList.add('reduced-motion')
      } else {
        document.body.classList.remove('reduced-motion')
      }
      return next
    })
  }

  return (
    <div className="app-container">
      <Header
        currentView={currentView}
        onViewChange={setCurrentView}
        isLive={isLiveBackend}
        executionMode={scenarioData?.execution_mode || (isLiveBackend ? 'LIVE' : 'REPLAY')}
        reducedMotion={reducedMotion}
        onToggleReducedMotion={handleToggleReducedMotion}
      />

      <main className="main-content" role="main">
        {currentView === 'replay' && (
          <DecisionReplay
            scenarios={scenarios}
            selectedScenarioId={selectedScenarioId}
            onSelectScenario={setSelectedScenarioId}
            scenarioData={scenarioData}
            onScenarioDataLoaded={setScenarioData}
            reducedMotion={reducedMotion}
          />
        )}

        {currentView === 'firewall' && (
          <PolicyFirewall
            report={firewallReport}
            repairs={repairs}
            reducedMotion={reducedMotion}
          />
        )}

        {currentView === 'trajectories' && (
          <TrajectoryViewer
            trajectories={trajectories}
            reducedMotion={reducedMotion}
          />
        )}

        {currentView === 'assurance' && (
          <AssurancePanel report={assuranceReport} />
        )}
      </main>
    </div>
  )
}

export default App
