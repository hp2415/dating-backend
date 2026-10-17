import asyncio

import pytest

from app.modules.admin.system import launch_checks
from app.modules.ops.push_provider import LogPushProvider, VendorPushProvider, get_push_provider
from app.modules.trust.identity_provider import ManualIdentityProvider, id_number_format_ok
from app.shared.config import settings
from app.shared.geo_provider import NoopGeoProvider, get_geo_provider


def test_id_number_checksum():
    assert id_number_format_ok("11010519491231002X")
    assert not id_number_format_ok("110105194912310021")
    assert not id_number_format_ok("abc")


def test_default_providers_are_stubs():
    assert isinstance(get_push_provider(), LogPushProvider)
    assert isinstance(get_geo_provider(), NoopGeoProvider)
    r = asyncio.run(ManualIdentityProvider().verify_real_name(real_name="张三", id_number="11010519491231002X"))
    assert r.verified is False and r.stub is True


def test_vendor_push_refuses_without_credentials():
    p = VendorPushProvider("fcm")
    with pytest.raises(RuntimeError):
        asyncio.run(p.send([], None))  # type: ignore[arg-type]


def test_launch_checks_flag_defaults(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    checks = {c["key"]: c for c in launch_checks()}
    assert checks["jwt_secret"]["level"] == "critical"
    assert checks["payment"]["level"] == "critical"
    assert checks["icp"]["level"] == "critical"
    monkeypatch.setattr(settings, "icp_record_no", "京ICP备00000000号-1")
    assert {c["key"]: c for c in launch_checks()}["icp"]["level"] == "ok"
