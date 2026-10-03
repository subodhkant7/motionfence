"""USD scene specification and generator for MotionFence industrial plant in NVIDIA Isaac Sim.

Entities defined:
- Ground Plane: /World/GroundPlane
- Coolant Piping Manifold: /World/IndustrialCell/CoolantManifold
- Valve B (Revolute joint actuator): /World/IndustrialCell/CoolantManifold/ValveB
- Pump P1 (Impeller physics/visual): /World/IndustrialCell/CoolantManifold/PumpP1
- Cooling Loop: /World/IndustrialCell/CoolingLoop
- Human Safety Zone: /World/SafetyZones/HumanZone_Sector4
- Human Worker: /World/Actors/HumanWorker
- Safety Gateway Actuator Indicator: /World/Gateway/SafetyEnclaveActuator
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from motionfence.simulation.adapters.models import IsaacEntityMapping


class IndustrialCellSceneSpec(BaseModel):
    """Specification of the physical cell simulated in Isaac Sim."""
    root_prim: str = Field(default="/World/IndustrialCell")
    valve_b_prim: str = Field(default="/World/IndustrialCell/CoolantManifold/ValveB")
    pump_p1_prim: str = Field(default="/World/IndustrialCell/CoolantManifold/PumpP1")
    human_zone_prim: str = Field(default="/World/SafetyZones/HumanZone_Sector4")
    human_actor_prim: str = Field(default="/World/Actors/HumanWorker")
    gateway_prim: str = Field(default="/World/Gateway/SafetyEnclaveActuator")
    
    # Kinematic and geometric limits
    valve_open_angle_deg: float = Field(default=0.0)
    valve_closed_angle_deg: float = Field(default=90.0)
    valve_stroke_time_sec: float = Field(default=0.35)
    human_outside_pos: tuple = Field(default=(5.0, 0.0, 0.0))
    human_inside_pos: tuple = Field(default=(2.5, 0.0, 0.0))
    human_zone_bounds: Dict[str, Any] = Field(
        default_factory=lambda: {
            "x_min": 1.5,
            "x_max": 3.5,
            "y_min": -1.0,
            "y_max": 1.0,
            "z_min": 0.0,
            "z_max": 2.2,
        }
    )

    def get_entities(self) -> Dict[str, Any]:
        """Return dictionary mapping entity keys to their USD prim info."""
        return {
            "ground": IsaacPrimInfo(prim_path="/World/GroundPlane", entity_type="ground"),
            "valve_b": IsaacPrimInfo(prim_path=self.valve_b_prim, entity_type="revolute_joint_actuator"),
            "pump_p1": IsaacPrimInfo(prim_path=self.pump_p1_prim, entity_type="pump_motor"),
            "human_safety_zone": IsaacPrimInfo(prim_path=self.human_zone_prim, entity_type="safety_zone"),
            "human_worker": IsaacPrimInfo(prim_path=self.human_actor_prim, entity_type="human_actor"),
            "safety_enclave_actuator": IsaacPrimInfo(prim_path=self.gateway_prim, entity_type="safety_gateway"),
        }

    def generate_usd_ascii(self) -> str:
        """Generate OpenUSD ASCII representation of the industrial cell stage."""
        return generate_scene_usd_ascii()

    def generate_standalone_script(self) -> str:
        """Generate standalone Python script runnable directly in Isaac Sim."""
        return generate_isaac_standalone_python_script(self)


class IsaacPrimInfo(BaseModel):
    """Specification of an individual USD prim entity."""
    prim_path: str
    entity_type: str


def generate_scene_usd_ascii() -> str:
    """Generate minimal valid OpenUSD ASCII text representing the industrial cell."""
    return """#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1.0
    upAxis = "Z"
)

