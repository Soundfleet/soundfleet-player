import pytest
import time

from unittest import mock

from soundfleet_player.storage import AudioTrackStorage

from .utils import is_redis_running


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@mock.patch("soundfleet_player.storage.shutil.copyfileobj")
@mock.patch("soundfleet_player.storage.requests.get")
@mock.patch("soundfleet_player.storage.AudioTrackStorage.can_download")
@mock.patch("soundfleet_player.storage.AudioTrackStorage.track_file_exists")
def test_download_track_if_it_does_not_exist(
    track_file_exists, can_download, get, _
):
    can_download.return_value = True
    track_file_exists.return_value = False
    track = {"url": "", "file": "test.ogg"}
    AudioTrackStorage().download(track)
    assert get.called


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@mock.patch("soundfleet_player.storage.requests.get")
@mock.patch("soundfleet_player.storage.AudioTrackStorage.can_download")
@mock.patch("soundfleet_player.storage.AudioTrackStorage.track_file_exists")
def test_download_track_if_it_exist(track_file_exists, can_download, get):
    can_download.return_value = True
    track_file_exists.return_value = True
    track = {"url": "", "file": "test.ogg"}
    AudioTrackStorage().download(track)
    assert not get.called


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@mock.patch("soundfleet_player.storage.requests.get")
@mock.patch("soundfleet_player.storage.shutil.copyfileobj")
@mock.patch("soundfleet_player.storage.AudioTrackStorage._delete_file")
@mock.patch("soundfleet_player.storage.shutil.disk_usage")
@mock.patch("soundfleet_player.storage.AudioTrackStorage.track_file_exists")
def test_storage_file_rotation(track_file_exists, disk_usage, delete_file, *_):
    class MyDiskUsage:
        _free = 0

        @property
        def free(self):
            self._free += 2**20
            return self._free

    disk_usage.return_value = MyDiskUsage()
    track_file_exists.return_value = False
    track = {"url": "", "file": "test.ogg", "size": 2**20}
    AudioTrackStorage().download(track)
    assert delete_file.call_count == 1024


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@mock.patch("soundfleet_player.storage.requests.get")
@mock.patch("soundfleet_player.storage.shutil.copyfileobj")
@mock.patch("soundfleet_player.storage.AudioTrackStorage._delete_file")
@mock.patch("soundfleet_player.storage.shutil.disk_usage")
@mock.patch("soundfleet_player.storage.AudioTrackStorage.track_file_exists")
def test_file_rotation_removes_least_used_file(
    track_file_exists, disk_usage, delete_file, *_
):
    class MyDiskUsage:
        _free = 99 * 2**20

        @property
        def free(self):
            self._free += 2**20
            return self._free

    disk_usage.return_value = MyDiskUsage()
    track_file_exists.return_value = False
    track = {"url": "", "file": "test.ogg", "size": 2**20}
    storage = AudioTrackStorage()
    storage._download_lru_cache.touch("to_delete.ogg")
    time.sleep(1)
    storage._download_lru_cache.touch("test.ogg")
    storage.download(track)
    delete_file.assert_called_with("to_delete.ogg")
