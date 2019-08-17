from __future__ import unicode_literals

import re

from setuptools import find_packages, setup


def get_version(filename):
    with open(filename) as fh:
        metadata = dict(re.findall("__([a-z]+)__ = '([^']+)'", fh.read()))
        return metadata['version']


setup(
    name='Mopidy-YDisk',
    version=get_version('mopidy_ydisk/__init__.py'),
    url='https://github.com/vonZeppelin/mopidy-ydisk',
    license='Apache License, Version 2.0',
    author='Leonid Bogdanov',
    author_email='leonid_bogdanov@mail.ru',
    description='Mopidy extension for Yandex.Disk',
    long_description=open('README.rst').read(),
    packages=find_packages(exclude=['tests', 'tests.*']),
    zip_safe=False,
    include_package_data=True,
    install_requires=[
        'setuptools',
        'Mopidy >= 1.0',
        'Pykka >= 1.1',
        'cachetools == 3.1.0',
        'furl == 2.0',
        'requests >= 2.15',
        'six >= 1.11',
    ],
    entry_points={
        'mopidy.ext': [
            'ydisk = mopidy_ydisk:Extension',
        ],
    },
    classifiers=[
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Topic :: Multimedia :: Sound/Audio :: Players',
    ],
)
