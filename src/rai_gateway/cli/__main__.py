"""
RAI Gateway CLI Entry Point

Usage:
    python -m rai_gateway.cli admin create
    python -m rai_gateway.cli admin list

Or if installed as a package:
    rai-admin create
    rai-admin list
"""

import click

from rai_gateway.cli.admin import admin
from rai_gateway.cli.orphan_cleanup import orphan_cleanup


@click.group()
@click.version_option(version="0.1.0", prog_name="rai-gateway")
def cli():
    """RAI Gateway CLI - Administration and operations tools."""
    pass


# Register command groups
cli.add_command(admin)
cli.add_command(orphan_cleanup)


if __name__ == "__main__":
    cli()
