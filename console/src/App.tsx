import React, { useState, useEffect } from 'react'
import { Header } from './components/Header'
import { DecisionReplay } from './components/DecisionReplay/DecisionReplay'
import { PolicyFirewall } from './components/PolicyFirewall/PolicyFirewall'
import { TrajectoryViewer } from './components/Trajectories/TrajectoryViewer'
import { AssurancePanel } from './components/Assurance/AssurancePanel'
import { DemoDirector } from './components/Director/DemoDirector'
import { SafetyLabView } from './components/SafetyLab/SafetyLabView'
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

function isDirectorRequested(): boolean {
  if (typeof window === 'undefined') return false
  const params = new URLSearchParams(window.location.search)
  return params.get('director') === '1' || params.get('director') === 'true' || params.get('mode') === 'director'
}

function isSafetyLabRequested(): boolean {
  if (typeof window === 'undefined') return false
  const params = new URLSearchParams(window.location.search)
  const pathname = window.location.pathname.toLowerCase()
  return (
    params.get('lab') === '1' ||
    params.get('lab') === 'true' ||
    params.get('safetylab') === '1' ||
    params.get('mode') === 'lab' ||
    params.get('mode') === 'safety-lab' ||
    pathname.startsWith('/safety-lab')
  )
}

export const App: React.FC = () => {
  const [currentView, setCurrentView] = useState<ViewMode>('replay')
  const [isLiveBackend, setIsLiveBackend] = useState<boolean>(false)
  const [reducedMotion, setReducedMotion] = useState<boolean>(false)
  const [isDirectorMode, setIsDirectorMode] = useState<boolean>(isDirectorRequested)
  const [isSafetyLabMode, setIsSafetyLabMode] = useState<boolean>(isSafetyLabRequested)

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

  // Listen to browser navigation (back/forward) for director and safety-lab query params
  useEffect(() => {
    const handlePopState = () => {
      setIsDirectorMode(isDirectorRequested())
      setIsSafetyLabMode(isSafetyLabRequested())
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  const handleOpenDirector = () => {
    setIsDirectorMode(true)
    setIsSafetyLabMode(false)
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href)
      url.searchParams.delete('lab')
      url.searchParams.set('director', '1')
      window.history.pushState({}, '', url.toString())
    }
  }

  const handleExitDirector = () => {
    setIsDirectorMode(false)
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href)
      url.searchParams.delete('director')
      url.searchParams.delete('mode')
      const newQuery = url.search ? url.search : ''
      window.history.pushState({}, '', url.pathname + newQuery)
    }
  }

  const handleOpenSafetyLab = () => {
    setIsSafetyLabMode(true)
    setIsDirectorMode(false)
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href)
      url.searchParams.delete('director')
      url.searchParams.set('lab', '1')
      window.history.pushState({}, '', url.toString())
    }
  }

  const handleExitSafetyLab = () => {
    setIsSafetyLabMode(false)
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href)
      url.searchParams.delete('lab')
      url.searchParams.delete('safetylab')
      url.searchParams.delete('mode')
      const newQuery = url.search ? url.search : ''
      window.history.pushState({}, '', url.pathname + newQuery)
    }
  }

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

  // Dedicated Safety Lab Mode
  if (isSafetyLabMode) {
    return (
      <div className="app-container safetylab-mode-active">
        <SafetyLabView
          onExitLab={handleExitSafetyLab}
          reducedMotion={reducedMotion}
          onToggleReducedMotion={handleToggleReducedMotion}
        />
      </div>
    )
  }

  // Dedicated Recording Mode: Demo Director
  if (isDirectorMode) {
    return (
      <div className="app-container director-mode-active">
        <DemoDirector
          scenarios={scenarios}
          onExitDirector={handleExitDirector}
          reducedMotion={reducedMotion}
          onToggleReducedMotion={handleToggleReducedMotion}
          assuranceReport={assuranceReport}
        />
      </div>
    )
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
        onOpenDirector={handleOpenDirector}
        onOpenSafetyLab={handleOpenSafetyLab}
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

