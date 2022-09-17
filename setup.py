#!/usr/bin/env python

import setuptools
from pkg_resources import parse_requirements

with open("requirements.txt", "r") as req_file:
    requirements = req_file.readlines()
    requirements = parse_requirements(requirements)


setuptools.setup(
    name="soundfleet-player",
    version="1.0",
    packages=setuptools.find_packages(),
    url="https://soundfleet.io",
    license="BSD 3-Clause License",
    author="Sylwester Kulpa",
    author_email="sylwester.kulpa@gmail.com",
    description="Player for Soundfleet",
    install_requires=[str(r) for r in requirements],
    scripts=[
        "bin/playerd",
        "bin/schedulerd",
        "bin/playerctl",
    ],
)
