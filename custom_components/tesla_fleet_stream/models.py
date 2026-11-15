"""Runtime models for Tesla Fleet Stream."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class EntityTimestamps:
    """Track when telemetry was received and when the value last changed."""

    last_updated: datetime
    last_changed: datetime


@dataclass
class DriveConsumptionSession:
    """Track energy/odometer anchors for the current drive session."""

    active: bool = False
    start_odometer_miles: float | None = None
    start_lifetime_energy_kwh: float | None = None
    start_energy_remaining_kwh: float | None = None
    # Used when Gear is unavailable: keep the trip open through brief stops.
    last_moving_at: datetime | None = None


@dataclass
class VehicleTelemetryState:
    """In-memory telemetry state for one VIN."""

    sensors: dict[str, Any] = field(default_factory=dict)
    binary_sensors: dict[str, bool | None] = field(default_factory=dict)
    location: dict[str, Any] | None = None
    connectivity: bool | None = None
    timestamps: dict[str, EntityTimestamps] = field(default_factory=dict)
    drive_consumption: DriveConsumptionSession = field(
        default_factory=DriveConsumptionSession
    )
    active_alerts: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_alert: dict[str, Any] | None = None
