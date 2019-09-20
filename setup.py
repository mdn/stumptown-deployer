from os import path

from setuptools import find_packages, setup

_here = path.dirname(__file__)


dev_requirements = ["black==19.3b0", "flake8==3.7.8", "therapist"]

setup(
    name="stumptown-deployer",
    version="0.2.6",
    author="Mozilla MDN",
    url="https://github.com/mdn/stumptown-deployer",
    description="Deploying static Stumptown sites",
    long_description=open(path.join(_here, "README.md")).read(),
    long_description_content_type="text/markdown",
    license="MPL 2.0",
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: Implementation :: CPython",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
    ],
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=["boto3", "click", "PyGithub", "GitPython", "python-decouple"],
    extras_require={"dev": dev_requirements},
    entry_points="""
        [console_scripts]
        stumptown-deployer=deployer.main:cli
    """,
    setup_requires=[],
    tests_require=["pytest"],
    keywords="git github s3 boto3 stumptown mdn",
)
