from __future__ import absolute_import, unicode_literals

import logging
import os
import shelve
import pykka

from itertools import cycle
from cachetools import cachedmethod
from mopidy.audio.scan import Scanner
from mopidy.audio.tags import convert_tags_to_track
from mopidy.exceptions import ScannerError
from six import PY2
from six.moves import range
from . import Extension, get_proxy

logger = logging.getLogger(__name__)


class Minion(pykka.ThreadingActor):
    def __init__(self, config, parent_ref):
        super(Minion, self).__init__()

        self._parent_ref = parent_ref
        self._scanner = Scanner(
            proxy_config=get_proxy(config), timeout=5 * 60 * 1000
        )

    def on_receive(self, message):
        file_uri = message['file_uri']
        file_producer = message['file_producer']
        try:
            result = self._scanner.scan(uri=file_producer().download_link)
            logger.debug('Tagging result for file %s: %s', file_uri, result)
            if result.playable:
                track = convert_tags_to_track(result.tags).replace(
                    uri=file_uri,
                    length=result.duration
                )
                self._parent_ref.tell({
                    'file_uri': file_uri,
                    'track': track
                })
        except ScannerError as e:
            logger.debug('Couldn\'t get track info for file %s: %s', file_uri, e)


class Tagger(pykka.ThreadingActor):
    def __init__(self, config):
        super(Tagger, self).__init__()

        mode = config[Extension.ext_name]['tagging_mode']
        track_cache_file = os.path.join(
            Extension.get_data_dir(config), 'track_cache'
        )

        logger.debug(
            'Using %d threads for tagging, track cache file is %s',
            mode, track_cache_file
        )

        minions = [
            Minion.start(config, self.actor_ref) for _ in range(mode)
        ]
        self._minions = cycle(minions)
        self._track_cache = shelve.open(track_cache_file, protocol=-1)

        def dispose():
            for minion in minions:
                minion.stop()
            self._track_cache.close()

        self._dispose = dispose

    def on_stop(self):
        self._dispose()

    def on_receive(self, message):
        file_uri = Tagger._to_shelve_key(message['file_uri'])
        self._track_cache[file_uri] = message['track']

    @cachedmethod(
        cache=lambda self: self._track_cache,
        key=lambda file_uri, _: Tagger._to_shelve_key(file_uri)
    )
    def get_track(self, file_uri, file_producer=None):
        minion = next(self._minions)
        if file_producer:
            logger.debug('No cached track for file %s, scanning...', file_uri)
            minion.tell({
                'file_uri': file_uri,
                'file_producer': file_producer
            })
        return None

    @staticmethod
    def _to_shelve_key(uri):
        return uri.encode('utf-8') if PY2 else uri
