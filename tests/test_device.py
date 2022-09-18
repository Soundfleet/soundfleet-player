import pytest
import pytz

from unittest import mock

from soundfleet_player.device import Device

from .utils import is_redis_running


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@pytest.mark.parametrize(
    [
        "state",
        "expected_timezone",
        "expected_volume",
        "expected_audio_tracks",
        "expected_music_blocks",
        "expected_ad_blocks",
    ],
    [
        (
            {
                "device": {"id": "1", "timezone_name": "UTC", "volume": 100},
                "audio_tracks": [],
                "music_blocks": [],
                "ad_blocks": [],
            },
            pytz.UTC,
            100,
            {},
            [],
            [],
        ),
        (
            {
                "device": {
                    "id": "1",
                    "timezone_name": "Europe/Warsaw",
                    "volume": 0,
                },
                "audio_tracks": [{"id": 1, "file_name": "1.ogg"}],
                "music_blocks": [],
                "ad_blocks": [],
            },
            pytz.timezone("Europe/Warsaw"),
            0,
            {1: {"id": 1, "file_name": "1.ogg"}},
            [],
            [],
        ),
    ],
)
@mock.patch("soundfleet_player.device.Device.get_state")
@mock.patch("soundfleet_player.device.Device._ack_sync")
@mock.patch("soundfleet_player.device.client.make_request")
def test_sync(
    _,
    ack_sync,
    get_state,
    state,
    expected_timezone,
    expected_volume,
    expected_audio_tracks,
    expected_music_blocks,
    expected_ad_blocks,
):
    device = Device()
    get_state.return_value = state
    device.sync()
    assert ack_sync.called
    assert device.timezone == expected_timezone
    assert device.volume == expected_volume
    assert device.audio_tracks == expected_audio_tracks
    assert device.music_blocks == expected_music_blocks
    assert device.ad_blocks == expected_ad_blocks
