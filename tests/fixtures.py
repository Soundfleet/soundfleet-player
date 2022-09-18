import pytest

from soundfleet_player.device import Device


@pytest.fixture
def device():
    device = Device()
    device_data = device._cache.get()
    device_data.update(timezone_name="UTC")
    device._cache.set(device_data)
    device._audio_tracks_cache.update(
        [
            {"id": 1, "file": "1.ogg", "length": 1},
            {"id": 2, "file": "2.ogg", "length": 1},
            {"id": 3, "file": "3.ogg", "length": 1},
        ]
    )
    return device
