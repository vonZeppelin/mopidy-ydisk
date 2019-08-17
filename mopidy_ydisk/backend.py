from __future__ import absolute_import, division, unicode_literals

import logging
import pykka

from cachetools import cachedmethod, TTLCache
from furl import furl
from mopidy import backend
from mopidy.models import Ref, Track
from six import iterkeys, itervalues
from . import Extension, get_proxy, get_user_agent
from .tagger import Tagger
from .ydisk import YDisk, YDiskDirectory

logger = logging.getLogger(__name__)

ROOT_URI = 'ydisk:/'


def _resource_coords(resource_uri):
    path = furl(resource_uri).path
    disk_id = path.segments.pop(0)
    name = path.segments[-1] if path.segments else ''
    return disk_id, name, '/'.join(path.segments) or '/'


class YDiskBackend(pykka.ThreadingActor, backend.Backend):
    uri_schemes = [Extension.ext_name]

    def __init__(self, config, audio):
        super(YDiskBackend, self).__init__()

        self.library = YDiskLibrary(backend=self, config=config)
        self.playback = YDiskPlayback(audio=audio, backend=self)

    def on_start(self):
        logger.info('Initializing YDisks...')
        self.library.init()

    def on_stop(self):
        logger.info('Stopping YDisks')
        self.library.dispose()


class YDiskLibrary(backend.LibraryProvider):
    root_directory = Ref.directory(uri=ROOT_URI, name='Yandex.Disk')
    disks = {}

    def __init__(self, backend, config):
        super(YDiskLibrary, self).__init__(backend)

        ext_config = config[Extension.ext_name]

        def init():
            user_agent = get_user_agent()
            proxy = get_proxy(config)
            self.disks = {
                disk.id: disk
                for disk in (
                    YDisk(token=token, proxy=proxy, user_agent=user_agent)
                    for token in ext_config['tokens']
                )
            }
            logger.info(
                'YDisks initialized: %s',
                ', '.join(iterkeys(self.disks)) or '[none]'
            )

        self._browse_cache = TTLCache(maxsize=1000, ttl=30 * 60)
        self._init = init
        if ext_config['tagging_mode'] > 0:
            self._tagger = Tagger.start(config).proxy()

    def init(self):
        self._init()

    def dispose(self):
        for disk in itervalues(self.disks):
            disk.dispose()
        if self._tagger:
            self._tagger.stop()
        self._browse_cache.clear()

    @cachedmethod(cache=lambda self: self._browse_cache, key=lambda uri: uri)
    def browse(self, uri):
        if uri == ROOT_URI:
            return [
                Ref.directory(uri=ROOT_URI + disk.id, name=disk.name)
                for disk in itervalues(self.disks)
            ]
        else:
            disk_id, _, dir_path = _resource_coords(uri)
            disk = self.disks[disk_id]
            return [
                YDiskLibrary._make_ref(disk_id, resource)
                for resource in disk.browse_dir(dir_path)
            ]

    def lookup(self, uri):
        disk_id, file_name, file_path = _resource_coords(uri)
        disk = self.disks[disk_id]
        track = Track(uri=uri, name=file_name)
        if self._tagger:
            track_f = self._tagger.get_track(
                uri, lambda: disk.get_file(file_path)
            )
            track = track_f.get() or track
        return [track]

    def get_images(self, uris):
        return {}

    @staticmethod
    def _make_ref(disk_id, resource):
        resource_uri = (furl(ROOT_URI) / disk_id / resource.path).url
        if isinstance(resource, YDiskDirectory):
            return Ref.directory(uri=resource_uri, name=resource.name)
        else:
            return Ref.track(uri=resource_uri, name=resource.name)


class YDiskPlayback(backend.PlaybackProvider):
    def translate_uri(self, uri):
        disk_id, _, file_path = _resource_coords(uri)
        disk = self.backend.library.disks[disk_id]

        return disk.get_file(file_path).download_link
