import pytest

from tests.site.conftest import World


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)
