import functools
import pkg_resources
from pathlib import Path

import click

from .constants import (
    DEFAULT_NAME_PATTERN,
    DEFAULT_BUCKET,
    S3_DEFAULT_BUCKET_LOCATION,
    DEFAULT_NO_PROGRESS_BAR,
)
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
    "--bucket",
    default=DEFAULT_BUCKET,
    help=f"Name of the bucket (default {DEFAULT_BUCKET!r})",
)
@click.option(
    "--name", default=None, help=f"Name of the site (default {DEFAULT_NAME_PATTERN!r})"
)
@click.option(
    "--bucket-location",
    default=S3_DEFAULT_BUCKET_LOCATION,
    help=f"Name of the bucket (default {S3_DEFAULT_BUCKET_LOCATION!r})",
)
@click.option(
    "--refresh",
    default=False,
    help="Ignores checking if files exist already",
    show_default=True,
    is_flag=True,
)
@click.option(
    "--bucket-lifecycle-days",
    required=False,
    type=int,
    help=(
        "If specified, the number of days until uploaded objects are deleted. "
        "(Only applicable when buckets are created!)"
    ),
)
@click.option(
    "--dry-run",
    default=False,
    help="No actual uploading",
    show_default=True,
    is_flag=True,
)
@click.option(
    "--no-progress-bar",
    default=DEFAULT_NO_PROGRESS_BAR,
    help="Don't use an iteractive progress bar",
    show_default=True,
    is_flag=True,
)
@click.argument("directory", type=click.Path())
def upload(ctx, directory, **kwargs):
    p = Path(directory)
    if not p.exists():
        error(f"{directory} does not exist")
        raise click.Abort

    ctx.obj.update(kwargs)
    upload_site(directory, ctx.obj)


@cli.command()
@click.pass_context
def version(ctx):
    info(pkg_resources.get_distribution("stumptown-deployer").version)
