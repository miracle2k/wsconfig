#!/usr/bin/env python
# encoding: utf8
"""Adapted from virtualenv's setup.py
"""

import sys, os
try:
    from setuptools import setup
    kw = {'entry_points':
          """[console_scripts]\nwsconfig = wsconfig:run\n""",
          'zip_safe': False}
except ImportError:
    from distutils.core import setup
    kw = {'scripts': ['wsconfig']}
import re

here = os.path.dirname(os.path.abspath(__file__))

# Figure out the version
version_re = re.compile(
    r'__version__ = (\(.*?\))')
fp = open(os.path.join(here, 'wsconfig.py'))
version = None
for line in fp:
    match = version_re.search(line)
    if match:
        exec "version = %s" % match.group(1)
        version = ".".join(map(str, version))
        break
else:
    raise Exception("Cannot find version in wsconfig.py")
fp.close()

setup(name='wsconfig',
      version=version,
      description="A tiny utility to automatize setting up a new workstation; linking config files and installing packages. ",
      classifiers=[
        'License :: OSI Approved :: BSD License',
      ],
      author='Michael Elsdörfer',
      author_email='michael@elsdoerfer.com',
      url='http://github.com/miracle2k/wsconfig',
      license='BSD',
      py_modules=['wsconfig'],
      **kw
      )

