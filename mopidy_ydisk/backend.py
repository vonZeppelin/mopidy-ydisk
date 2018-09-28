from __future__ import absolute_import, division, unicode_literals

import logging

import mutagen
import pykka

from itertools import cycle, takewhile

from cachetools import cachedmethod, TTLCache
from furl import furl
from mopidy import backend
from mopidy.models import Album, Artist, Ref, Track
from six import iterkeys, itervalues, text_type
from six.moves import range

from . import Extension, get_proxy, get_user_agent
from .ydisk import YDisk, YDiskDirectory


logger = logging.getLogger(__name__)

ROOT_URI = 'ydisk:/'


def resource_coords(resource_uri):
    path = furl(resource_uri).path
    disk_id = path.segments.pop(0)
    name = path.segments[-1] if path.segments else ''
    return disk_id, name, '/'.join(path.segments) or '/'


class TagsRetriever(pykka.ThreadingActor):

    def __init__(self, parent_ref):
        super(TagsRetriever, self).__init__()

        self._parent_ref = parent_ref

    def on_receive(self, message):
        disk = message['disk']
        file_uri = message['file_uri']
        try:
            _, _, file_path = resource_coords(file_uri)
            tags = mutagen.File(disk.get_file(file_path), easy=True)
            logger.debug('Read tags for file %s: %s', file_uri, tags)
            self._parent_ref.tell({
                'file_uri': file_uri,
                'tags': tags
            })
        except Exception as e:
            logger.warn('Couldn\'t read tags for file %s: %s', file_uri, e)


class TagsReader(pykka.ThreadingActor):

    def __init__(self, tags_retrieve_concurrency):
        super(TagsReader, self).__init__()

        if tags_retrieve_concurrency > 0:
            tags_retrievers = [
                TagsRetriever.start(self.actor_ref)
                for _ in range(tags_retrieve_concurrency)
            ]
            self._cache = TTLCache(maxsize=1000, ttl=24 * 60 * 60)
            self._tags_retrievers = cycle(tags_retrievers)

            def on_stop():
                for ref in tags_retrievers:
                    ref.stop()
                self._cache.clear()

            self._on_stop = on_stop
        else:
            self._cache = None
            self._tags_retrievers = None

            def on_stop():
                pass

            self._on_stop = on_stop

    def on_stop(self):
        self._on_stop()

    def on_receive(self, message):
        if self._cache:
            self._cache[message['file_uri']] = message['tags']

    @cachedmethod(
        cache=lambda self: self._cache, key=lambda self, file_uri, _: file_uri
    )
    def read(self, file_uri, disk):
        if self._tags_retrievers:
            logger.debug('No cached tags for file %s, reading...', file_uri)

            retriever_ref = next(self._tags_retrievers)
            retriever_ref.tell({
                'file_uri': file_uri,
                'disk': disk
            })

        return None


class YDiskBackend(pykka.ThreadingActor, backend.Backend):

    uri_schemes = [Extension.ext_name]

    def __init__(self, config, audio):
        super(YDiskBackend, self).__init__()

        ydisk_config = config[Extension.ext_name]
        self._tags_reader_ref = TagsReader.start(
            ydisk_config['tags_retrieve_concurrency']
        )
        self.library = YDiskLibrary(
            backend=self,
            tags_reader=self._tags_reader_ref.proxy(),
            proxy=get_proxy(config),
            tokens=ydisk_config['tokens']
        )
        self.playback = YDiskPlayback(audio=audio, backend=self)

    def on_start(self):
        self.library.init()

    def on_stop(self):
        self.library.dispose()
        self._tags_reader_ref.stop()


class YDiskLibrary(backend.LibraryProvider):

    root_directory = Ref.directory(uri=ROOT_URI, name='Yandex.Disk')
    disks = {}

    def __init__(self, backend, tags_reader, proxy, tokens):
        super(YDiskLibrary, self).__init__(backend)

        def init():
            user_agent = get_user_agent()
            self.disks = {
                disk.id: disk
                for disk in (
                    YDisk(token=token, proxy=proxy, user_agent=user_agent)
                    for token in tokens
                )
            }
            logger.info(
                'Initialized YDisks [%s]', ', '.join(iterkeys(self.disks))
            )

        self._cache = TTLCache(maxsize=1000, ttl=30 * 60)
        self._init = init
        self._tags_reader = tags_reader

    def init(self):
        self._init()

    @cachedmethod(cache=lambda self: self._cache, key=lambda self, uri: uri)
    def browse(self, uri):
        if uri == ROOT_URI:
            return [
                Ref.directory(uri=ROOT_URI + disk.id, name=disk.name)
                for disk in itervalues(self.disks)
            ]
        else:
            disk_id, _, dir_path = resource_coords(uri)
            disk = self.disks[disk_id]
            return [
                YDiskLibrary._make_ref(disk_id, resource)
                for resource in disk.browse_dir(dir_path)
            ]

    def lookup(self, uri):
        disk_id, file_name, _ = resource_coords(uri)
        disk = self.disks[disk_id]
        file_tags = self._tags_reader.read(uri, disk).get()
        if file_tags:
            get_tag = YDiskLibrary._get_tag(file_tags)
            return [
                Track(
                    uri=uri,
                    name=get_tag('title', file_name),
                    artists=[
                        Artist(name=artist, sortname=artist)
                        for artist in file_tags.get('artist', ())
                    ],
                    album=Album(name=get_tag('album')),
                    genre=get_tag('genre'),
                    track_no=get_tag('tracknumber', 0),
                    disc_no=get_tag('discnumber', 0),
                    date=get_tag('date'),
                    bitrate=get_tag('bpm', 0)
                )
            ]
        else:
            return [Track(uri=uri, name=file_name)]

    def get_images(self, uris):
        return {}

    def dispose(self):
        for disk in itervalues(self.disks):
            disk.dispose()
        self._cache.clear()

    @staticmethod
    def _get_tag(tags):
        def get_tag(tag_key, default='Unknown'):
            tag = tags.get(tag_key)
            if not tag:
                return default

            # mutagen always returns an iterable with tag values - get 1st one
            tag = next(iter(tag))

            # when an int is expected
            if isinstance(default, int):
                # make sure tag value contains only digits
                sanitized_tag = takewhile(text_type.isdigit, tag)
                # convert sanitized value to int
                tag = int(''.join(sanitized_tag))

            return tag

        return get_tag

    @staticmethod
    def _make_ref(disk_id, resource):
        resource_uri = (furl(ROOT_URI) / disk_id / resource.path).url
        if isinstance(resource, YDiskDirectory):
            return Ref.directory(uri=resource_uri, name=resource.name)
        else:
            return Ref.track(uri=resource_uri, name=resource.name)


class YDiskPlayback(backend.PlaybackProvider):

    def translate_uri(self, uri):
        disk_id, _, file_path = resource_coords(uri)
        disk = self.backend.library.disks[disk_id]

        return disk.get_file(file_path).file_path
