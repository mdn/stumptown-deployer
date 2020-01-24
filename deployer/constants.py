import json
import sys
import os

from decouple import AutoConfig

config = AutoConfig(os.curdir)

DEFAULT_BUCKET = config("DEPLOYER_DEFAULT_BUCKET", "yari")

DEFAULT_NAME_PATTERN = config(
    "DEPLOYER_DEFAULT_NAME_PATTERN", "{username}-{branchname}"
)

AWS_PROFILE = config("AWS_PROFILE", default="default")

# E.g. us-east-1
S3_DEFAULT_BUCKET_LOCATION = config("S3_DEFAULT_BUCKET_LOCATION", default="")

# When uploading a bunch of files, the work is done in a thread pool.
# If you use too many "workers" it might saturate your network meaning it's
# slower.
MAX_WORKERS_PARALLEL_UPLOADS = config(
    "DEPLOYER_MAX_WORKERS_PARALLEL_UPLOADS", default=50, cast=int
)

# E.g. /en-US/docs/Foo/Bar/index.html
DEFAULT_CACHE_CONTROL = config(
    "DEPLOYER_DEFAULT_CACHE_CONTROL", default=60 * 60, cast=int
)
# E.g. '2.02b14290.chunk.css'
HASHED_CACHE_CONTROL = config(
    "DEPLOYER_HASHED_CACHE_CONTROL", default=60 * 60 * 24 * 365, cast=int
)


DEFAULT_NO_PROGRESS_BAR = config(
    "NO_PROGRESS_BAR",
    cast=bool,
    default=not sys.stdout.isatty() or bool(json.loads(os.environ.get("CI", "0"))),
)
