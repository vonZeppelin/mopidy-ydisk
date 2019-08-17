from __future__ import unicode_literals

import requests

from requests.compat import urljoin

CLIENT_ID = '1e51d85f1b6d4025b6a5aa47bc61bf1c'
CLIENT_SECRET = 'af02034c5808483f9c09a693feadd0d6'
DISK_BASE_URL = 'https://cloud-api.yandex.net/v1/disk/'
OAUTH_TOKEN_URL = 'https://oauth.yandex.com/token'
SHORTLINK_URL = 'https://clck.ru/Dsvit'

BROWSE_LIMIT = (1 << 31) - 1
BROWSE_DIR_FIELDS = ','.join(
    '_embedded.items.' + field
    for field in ['file', 'media_type', 'name', 'path', 'type']
)
LIST_FILES_FIELDS = ','.join(
    'items.' + field
    for field in ['file', 'name', 'path', 'type']
)


class YDiskException(Exception):
    def __init__(self, message, error_code):
        super(YDiskException, self).__init__(message)
        self.error_code = error_code

    def __str__(self):
        return '[%s] %s' % (self.error_code, self.message)

    @classmethod
    def from_json(cls, json):
        code = json['error']
        description = json.get('description') or json.get('error_description')
        return cls(description, code)


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
    def __init__(self, session, name, path, download_link):
        self._session = session
        self.download_link = download_link
        self.name = name
        self.path = path


class YDisk(object):
    @staticmethod
    def exchange_token(auth_code, proxy, user_agent):
        request_data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'code': auth_code,
            'grant_type': 'authorization_code'
        }
        with YDiskSession(OAUTH_TOKEN_URL, proxy, user_agent) as session:
            response = session.post('', data=request_data)
            if response.ok:
                return response.json()['access_token']
            else:
                raise YDiskException.from_json(response.json())

    def __init__(self, token, proxy, user_agent):
        self._session = YDiskSession(DISK_BASE_URL, proxy, user_agent, token)

        request_params = {
            'fields': 'user.login,user.display_name'
        }
        response = self._session.get('', params=request_params)
        if response.ok:
            user = response.json()['user']
            self.id = user['login']
            self.name = user.get('display_name') or self.id
        else:
            raise YDiskException.from_json(response.json())

    def dispose(self):
        self._session.close()

    def browse_dir(self, path):
        request_params = {
            'fields': BROWSE_DIR_FIELDS,
            'limit': BROWSE_LIMIT,
            'path': path,
            'sort': 'name'
        }

        response = self._session.get('resources', params=request_params)
        if response.ok:
            for item in response.json()['_embedded']['items']:
                name = item['name']
                path = YDisk._get_item_path(item)
                if item['type'] == 'dir':
                    yield YDiskDirectory(name=name, path=path)
                elif item['media_type'] == 'audio':
                    yield YDiskFile(
                        session=self._session,
                        name=name,
                        path=path,
                        download_link=item['file']
                    )
        else:
            raise YDiskException.from_json(response.json())

    def get_file(self, path):
        request_params = {
            'fields': 'name,file',
            'path': path
        }

        response = self._session.get('resources', params=request_params)
        if response.ok:
            file_info = response.json()
            return YDiskFile(
                session=self._session,
                name=file_info['name'],
                path=path,
                download_link=file_info['file']
            )
        else:
            raise YDiskException.from_json(response.json())

    def list_files(self, media_type='audio'):
        request_params = {
            'fields': LIST_FILES_FIELDS,
            'limit': BROWSE_LIMIT,
            'media_type': media_type
        }

        response = self._session.get('resources/files', params=request_params)
        if response.ok:
            for item in response.json()['items']:
                if item['type'] == 'file':
                    yield YDiskFile(
                        session=self._session,
                        name=item['name'],
                        path=YDisk._get_item_path(item),
                        download_link=item['file']
                    )
        else:
            raise YDiskException.from_json(response.json())

    @staticmethod
    def _get_item_path(item):
        return item['path'].lstrip('disk:')
