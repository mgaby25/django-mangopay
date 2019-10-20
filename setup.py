#!/usr/bin/env python

from setuptools import setup, find_packages
import mangopay

setup(
    name='django-mangopay2',
    version=".".join(map(str, mangopay.__version__)),
    author='Gabriel Muj',
    author_email='muj_gabriel@yahoo.com',
    url='http://github.com/mgaby25/django-mangopay2',
    install_requires=[
        'Django>=1.11.10',
        'django-countries==5.5',
        'mangopaysdk>=3.7.0',
        'django-localflavor==2.2',
    ],
    description='Django package that helps in your Mangopay integration',
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "Framework :: Django",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Operating System :: OS Independent",
        "Topic :: Software Development"
    ],
)
