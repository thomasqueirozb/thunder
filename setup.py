#!/usr/bin/env python3
from setuptools import setup, find_packages
from thunder.version import __version__


setup(
    name="thunder",
    # packages=["thunder"],
    packages=find_packages(),
    version=__version__,
    description="Boto3 wrapper",
    url="http://github.com/thomasqueirozb/thunder",
    author="Thomas Queiroz",
    author_email="thomasqueirozb@gmail.com",
    license="MIT",
    zip_safe=False,
    python_requires=">=3.5",
)
