#!/usr/bin/env python

from setuptools import setup, find_packages

with open('moya/_version.py') as f:
    exec(f.read())

try:
    import pypandoc
    long_description = pypandoc.convert('README.md', 'rst')
except(IOError, ImportError):
    long_description = open('README.md').read()


classifiers = [
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    "Programming Language :: Python :: 2.7",
    "Programming Language :: Python :: 3.4",
    "Programming Language :: Python :: 3.5"
]

setup(
    name='moya',
    version=VERSION,
    description="web development platform",
    long_description=long_description,
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
            'moya-doc = moya.command.moyadoc:main'
        ]
    },
    scripts=[
        'scripts/moya-workon',
    ],
    platforms=['any'],
    packages=find_packages(),
    include_package_data=True,
    exclude_package_data={'': ['_*', 'docs/*']},

    classifiers=classifiers,
    install_requires=[
        'babel~=2.3.4',
        'beautifulsoup4~=4.5.1',
        'bleach~=1.5.0',
        'colorama~=0.3.3',
        'commonmark~=0.6.3',
        'cssselect~=1.0.0',
        'fs~=2.0.0',
        'iso8601~=0.1.11',
        'lxml~=3.7.0',
        'passlib~=1.6.5',
        'pillow~=3.4.0',  # 3.0.0 version had an incompatible exif change
        'polib~=1.0.7',
        'postmarkup',
        'premailer~=2.9.3',
        'pygments~=2.1.3',
        'pymysql~=0.7.9',
        'pyparsing==2.1.10',
        'pytz>=2016.7',
        'requests~=2.9.1',
        'sqlalchemy~=1.1.4',
        'tzlocal~=1.3',
        'watchdog~=0.8.3',
        'webob~=1.6.0',
    ],
    extras_require={
        ':sys_platform=="linux2" or sys_platform=="linux3"': ["pyinotify"],
        'dev': ['notify2']
    },
    setup_requires=["setuptools_git >= 0.3"]
)
