import functools
import pkg_resources
from pathlib import Path

import click

from .constants import (
DEFAULT_NAME_PATTERN
)
from .exceptions import CoreException
from .upload import upload
from .utils import error, info


def cli_wrap(fn):
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        try:
            fn(*args, **kwargs)
        except CoreException as exception:
            info(exception.__class__.__name__)
            error(str(exception))
            raise click.Abort

    return inner


# # XXX This all feels clunky! Useful functionality but annoying to have to repeat
# # the names so much.
# make_submodules_pr = cli_wrap(make_submodules_pr)
# start_cleaner = cli_wrap(start_cleaner)
# start_localerefresh = cli_wrap(start_localerefresh)
# check_builds = cli_wrap(check_builds)
# stage_push = cli_wrap(stage_push)
# prod_push = cli_wrap(prod_push)
# self_check = cli_wrap(self_check)


@click.group()
# @click.option(
#     "--master-branch",
#     default=DEFAULT_MASTER_BRANCH,
#     help=f"name of main branch (default {DEFAULT_MASTER_BRANCH!r})",
# )
# @click.option(
#     "--upstream-name",
#     default=DEFAULT_UPSTREAM_NAME,
#     help=f"name of upstream remote (default {DEFAULT_UPSTREAM_NAME!r})",
# )
# @click.option(
#     "--submodules-upstream-name",
#     default=DEFAULT_SUBMODULES_UPSTREAM_NAME,
#     help=(
#         f"name of upstream remote in submodules "
#         f"(default {DEFAULT_SUBMODULES_UPSTREAM_NAME!r})"
#     ),
# )
@click.option("--debug/--no-debug", default=False)
@click.pass_context
def cli(
    ctx,
    # directory,
    debug,
    # name,
):
    ctx.ensure_object(dict)
    # ctx.obj["directory"] = directory
    ctx.obj["debug"] = debug
    # ctx.obj['name'] = name

    # p = Path(directory)
    # if not p.exists():
    #     error(f"{directory} does not exist")
    #     raise click.Abort


@cli.command()
@click.pass_context
# @cli_wrap
@click.option(
    "--name",
    default=None,
    help=f"Name of the site (default {DEFAULT_NAME_PATTERN!r})",
)
@click.option("--refresh/--no-refresh", default=False, help="Ignores checking if files exist already")
@click.argument("directory", nargs=-1, type=click.Path())
def upload(ctx, directory, name, refresh):
    print("HI")
    # upload(ctx.obj["directory"], ctx.obj)


@cli.command()
@click.pass_context
def version(ctx):
    info(pkg_resources.get_distribution("stumptown-deployer").version)
