#!/usr/bin/env python

from setuptools import setup, find_packages

VERSION = "0.5.16"
# Don't forget to update version in moya/__init__.py

classifiers = [
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    "Programming Language :: Python :: 2.7",
    "Programming Language :: Python :: 3.4"
]

long_desc = """Web development framework"""

setup(name='moya',
      version=VERSION,
      description="web development platform",
      long_description=long_desc,
      zip_safe=False,
      license="MIT",
      author="Will McGugan",
      author_email="will@willmcgugan.com",
      url="http://www.moyaproject.com",

      entry_points={
          "console_scripts": [
              'moya = moya.command.app:main',
              'moya-pm = moya.command.moyapi:main',
              'moya-srv = moya.command.moyasrv:main',
          ]
      },
      scripts=['scripts/moya-workon'],

      platforms=['any'],
      packages=find_packages(),
      include_package_data=True,
      exclude_package_data={'': ['_*', 'docs/*']},

      classifiers=classifiers,
      install_requires=['pyparsing',
                        'webob',
                        'sqlalchemy',
                        'pytz',
                        'pygments',
                        'fs >= 0.5.1',
                        'iso8601',
                        'babel',
                        'postmarkup',
                        'polib',
                        'pillow',
                        'pymysql',
                        'passlib',
                        'commonmark',
                        'requests',
                        'lxml',
                        'colorama',
                        'premailer'],
      extras_require={
          ':sys_platform!="win32"': ["notify2", "pyinotify"]
      },
      setup_requires=["setuptools_git >= 0.3"]
      )
