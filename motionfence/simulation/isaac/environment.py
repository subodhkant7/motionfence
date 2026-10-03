"""Environment discovery and hardware capability detection for NVIDIA Isaac Sim.

Inspects:
- Operating system (Ubuntu Linux 22.04/24.04 or Windows 11 required by NVIDIA)
- Host architecture (x86_64 or aarch64)
- NVIDIA GPU availability (via nvidia-smi / NVML)
- VRAM and system RAM
- CUDA runtime presence
- Isaac Sim standalone Python module ('isaacsim' or 'omni')
- Omniverse kit launcher binaries
"""

from typing import List, Optional
import os
import platform
import subprocess
import shutil
from pydantic import BaseModel, Field


class IsaacEnvironmentReport(BaseModel):
    """Report detailing NVIDIA Isaac Sim compatibility and local runtime availability."""
    is_available: bool = Field(description="Whether Isaac Sim can execute in the current host environment.")
    os_name: str = Field(description="Operating system name (e.g. Darwin, Linux, Windows).")
    os_version: str = Field(description="Operating system release/version.")
    arch: str = Field(description="CPU hardware architecture (e.g. arm64, x86_64).")
    os_type: str = Field(default="", description="Operating system family (Darwin, Linux, Windows).")
    nvidia_gpu_present: bool = Field(description="Whether a physical NVIDIA GPU was detected.")
    meets_hardware_requirements: bool = Field(default=False, description="Whether host meets NVIDIA hardware requirements.")
    gpu_model: Optional[str] = Field(default=None, description="Name/model of detected GPU.")
    gpu_vram_gb: Optional[float] = Field(default=None, description="VRAM in Gigabytes.")
    driver_version: Optional[str] = Field(default=None, description="NVIDIA display driver version.")
    cuda_available: bool = Field(default=False, description="Whether CUDA runtime is active.")
    isaac_python_installed: bool = Field(default=False, description="Whether 'isaacsim' Python package is importable.")
    isaac_version: Optional[str] = Field(default=None, description="Installed Isaac Sim release version.")
    isaac_binary_path: Optional[str] = Field(default=None, description="Filesystem path to isaac-sim launcher.")
    unavailability_reasons: List[str] = Field(default_factory=list, description="Reasons preventing live Isaac execution.")
    setup_guidance: str = Field(default="", description="Actionable instructions to provision Isaac Sim.")
    diagnostic_summary: str = Field(default="", description="Compact human-readable diagnostic summary.")


def detect_isaac_environment() -> IsaacEnvironmentReport:
    """Detect whether NVIDIA Isaac Sim is available in the current environment."""
    os_name = platform.system()
    os_version = platform.release()
    arch = platform.machine()

    nvidia_gpu = False
    gpu_model = None
    gpu_vram = None
    driver_version = None
    cuda_available = False
    isaac_python = False
    isaac_version = None
    isaac_bin = None
    unavailability: List[str] = []

    # 1. OS check: NVIDIA Isaac Sim officially requires Ubuntu Linux (22.04/24.04) or Windows 11
    if os_name == "Darwin":
        unavailability.append(
            f"macOS ({arch}) is not a supported host for NVIDIA Isaac Sim. "
            "NVIDIA Omniverse / Isaac Sim requires Linux (Ubuntu 22.04/24.04) or Windows 11."
        )

    # 2. Check for NVIDIA GPU via nvidia-smi
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            res = subprocess.run(
                [nvidia_smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                if len(parts) >= 3:
                    gpu_model = parts[0]
                    gpu_vram = float(parts[1]) / 1024.0
                    driver_version = parts[2]
                    nvidia_gpu = True
        except Exception:
            pass
    else:
        unavailability.append("nvidia-smi executable not found. No NVIDIA GPU driver detected.")

    # 3. Check for CUDA
    nvcc = shutil.which("nvcc")
    if nvcc:
        cuda_available = True
    else:
        # Check standard paths
        for p in ["/usr/local/cuda/bin/nvcc", "C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA"]:
            if os.path.exists(p):
                cuda_available = True
                break

    # 4. Check for Isaac Sim Python package
    try:
        import isaacsim  # type: ignore
        isaac_python = True
        isaac_version = getattr(isaacsim, "__version__", "6.0.0")
    except ImportError:
        try:
            import omni  # type: ignore
            isaac_python = True
            isaac_version = "Omniverse Kit"
        except ImportError:
            unavailability.append("Python 'isaacsim' / 'omni' SDK packages not installed in active environment.")

    # 5. Check for isaac-sim launcher binary
    isaac_bin = shutil.which("isaac-sim") or shutil.which("isaac-sim.sh") or shutil.which("isaac-sim.bat")
    if not isaac_bin:
        # Check standard default install paths
        candidates = [
            os.path.expanduser("~/.local/share/ov/pkg/isaac-sim-6.0.0/isaac-sim.sh"),
            os.path.expanduser("~/.local/share/ov/pkg/isaac_sim-4.2.0/isaac-sim.sh"),
            os.path.expanduser("~/.local/share/ov/pkg/isaac-sim-4.0.0/isaac-sim.sh"),
            "/opt/nvidia/isaac-sim/isaac-sim.sh",
        ]
        for c in candidates:
            if os.path.exists(c):
                isaac_bin = c
                break

    if not isaac_bin and not isaac_python:
        unavailability.append("Isaac Sim launcher executable not located in PATH or standard Omniverse directories.")

    # Overall availability
    is_available = (nvidia_gpu or isaac_python) and len(unavailability) == 0

    guidance = (
        "Isaac Sim is ready for live physical simulation."
        if is_available
        else (
            "To run live NVIDIA Isaac Sim: deploy MotionFence on an Ubuntu 22.04 LTS system with an "
            "NVIDIA RTX GPU (>= 8GB VRAM) and install Isaac Sim (recommended: 6.x via Omniverse Launcher). "
            "MotionFence automatically activates IsaacSimAdapter in offline contract mode on this machine."
        )
    )

    meets_hw = (os_name in ["Linux", "Windows"]) and nvidia_gpu and (gpu_vram is None or gpu_vram >= 8.0)
    summary = f"OS={os_name} {os_version} ({arch}), NVIDIA GPU={nvidia_gpu} ({gpu_model or 'None'}), CUDA={cuda_available}, Isaac Sim Available={is_available}"

    return IsaacEnvironmentReport(
        is_available=is_available,
        os_name=os_name,
        os_version=os_version,
        arch=arch,
        os_type=os_name,
        nvidia_gpu_present=nvidia_gpu,
        meets_hardware_requirements=meets_hw,
        gpu_model=gpu_model,
        gpu_vram_gb=gpu_vram,
        driver_version=driver_version,
        cuda_available=cuda_available,
        isaac_python_installed=isaac_python,
        isaac_version=isaac_version,
        isaac_binary_path=isaac_bin,
        unavailability_reasons=unavailability,
        setup_guidance=guidance,
        diagnostic_summary=summary,
    )
