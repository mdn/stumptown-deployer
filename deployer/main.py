import functools
import pkg_resources
from pathlib import Path

import click

from .constants import DEFAULT_NAME_PATTERN
from .exceptions import CoreException
from .upload import upload_site
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


@click.group()
@click.option("--debug/--no-debug", default=False)
@click.pass_context
def cli(ctx, debug):
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug


@cli.command()
@click.pass_context
@cli_wrap
@click.option(
    "--name", default=None, help=f"Name of the site (default {DEFAULT_NAME_PATTERN!r})"
)
@click.option(
    "--refresh/--no-refresh",
    default=False,
    help="Ignores checking if files exist already",
)
@click.argument("directory", type=click.Path())
def upload(ctx, directory, name, refresh):
    p = Path(directory)
    if not p.exists():
        error(f"{directory} does not exist")
        raise click.Abort

    ctx.obj["name"] = name
    ctx.obj["refresh"] = refresh
    upload_site(directory, ctx.obj)


@cli.command()
@click.pass_context
def version(ctx):
    info(pkg_resources.get_distribution("stumptown-deployer").version)
