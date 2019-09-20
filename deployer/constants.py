import os

from decouple import AutoConfig

config = AutoConfig(os.curdir)


DEFAULT_NAME_PATTERN = config(
    "DEPLOYER_DEFAULT_NAME_PATTERN",
    "stumptown-{username}-{branchname}-{date}")
