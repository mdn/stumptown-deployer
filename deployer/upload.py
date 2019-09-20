import datetime
import getpass
import shutil
import time
from urllib.parse import urlparse

import boto3
import click
import git

from .constants import (
    DEFAULT_NAME_PATTERN
)
# from .exceptions import (
#     # DirtyRepoError,
#     # PushBranchError,
#     # RemoteURLError,
#     # MasterBranchError,
# )
from .utils import info, success, warning, ppath


def center(msg):
    t_width, _ = shutil.get_terminal_size(fallback=(80, 24))
    warning(f"-----  {msg}  ".ljust(t_width, "-"))


def upload(directory, config):
    if not config.get('name'):
        repo = git.Repo(directory)
        active_branch = repo.active_branch
        config['name'] = DEFAULT_NAME_PATTERN.format(
            username=getpass.getuser(),
            branchname=active_branch.name,
            date=datetime.datetime.utcnow().strftime("%Y%m%d")
        )

    info(f"About to upload {ppath(directory)} to {config['name']}")
