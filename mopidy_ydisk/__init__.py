from __future__ import unicode_literals

import os

from mopidy import config, ext
from mopidy.httpclient import format_proxy, format_user_agent

__version__ = '0.2.0'


class Extension(ext.Extension):
    dist_name = 'Mopidy-YDisk'
    ext_name = 'ydisk'
    version = __version__

    def get_command(self):
        from .commands import YDiskCommand
        return YDiskCommand()

    def get_config_schema(self):
        schema = super(Extension, self).get_config_schema()
        schema['tagging_mode'] = config.Integer(minimum=0, maximum=10)
        schema['tokens'] = config.List(optional=True)
        return schema

    def get_default_config(self):
        conf_file = os.path.join(os.path.dirname(__file__), 'ext.conf')
        return config.read(conf_file)

    def setup(self, registry):
        from .backend import YDiskBackend
        registry.add('backend', YDiskBackend)


def get_user_agent():
    return format_user_agent(
        '%s/%s' % (Extension.dist_name, Extension.version)
    )


def get_proxy(cfg):
    return format_proxy(cfg['proxy'])
