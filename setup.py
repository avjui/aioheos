from __future__ import print_function
from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand
import io
import codecs
import os
import sys

import aioheos

here = os.path.abspath(os.path.dirname(__file__))

def read(*filenames, **kwargs):
    encoding = kwargs.get('encoding', 'utf-8')
    sep = kwargs.get('sep', '\n')
    buf = []
    for filename in filenames:
        with io.open(filename, encoding=encoding) as f:
            buf.append(f.read())
    return sep.join(buf)

#long_description =  read('README.txt', 'CHANGES.txt')
long_description = "MY TEST"

class PyTest(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        import pytest
        errcode = pytest.main(self.test_args)
        sys.exit(errcode)

setup(
    name='aioheos',
    version=aioheos.__version__,
    url='https://github.com/jarlebh/aioheos',
    license='MIT',
    author='Jarle Hjortland',
    tests_require=['pytest'],
    install_requires=['aiohttp>=3.4.4',
                      'lxml>=4.3.0'
                     ],
    cmdclass={'test': PyTest},
    author_email='jarlehjortland@gmail.com',
    description='API for communcation with HEOS loudspeakers',
    long_description=long_description,
    packages=['aioheos'],
    include_package_data=True,
    platforms='any',
    test_suite='aioheos.test.test_sandman',
    classifiers = [
        'Programming Language :: Python',
        'Development Status :: 4 - Beta',
        'Natural Language :: English',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT',
        'Operating System :: OS Independent',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        ],
    extras_require={
        'testing': ['pytest'],
    }
)