from __future__ import unicode_literals

import io
import logging

import requests

from requests.compat import urljoin


CLIENT_ID = '1e51d85f1b6d4025b6a5aa47bc61bf1c'
CLIENT_SECRET = 'af02034c5808483f9c09a693feadd0d6'
DISK_BASE_URL = 'https://cloud-api.yandex.net/v1/disk/'
OAUTH_TOKEN_URL = 'https://oauth.yandex.com/token'
SHORTLINK_URL = 'https://clck.ru/Dsvit'

BROWSE_LIMIT = (1 << 31) - 1

logger = logging.getLogger(__name__)


class YDiskException(Exception):

    def __init__(self, message, error_code):
        super(YDiskException, self).__init__(message)
        self.error_code = error_code

    def __str__(self):
        return '[%s] %s' % (self.error_code, self.message)

    @staticmethod
    def from_json(json):
        code = json['error']
        description = json.get('description') or json.get('error_description')
        return YDiskException(description, code)


class YDiskSession(requests.Session):

    def __init__(self, base_url, proxy, user_agent, token=None):
        super(YDiskSession, self).__init__()

        self.base_url = base_url
        self.headers.update({'User-Agent': user_agent})
        self.proxies.update({'http': proxy, 'https': proxy})
        if token:
            self.headers.update({'Authorization': 'OAuth ' + token})

    def request(self, method, url, *args, **kwargs):
        return super(YDiskSession, self).request(
            method, urljoin(self.base_url, url), *args, **kwargs
        )


class YDiskDirectory(object):

    def __init__(self, name, path):
        self.name = name
        self.path = path


class YDiskFile(object):

    def __init__(self, session, file_path, name, path, size=-1):
        self.file_path = file_path
        self.name = name
        self.path = path
        self._offset = 0
        self._session = session
        self._size = size

    def read(self, count=-1):
        if count == 0:
            return b''
        if count < 0:
            end = self.size() - 1
        else:
            end = self._offset + count - 1

        request_headers = {'Range': 'bytes=%d-%d' % (self._offset, end)}
        response = self._session.get(self.file_path, headers=request_headers)
        if not response.ok:
            error = YDiskException.from_json(response.json())
            raise IOError(error.message)
        self._offset += len(response.content)
        return response.content

    def tell(self):
        return self.seek(0, io.SEEK_CUR)

    def seek(self, offset, whence=0):
        if whence == io.SEEK_SET:
            self._offset = offset
        elif whence == io.SEEK_CUR:
            self._offset += offset
        elif whence == io.SEEK_END:
            self._offset = self.size() + offset
        else:
            raise IOError('Invalid whence')
        return self._offset

    def size(self):
        if self._size < 0:
            response = self._session.head(self.file_path)
            if response.ok:
                self._size = int(response.headers['Content-Length'])
            else:
                raise IOError('Couldn\'t determine size')
        return self._size

    def write(self, data):
        raise NotImplementedError

    def truncate(self, size=None):
        raise NotImplementedError

    def flush(self):
        raise NotImplementedError

    def fileno(self):
        raise NotImplementedError


class YDisk(object):

    id = None
    name = None

    def __init__(self, token, proxy, user_agent):
        self._session = YDiskSession(DISK_BASE_URL, proxy, user_agent, token)

        response = self._session.get('')
        if response.ok:
            user = response.json()['user']
            self.id = user['login']
            self.name = user.get('display_name') or self.id
        else:
            raise YDiskException.from_json(response.json())

    @staticmethod
    def exchange_token(auth_code, proxy, user_agent):
        request_data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'code': auth_code,
            'grant_type': 'authorization_code'
        }
        with YDiskSession(OAUTH_TOKEN_URL, proxy, user_agent) as s:
            response = s.post('', data=request_data)
            if response.ok:
                return response.json()['access_token']
            else:
                raise YDiskException.from_json(response.json())

    def dispose(self):
        self._session.close()

    def browse_dir(self, path):
        request_params = {
            'fields': '_embedded.items.file,_embedded.items.media_type,_embedded.items.name,_embedded.items.path,_embedded.items.size,_embedded.items.type',
            'limit': BROWSE_LIMIT,
            'path': path,
            'sort': 'name'
        }

        response = self._session.get('resources', params=request_params)
        if response.ok:
            for item in response.json()['_embedded']['items']:
                name = item['name']
                path = item['path'].lstrip('disk:')
                if item['type'] == 'dir':
                    yield YDiskDirectory(
                        name=name, path=path
                    )
                elif item['media_type'] == 'audio':
                    yield YDiskFile(
                        session=self._session,
                        file_path=item['file'],
                        name=name,
                        path=path,
                        size=item['size']
                    )
        else:
            raise YDiskException.from_json(response.json())

    def get_file(self, path):
        request_params = {
            'fields': 'name,file,size',
            'path': path
        }

        response = self._session.get('resources', params=request_params)
        if response.ok:
            file_info = response.json()
            return YDiskFile(
                session=self._session,
                file_path=file_info['file'],
                name=file_info['name'],
                path=path,
                size=file_info['size']
            )
        else:
            raise YDiskException.from_json(response.json())
