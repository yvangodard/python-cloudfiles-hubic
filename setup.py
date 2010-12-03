#!/usr/bin/python

from distutils.core import setup
from cloudfiles.consts import __version__

setup(
    name='cloudfiles',
    version=__version__,
    description='CloudFiles client library for python',
    author='Rackspace',
    url='https://www.rackspacecloud.com/',
    packages=['cloudfiles']
)
