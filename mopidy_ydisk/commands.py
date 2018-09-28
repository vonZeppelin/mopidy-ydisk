from __future__ import absolute_import, print_function, unicode_literals

from mopidy.commands import Command

from . import get_proxy, get_user_agent
from .ydisk import SHORTLINK_URL, YDisk, YDiskException


class YDiskCommand(Command):

    def __init__(self):
        super(YDiskCommand, self).__init__()
        self.add_child('shortlink', PrintShortlinkCommand())
        self.add_child('token', ExchangeTokenCommand())


class PrintShortlinkCommand(Command):

    help = 'Print authentication shortlink'

    def __init__(self):
        super(PrintShortlinkCommand, self).__init__()
        self.set(base_verbosity_level=-1)

    def run(self, args, config):
        print('To get authorization code follow ' + SHORTLINK_URL)
        return 0


class ExchangeTokenCommand(Command):

    help = 'Exchange authorization code for access token'

    def __init__(self):
        super(ExchangeTokenCommand, self).__init__()
        self.set(base_verbosity_level=-1)
        self.add_argument(
            'code', metavar='CODE', type=int, help='Authorization code'
        )

    def run(self, args, config):
        try:
            token = YDisk.exchange_token(
                auth_code=args.code,
                proxy=get_proxy(config),
                user_agent=get_user_agent()
            )
            print(token)
            return 0
        except YDiskException as e:
            print('Could\'t exchange code for token: %s' % e)
            return 1
