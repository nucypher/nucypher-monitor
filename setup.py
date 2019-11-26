#!/usr/bin/env python3
# -*- coding: utf-8 -*-


"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import os
import sys

from setuptools import setup, find_packages
from setuptools.command.install import install


#
# Metadata
#

PACKAGE_NAME = 'nucypher-monitor'
BASE_DIR = os.path.dirname(__file__)


ABOUT = dict()
with open(os.path.join(BASE_DIR, 'monitor', "__about__.py")) as f:
    exec(f.read(), ABOUT)

with open(os.path.join(BASE_DIR, "README.md")) as f:
    long_description = f.read()


#
# Utilities
#

class VerifyVersionCommand(install):
    """Custom command to verify that the git tag matches our version"""
    description = 'verify that the git tag matches our version'

    def run(self):
        tag = os.getenv('CIRCLE_TAG')
        if tag.startswith('v'):
            tag = tag[1:]

        version = ABOUT['__version__']
        if version.startswith('v'):
            version = version[1:]

        if tag != version:
            info = "Git tag: {0} does not match the version of this app: {1}".format(
                os.getenv('CIRCLE_TAG'), ABOUT['__version__']
            )
            sys.exit(info)


#
#  Dependencies
#

TESTS_REQUIRE = [
    'pytest',
]

DEPLOY_REQUIRES = [
    'bumpversion',
]


EXTRAS_REQUIRE = {'development': TESTS_REQUIRE,
                  'deployment': DEPLOY_REQUIRES}

setup(name=ABOUT['__title__'],
      url=ABOUT['__url__'],
      version=ABOUT['__version__'],
      author=ABOUT['__author__'],
      author_email=ABOUT['__email__'],
      description=ABOUT['__summary__'],
      license=ABOUT['__license__'],
      long_description=long_description,
      long_description_content_type="text/markdown",

      setup_requires=['pytest-runner'],  # required for `setup.py test`
      tests_require=TESTS_REQUIRE,
      extras_require=EXTRAS_REQUIRE,

      packages=find_packages(exclude=["tests"]),
      include_package_data=True,

      # Entry Points
      entry_points={'console_scripts': [
          '{0} = monitor.cli.main:monitor'.format(PACKAGE_NAME),
      ]},
      cmdclass={'verify': VerifyVersionCommand},

      classifiers=[
          "Development Status :: 3 - Alpha",
          "Intended Audience :: Developers",
          "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
          "Natural Language :: English",
          "Operating System :: OS Independent",
          "Programming Language :: Python",
          "Programming Language :: Python :: 3 :: Only",
          "Programming Language :: Python :: 3.6",
          "Programming Language :: Python :: 3.7",
          "Programming Language :: Python :: 3.8",
      ],
      python_requires='>=3'
      )