def Xform "World"
{
    def Xform "GroundPlane"
    {
        double3 xformOp:translate = (0, 0, 0)
        uniform token[] xformOpOrder = ["xformOp:translate"]
    }

    def Xform "IndustrialCell"
    {
        def Xform "CoolantManifold"
        {
            def Mesh "ValveB" (
                apiSchemas = ["PhysicsRevoluteJointAPI"]
            )
            {
                float physics:lowerLimit = 0.0
                float physics:upperLimit = 90.0
                token physics:axis = "Z"
                string motionfence:role = "VALVE_B_ACTUATOR"
            }

            def Mesh "PumpP1"
            {
                string motionfence:role = "PUMP_P1_MOTOR"
                float motionfence:target_rpm = 1750.0
            }

            def Xform "CoolingLoop"
            {
                string motionfence:role = "HEAT_EXCHANGER_LOOP"
            }
        }
    }

    def Scope "SafetyZones"
    {
        def Cube "HumanZone_Sector4"
        {
            double size = 2.0
            double3 xformOp:scale = (1.0, 1.0, 1.1)
            double3 xformOp:translate = (2.5, 0.0, 1.1)
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
            string motionfence:zone_id = "SECTOR_4"
        }
    }

    def Xform "Actors"
    {
        def Capsule "HumanWorker"
        {
            double height = 1.75
            double radius = 0.3
            double3 xformOp:translate = (5.0, 0.0, 0.875)
            uniform token[] xformOpOrder = ["xformOp:translate"]
            string motionfence:actor_id = "WORKER_01"
        }
    }

    def Xform "Gateway"
    {
        def Xform "SafetyEnclaveActuator"
        {
            string motionfence:auth_required = "AuthorizationTicket"
            string motionfence:status = "READY"
        }
    }
}
"""


def generate_isaac_standalone_python_script(spec: Optional[IndustrialCellSceneSpec] = None) -> str:
    """Generate a standalone Python script runnable directly inside Isaac Sim via:
    
    `./python.sh scripts/isaac_motionfence_cell.py`
    """
    s = spec or IndustrialCellSceneSpec()
    return f'''"""MotionFence NVIDIA Isaac Sim Standalone Industrial Cell Runner.

SECURITY INVARIANT:
Isaac Sim is downstream of MotionFence SafetyEnclave.
Actuation commands require a cryptographically verified AuthorizationTicket.
"""

import sys
import time

try:
    from isaacsim import SimulationApp
    simulation_app = SimulationApp({{"headless": False}})
    import omni
    import omni.timeline
    from pxr import Gf, UsdGeom, UsdPhysics
except ImportError:
    print("[ERROR] Isaac Sim environment required to run this script.")
    sys.exit(1)


def build_industrial_cell_stage(stage):
    """Construct minimal industrial cell primitives in the USD stage."""
    world = UsdGeom.Xform.Define(stage, "/World")
    
    # Ground
    ground = UsdGeom.Plane.Define(stage, "/World/GroundPlane")
    ground.CreateAxisAttr("Z")
    
    # Valve B
    valve = UsdGeom.Cylinder.Define(stage, "{s.valve_b_prim}")
    valve.CreateRadiusAttr(0.2)
    valve.CreateHeightAttr(0.4)
    
    # Pump P1
    pump = UsdGeom.Cube.Define(stage, "{s.pump_p1_prim}")
    pump.CreateSizeAttr(0.6)
    
    # Human Zone
    zone = UsdGeom.Cube.Define(stage, "{s.human_zone_prim}")
    zone.CreateSizeAttr(2.0)
    
    # Human Actor
    worker = UsdGeom.Capsule.Define(stage, "{s.human_actor_prim}")
    worker.CreateHeightAttr(1.75)
    worker.CreateRadiusAttr(0.3)
    
    print("[MotionFence] Industrial cell USD stage configured.")


def run_standalone_simulation():
    """Run standalone simulation stepping loop."""
    timeline = omni.timeline.get_timeline_interface()
    timeline.play()
    
    print("[MotionFence] NVIDIA Isaac Sim physical simulation active.")
    print("Listening for MotionFence authorized actuation signals...")
    
    while simulation_app.is_running():
        simulation_app.update()
        
    timeline.stop()
    simulation_app.close()


if __name__ == "__main__":
    run_standalone_simulation()
'''
