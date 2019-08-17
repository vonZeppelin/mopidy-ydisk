************
Mopidy-YDisk
************

.. image:: https://img.shields.io/pypi/v/Mopidy-YDisk.svg?style=flat
    :target: https://pypi.python.org/pypi/Mopidy-YDisk/
    :alt: Latest PyPI version

`Mopidy <http://www.mopidy.com/>`_ extension for playing music files from `Yandex.Disk <https://disk.yandex.ru/>`_.


Installation
============

Install by running::

    sudo pip install Mopidy-YDisk

Or, if available, install the Debian/Ubuntu package from `apt.mopidy.com <http://apt.mopidy.com/>`_.


Configuration
=============

Before starting Mopidy you should acquire and add Yandex.Disk tokens to your Mopidy configuration file::

    [ydisk]
    tokens = <token_1>,...,<token_n>


To acquire a Yandex.Disk token use Mopidy commands::

    mopidy ydisk shortlink
    mopidy ydisk token <auth_code>


Audio metadata retrieval
------------------------

Mopidy-YDisk extension can read and cache audio file metadata, i.e. tags.

This feature is disabled by default. To enable it, use the following parameter::

    [ydisk]
    tagging_mode = 3

where value ``0`` disables the feature and value ``0 < n <= 10`` means ``n`` threads will be used to load audio tags.

To clear the tags cache, use the following Mopidy command::

    mopidy ydisk clear


Project resources
=================

- `Source code <https://github.com/vonZeppelin/mopidy-ydisk>`_
- `Issue tracker <https://github.com/vonZeppelin/mopidy-ydisk/issues>`_


Changelog
=========

v0.2.0
------

- Improved audio tags retrieval.


v0.1.0
------

- Initial release.
