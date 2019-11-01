import functools
import pkg_resources
from pathlib import Path

import click

from .constants import DEFAULT_NAME_PATTERN
from .exceptions import CoreException
from .upload import upload_site
from .kumadownloader import download_kuma_s3_bucket
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
    "--refresh",
    default=False,
    help="Ignores checking if files exist already",
    show_default=True,
    is_flag=True,
)
@click.option(
    "-l",
    "--lifecycle-days",
    required=False,
    type=int,
    help="If specified, the number of days until uploaded objects are deleted",
)
@click.argument("directory", type=click.Path())
def upload(ctx, directory, name, refresh, lifecycle_days):
    p = Path(directory)
    if not p.exists():
        error(f"{directory} does not exist")
        raise click.Abort

    ctx.obj["name"] = name
    ctx.obj["refresh"] = refresh
    ctx.obj["lifecycle_days"] = lifecycle_days
    upload_site(directory, ctx.obj)


@cli.command()
@click.pass_context
@cli_wrap
@click.option(
    "--s3url", help="URL to S3 bucket", default="s3://mdn-api-prod/", show_default=True
)
@click.option(
    "-s",
    "--searchfilter",
    help="string that must appear in S3 key",
    default="",
    multiple=True,
)
@click.option(
    "--check-for-existence",
    help="Even if ETag is in the cache file, check that the destination file exists",
    default=False,
    show_default=True,
    is_flag=True,
)
@click.option(
    "--refresh",
    default=False,
    help="Ignores checking if files exist already or is cached",
    show_default=True,
    is_flag=True,
)
@click.argument("destination", type=click.Path())
def kumadownload(
    ctx,
    destination,
    s3url,
    searchfilter: (str) = (),
    check_for_existence=False,
    refresh=False,
):
    p = Path(destination)
    p.is_dir() or p.mkdir()
    download_kuma_s3_bucket(
        p,
        s3url,
        searchfilter=searchfilter,
        check_for_existence=check_for_existence,
        refresh=refresh,
    )


@cli.command()
@click.pass_context
def version(ctx):
    info(pkg_resources.get_distribution("stumptown-deployer").version)
