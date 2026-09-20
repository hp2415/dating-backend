"""pytest configuration for dating-backend."""

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
