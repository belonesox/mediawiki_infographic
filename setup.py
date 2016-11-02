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
    version='1.00',
    packages=['mediawiki_infographic'],
    author_email = "stanislav.fomin@gmail.com",

)

