import React, { useState, useEffect, useCallback } from 'react'
import { Header } from './components/Header'
import { DecisionReplay } from './components/DecisionReplay/DecisionReplay'
import { PolicyFirewall } from './components/PolicyFirewall/PolicyFirewall'
import { TrajectoryViewer } from './components/Trajectories/TrajectoryViewer'
import { AssurancePanel } from './components/Assurance/AssurancePanel'
import { DemoDirector } from './components/Director/DemoDirector'
import { SafetyLabView } from './components/SafetyLab/SafetyLabView'
import { LandingPage } from './components/Landing/LandingPage'
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

export type AppRoute = 'home' | 'demo' | 'safety-lab' | 'console' | 'architecture'

export function resolveCurrentRoute(): AppRoute {
  if (typeof window === 'undefined') return 'home'
  const params = new URLSearchParams(window.location.search)
  const pathname = (window.location.pathname || '').toLowerCase().replace(/\/$/, '')

  // Query parameter backward-compatibility overrides
  if (params.get('director') === '1' || params.get('director') === 'true' || params.get('mode') === 'director') {
    return 'demo'
  }
  if (
    params.get('lab') === '1' ||
    params.get('lab') === 'true' ||
    params.get('safetylab') === '1' ||
    params.get('mode') === 'lab' ||
    params.get('mode') === 'safety-lab'
  ) {
    return 'safety-lab'
  }
  if (
    params.get('console') === '1' ||
    params.get('mode') === 'console' ||
    params.get('view') === 'replay' ||
    params.get('view') === 'firewall' ||
    params.get('view') === 'trajectories' ||
    params.get('view') === 'assurance'
  ) {
    return 'console'
  }
  if (params.get('arch') === '1' || params.get('mode') === 'architecture') {
    return 'architecture'
  }

  // Pathname routing
  if (pathname === '/demo') return 'demo'
  if (pathname === '/safety-lab' || pathname === '/safetylab') return 'safety-lab'
  if (pathname === '/console' || pathname === '/judge') return 'console'
  if (pathname === '/architecture') return 'architecture'

  return 'home'
}

export const App: React.FC = () => {
  const [currentRoute, setCurrentRoute] = useState<AppRoute>(resolveCurrentRoute)
  const [currentView, setCurrentView] = useState<ViewMode>('replay')
  const [isLiveBackend, setIsLiveBackend] = useState<boolean>(false)
  const [reducedMotion, setReducedMotion] = useState<boolean>(false)

  // Scenarios state for Console and Director
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

  // Listen to browser navigation (back/forward)
  useEffect(() => {
    const handlePopState = () => {
      setCurrentRoute(resolveCurrentRoute())
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  const handleNavigate = useCallback((route: AppRoute) => {
    setCurrentRoute(route)
    if (typeof window !== 'undefined') {
      let path = '/'
      if (route === 'demo') path = '/demo'
      else if (route === 'safety-lab') path = '/safety-lab'
      else if (route === 'console') path = '/console'
      else if (route === 'architecture') path = '/architecture'
      window.history.pushState({}, '', path)
      if (route === 'home' || route === 'architecture') {
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }
    }
  }, [])

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

  // 1. Home / Product Explainer & Architecture Views
  if (currentRoute === 'home' || currentRoute === 'architecture') {
    return (
      <LandingPage
        onNavigate={handleNavigate}
        reducedMotion={reducedMotion}
        onToggleReducedMotion={handleToggleReducedMotion}
      />
    )
  }

  // 2. Dedicated Safety Lab Route
  if (currentRoute === 'safety-lab') {
    return (
      <div className="app-container safetylab-mode-active">
        <SafetyLabView
          onExitLab={() => handleNavigate('home')}
          reducedMotion={reducedMotion}
          onToggleReducedMotion={handleToggleReducedMotion}
        />
      </div>
    )
  }

  // 3. Dedicated Interactive Demo / Director Route
  if (currentRoute === 'demo') {
    return (
      <div className="app-container director-mode-active">
        <DemoDirector
          scenarios={scenarios}
          onExitDirector={() => handleNavigate('home')}
          reducedMotion={reducedMotion}
          onToggleReducedMotion={handleToggleReducedMotion}
          assuranceReport={assuranceReport}
        />
      </div>
    )
  }

  // 4. Judge Decision Replay Console Route
  return (
    <div className="app-container">
      <Header
        currentView={currentView}
        onViewChange={setCurrentView}
        isLive={isLiveBackend}
        executionMode={scenarioData?.execution_mode || (isLiveBackend ? 'LIVE' : 'REPLAY')}
        reducedMotion={reducedMotion}
        onToggleReducedMotion={handleToggleReducedMotion}
        onOpenHome={() => handleNavigate('home')}
        onOpenDirector={() => handleNavigate('demo')}
        onOpenSafetyLab={() => handleNavigate('safety-lab')}
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
