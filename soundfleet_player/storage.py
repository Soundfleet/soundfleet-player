import logging
import os
import requests
import shutil

from typing import Union

from soundfleet_player.conf import settings
from soundfleet_player.types import AudioTrack


logger = logging.getLogger(__name__)


class DownloadFailed(Exception):
    pass


class AudioTrackStorage:
    _download_dir = settings.DOWNLOAD_DIR
    _safe_buffer = 2**30  # 1GB

    def __init__(self):
        from soundfleet_player.cache import (
            DownloadLRUCache,
        )  # avoid circular import

        if not os.path.exists(self._download_dir):
            os.makedirs(self._download_dir, exist_ok=True)
        self._download_lru_cache = DownloadLRUCache(self._download_dir)

    def track_file_exists(self, track):
        return os.path.exists(self._get_path(track))

    def download(self, track: AudioTrack):
        if not self.track_file_exists(track):
            while not self.can_download(self._download_dir, track):
                logger.debug(
                    f"Unable to download {track['file']},"
                    f" insufficient free space"
                )
                self.release_disk_space()
            try:
                with requests.get(
                    track.get("url"), stream=True, timeout=3
                ) as r:
                    r.raise_for_status()
                    with open(self._get_path(track), "wb") as f:
                        shutil.copyfileobj(r.raw, f)
                logger.debug(f"Downloaded file: {track['file']}")
            except Exception as e:
                logger.error(e)
                raise DownloadFailed(track)
        else:
            logger.debug(f"File {track['file']} already present in filesystem")
        self._download_lru_cache.touch(track["file"])
        return track

    @classmethod
    def remove_tracks(cls, *tracks):
        for track in tracks:
            path = cls._get_path(track)
            logger.debug(f"Trying to remove file: {path} from local filesystem")
            if os.path.exists(path):
                os.unlink(path)

    @classmethod
    def can_download(cls, dest: str, track: dict):
        """
        Check if destination has enough space with margin of 100MB
        """
        return shutil.disk_usage(dest).free - track["size"] >= cls._safe_buffer

    @classmethod
    def _get_path(cls, track):
        return os.path.join(cls._download_dir, track["file"])

    def release_disk_space(self) -> None:
        """
        Delete single track using LRU algorithm
        """
        files_with_date = self._download_lru_cache.all()
        lru_ordered = iter(sorted(files_with_date.items(), key=lambda i: i[1]))
        fname, counter = next(lru_ordered, (None, None))
        self._delete_file(fname)

    def _delete_file(self, fname: Union[str, None]) -> None:
        if fname is not None:
            path = os.path.abspath(os.path.join(self._download_dir, fname))
            if os.path.exists(path):
                os.unlink(path)
            self._download_lru_cache.remove(fname)
