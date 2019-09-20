class CoreException(Exception):
    """Exists for the benefit of making the cli easier to catch exceptions."""


class NoGitDirectory(CoreException):
    """When trying to find a/the git directory and failing."""
