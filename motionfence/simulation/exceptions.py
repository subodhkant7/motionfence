"""Simulation and actuator error definitions."""


class SimulationError(Exception):
    """Base exception for physical simulation operations."""
    pass


class UnauthorizedActionError(SimulationError):
    """Raised when an unapproved action proposal attempts to execute or mutate physical state."""
    pass


class ActuatorFaultError(SimulationError):
    """Raised when an actuator experiences mechanical failure or jamming."""
    pass
