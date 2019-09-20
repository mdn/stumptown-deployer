import os
from pathlib import Path

import click


def error(*msg):
    msg = " ".join([str(x) for x in msg])
    click.echo(click.style(msg, fg="red"))


def warning(*msg):
    msg = " ".join([str(x) for x in msg])
    click.echo(click.style(msg, fg="yellow"))


def info(*msg):
    msg = " ".join([str(x) for x in msg])
    click.echo(click.style(msg))


def success(*msg):
    msg = " ".join([str(x) for x in msg])
    click.echo(click.style(msg, fg="green"))


def ppath(path, current_dir=None):
    current_dir = current_dir or os.curdir
    p = Path(path)
    return str(p.relative_to(current_dir))
