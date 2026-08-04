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
class VehicleTelemetryState:
    """In-memory telemetry state for one VIN."""

    sensors: dict[str, Any] = field(default_factory=dict)
    binary_sensors: dict[str, bool | None] = field(default_factory=dict)
    location: dict[str, Any] | None = None
    connectivity: bool | None = None
    timestamps: dict[str, EntityTimestamps] = field(default_factory=dict)
