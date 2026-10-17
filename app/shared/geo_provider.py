"""Map / geocoding provider abstraction (server-side).

The Android map SDK (rendering, POI picker) lives in the client; this is for server-side geocoding,
distance fallback and city resolution. ``MAP_PROVIDER=none`` (default) means: no external lookups;
callers must tolerate ``None`` and keep using the city text + client-supplied coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.shared.config import settings


@dataclass
class GeoPoint:
    lat: float
    lng: float
    city: str | None = None
    address: str | None = None


class GeoProvider(Protocol):
    name: str

    async def geocode(self, address: str, *, city: str | None = None) -> GeoPoint | None: ...

    async def reverse(self, lat: float, lng: float) -> GeoPoint | None: ...


class NoopGeoProvider:
    name = "none"

    async def geocode(self, address: str, *, city: str | None = None) -> GeoPoint | None:
        return None

    async def reverse(self, lat: float, lng: float) -> GeoPoint | None:
        return None


class VendorGeoProvider(NoopGeoProvider):
    def __init__(self, name: str):
        self.name = name

    async def geocode(self, address: str, *, city: str | None = None) -> GeoPoint | None:
        if not settings.map_server_key:
            raise RuntimeError(f"map provider {self.name} key not configured")
        raise NotImplementedError(f"map provider {self.name} not wired yet")

    async def reverse(self, lat: float, lng: float) -> GeoPoint | None:
        if not settings.map_server_key:
            raise RuntimeError(f"map provider {self.name} key not configured")
        raise NotImplementedError(f"map provider {self.name} not wired yet")


def get_geo_provider() -> GeoProvider:
    name = (settings.map_provider or "none").strip().lower()
    if name in {"amap", "tencent", "baidu"}:
        return VendorGeoProvider(name)
    return NoopGeoProvider()


def geo_status() -> dict:
    name = (settings.map_provider or "none").strip().lower()
    return {"provider": name, "ready": name == "none" or bool(settings.map_server_key), "real": name != "none"}
