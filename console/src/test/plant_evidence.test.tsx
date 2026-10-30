import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WebGLIndustrialPlant } from '../components/DigitalTwin/WebGLIndustrialPlant'
import { derivePresentationTimeline } from '../services/frameDerivation'
import safe from '../data/scenario_live_safe.json'
import { ScenarioData } from '../types'

describe('WebGL plant evidence HUD', () => {
  it('renders absent measurements as NOT_RECORDED without invented angle, distance, pressure or readiness', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    const state = derivePresentationTimeline('safe', null).frames[0].plantState
    const { container } = render(<WebGLIndustrialPlant plantState={state} reducedMotion />)
    expect(container.querySelector('.angle-badge')).toHaveTextContent('NOT_RECORDED')
    expect(container.querySelector('.pressure-badge')).toHaveTextContent('NOT_RECORDED')
    expect(container.querySelector('.actuator-badge')).toHaveTextContent('NOT_RECORDED')
    expect(container.querySelector('.zone-badge')).toHaveTextContent('NOT_RECORDED')
    expect(screen.queryByText(/5.0m|2.0m|95.5 PSI|90.0°/)).not.toBeInTheDocument()
    vi.restoreAllMocks()
  })

  it('updates real HUD values on rewind without retaining the later state', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    const frames = derivePresentationTimeline('safe', safe as unknown as ScenarioData).frames
    const { container, rerender } = render(<WebGLIndustrialPlant plantState={frames[8].plantState} />)
    expect(container.querySelector('.actuator-badge')).toHaveTextContent('VERIFIED')
    expect(container.querySelector('.pressure-badge')).toHaveTextContent('125 PSI')
    rerender(<WebGLIndustrialPlant plantState={frames[0].plantState} />)
    expect(container.querySelector('.actuator-badge')).toHaveTextContent('READY')
    expect(container.querySelector('.pressure-badge')).toHaveTextContent('95.5 PSI')
    expect(container.querySelector('.angle-badge')).toHaveTextContent('NOT_RECORDED')
    expect(JSON.parse(container.querySelector('.webgl-plant-container')!.getAttribute('data-source-state')!)).toEqual(frames[0].plantState)
    vi.restoreAllMocks()
  })
})
