import os

from decouple import AutoConfig

config = AutoConfig(os.curdir)


DEFAULT_NAME_PATTERN = config(
    "DEPLOYER_DEFAULT_NAME_PATTERN", "stumptown-{username}-{branchname}-{date}"
)

AWS_PROFILE = config("AWS_PROFILE", default="default")

# E.g. us-east-1
S3_DEFAULT_BUCKET_LOCATION = config("S3_DEFAULT_BUCKET_LOCATION", default="")

# When uploading a bunch of files, the work is done in a thread pool.
# If you use too many "workers" it might saturate your network meaning it's
# slower.
MAX_WORKERS_PARALLEL_UPLOADS = config(
    "DEPLOYER_MAX_WORKERS_PARALLEL_UPLOADS", default=10, cast=int
)
