"""Evidence assertions and actual WebGL captures, with no provider calls or deployment."""
import argparse
import json
import math
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def run(base_url: str, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--enable-webgl', '--use-gl=angle', '--use-angle=swiftshader'])
        page = browser.new_page(viewport={'width': 1920, 'height': 1080}, reduced_motion='reduce')
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(f'{base_url}/demo', wait_until='networkidle')

        def snapshot(scene, stage, expected_valve, expected_status, expected_zone=None):
            page.get_by_test_id(f'stage-item-{stage}').click()
            viewport = page.locator('.webgl-plant-container')
            expect(viewport).to_have_attribute('data-rendered-zone', expected_zone or 'CLEAR')
            state = json.loads(viewport.get_attribute('data-source-state'))
            assert state['valve_b_state'] == expected_valve, state
            expect(page.get_by_test_id('director-status-badge')).to_contain_text(expected_status)
            expect(page.get_by_test_id('director-mode-badge')).to_contain_text('REPLAY')
            assert page.locator('.webgl-canvas').count() == 1, 'Actual WebGL canvas required'
            expect(viewport).to_have_attribute('data-rendered-valve-radians', str(math.pi / 2) if expected_valve == 'CLOSED' else '0')
            applied_angle = float(viewport.get_attribute('data-rendered-valve-radians'))
            assert math.isclose(applied_angle, math.pi / 2 if expected_valve == 'CLOSED' else 0, abs_tol=1e-6)
            source = page.get_by_test_id('plant-source').inner_text()
            assert state['stage_name'] in ('initial', 'authorized', 'actuated', 'verified', 'denied', 'locked', 'drifted', 'locked_toctou', 'fault_injected', 'recovered')
            source_record = page.request.get(f'{base_url}/api/scenarios/{scene}').json()
            assert state in source_record['digital_twin_snapshots'], 'Renderer must receive an actual recorded snapshot'
            assert page.get_by_test_id(f'stage-item-{stage}').locator('.source-reference').inner_text().split(' · ')[0].removeprefix('Source: ') in source
            # Critical labels must fit, and the 3D viewport must stay within 1080p.
            for selector in ['.stage-compact-header', '.webgl-camera-presets-bar', '.webgl-hud-overlay']:
                box = page.locator(selector).bounding_box()
                assert box and box['x'] >= 0 and box['x'] + box['width'] <= 1920
            expected_camera = 'Recovery' if stage == 'recovery' else 'Safety Zone' if stage == 'world_change' else 'Actuator' if stage in ('execution', 'revalidation') else 'Valve B' if stage == 'verification' else 'Overview'
            expect(page.locator('.preset-btn.active')).to_have_text(expected_camera)
            page.wait_for_timeout(250)
            plant_box = viewport.bounding_box()
            for value in page.locator('.hud-value').all():
                box = value.bounding_box()
                assert box and plant_box and box['x'] >= plant_box['x'] and box['x'] + box['width'] <= plant_box['x'] + plant_box['width'], box
            page.screenshot(path=str(output / f'{scene}_{stage}_1920x1080.png'))
            results.append({'scene': scene, 'stage': stage, 'status': expected_status, 'snapshot': state, 'source': source, 'applied_valve_radians': applied_angle})

        def select(scene):
            page.get_by_test_id(f'timeline-step-{scene}').click()
            expect(page.get_by_test_id('plant-source')).to_contain_text('RECORDED NEMOTRON INFERENCE', timeout=12000)
            expect(page.get_by_test_id('stage-item-verification')).to_contain_text('PENDING')
            assert page.get_by_test_id('active-step-counter').inner_text() == '1'

        select('safe')
        snapshot('safe', 'observe', 'OPEN', 'UNVERIFIED')
        snapshot('safe', 'execution', 'CLOSED', 'UNVERIFIED')
        snapshot('safe', 'verification', 'CLOSED', 'VERIFIED')
        snapshot('safe', 'observe', 'OPEN', 'UNVERIFIED')
        select('denied')
        snapshot('denied', 'policy', 'OPEN', 'DENIED', 'OCCUPIED')
        snapshot('denied', 'execution', 'OPEN', 'DENIED', 'OCCUPIED')
        select('toctou')
        snapshot('toctou', 'world_change', 'OPEN', 'UNVERIFIED', 'OCCUPIED')
        snapshot('toctou', 'revalidation', 'OPEN', 'BLOCKED', 'OCCUPIED')
        snapshot('toctou', 'authorization', 'OPEN', 'UNVERIFIED', 'CLEAR')
        select('recovery')
        snapshot('recovery', 'execution', 'OPEN', 'UNVERIFIED')
        snapshot('recovery', 'verification', 'OPEN', 'VERIFICATION_FAILED')
        snapshot('recovery', 'recovery', 'CLOSED', 'UNVERIFIED')
        assert 'FINAL INDEPENDENT VERIFICATION NOT RECORDED' in page.get_by_test_id('stage-expanded-content').inner_text()
        assert not errors, errors
        (output / 'browser-evidence.json').write_text(json.dumps({'viewport': [1920, 1080], 'webgl': True, 'checks': results, 'page_errors': errors}, indent=2))
        browser.close()
    print(f'{len(results)} evidence/mesh checks passed; screenshots: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8091')
    parser.add_argument('--output', type=Path, default=Path('output/playwright/phase2y-r1'))
    args = parser.parse_args()
    run(args.base_url, args.output)
