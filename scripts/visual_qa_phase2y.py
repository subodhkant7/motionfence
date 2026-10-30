import os
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8089"
OUT_DIR = os.path.abspath("docs/screenshots/phase_2y")
os.makedirs(OUT_DIR, exist_ok=True)

VIEWPORTS = [
    ("1080p", 1920, 1080),
    ("1440x900", 1440, 900),
    ("1366x768", 1366, 768),
    ("mobile", 390, 844),
]

def run_visual_qa():
    print(f"Starting Visual QA Suite for MotionFence Phase 2Y...")
    print(f"Target URL: {BASE_URL}")
    print(f"Output directory: {OUT_DIR}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--enable-webgl", "--use-gl=angle", "--use-angle=metal"]
        )

        for label, width, height in VIEWPORTS:
            print(f"\n--- Testing Viewport: {label} ({width}x{height}) ---")
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()

            # 1. Test /demo with new Split-Screen DecisionTwinStage
            page.goto(f"{BASE_URL}/demo", wait_until="networkidle")
            page.wait_for_timeout(1500)

            # Scene 1: Safe Isolation
            pills = page.locator(".scene-step-pill").all()
            if len(pills) > 1:
                pills[1].click()
                page.wait_for_timeout(2000)
                ss_path = os.path.join(OUT_DIR, f"demo_safe_isolation_{label}.png")
                page.screenshot(path=ss_path)
                print(f"  Captured: {ss_path}")

            # Scene 2: Hazard Zone Breach (Denied)
            if len(pills) > 2:
                pills[2].click()
                page.wait_for_timeout(2000)
                ss_path = os.path.join(OUT_DIR, f"demo_hazard_denial_{label}.png")
                page.screenshot(path=ss_path)
                print(f"  Captured: {ss_path}")

            # Scene 3: TOCTOU State Drift (Blocked)
            if len(pills) > 3:
                pills[3].click()
                page.wait_for_timeout(2000)
                ss_path = os.path.join(OUT_DIR, f"demo_toctou_drift_{label}.png")
                page.screenshot(path=ss_path)
                print(f"  Captured: {ss_path}")

            # Scene 4: Mechanical Fault & Recovery
            if len(pills) > 4:
                pills[4].click()
                page.wait_for_timeout(2000)
                ss_path = os.path.join(OUT_DIR, f"demo_mechanical_fault_{label}.png")
                page.screenshot(path=ss_path)
                print(f"  Captured: {ss_path}")

            # 2. Test /console in 3D Split Stage mode
            page.goto(f"{BASE_URL}/console", wait_until="networkidle")
            page.wait_for_timeout(2000)
            ss_path = os.path.join(OUT_DIR, f"console_3d_stage_{label}.png")
            page.screenshot(path=ss_path)
            print(f"  Captured: {ss_path}")

            context.close()

        browser.close()

    print("\nVisual QA complete! All target resolutions captured.")

if __name__ == "__main__":
    run_visual_qa()
