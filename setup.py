#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
 Setup for the package
"""

from setuptools import setup

setup(
    entry_points={
        'console_scripts': [
            'mediawiki_category_graph=mediawiki_infographic:mediawiki_category_graph',
        ],
    },
    name='mediawiki_infographic',
    version='1.03',
    packages=['mediawiki_infographic'],
    package_dir={'mediawiki_infographic': 'mediawiki_infographic'},
    package_data={'mediawiki_infographic': ['template/*.*']},
    author_email="stanislav.fomin@gmail.com",
    install_requires=[
        'networkx',
#        'mysql-connector-python',
    ],
    dependency_links=[
        'git+https://github.com/belonesox/python-belonesox-tools.git#egg=belonesox_tools'
    ],    
)
