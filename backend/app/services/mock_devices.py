"""Backward-compatibility shim.

Re-exports SimulatedDeviceAdapter and SimulatedDeviceManager under their
legacy names. New code should import from
app.services.bms_simulator.adapters.simulated_adapter directly.
"""

from app.services.bms_simulator.adapters.simulated_adapter import (  # noqa: F401
    SimulatedDeviceAdapter as MockDeviceAdapter,
    SimulatedDeviceManager as MockDeviceManager,
)

__all__ = ["MockDeviceAdapter", "MockDeviceManager"]
