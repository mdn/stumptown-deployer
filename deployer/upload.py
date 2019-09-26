import concurrent.futures
import datetime
import getpass
import hashlib
import mimetypes
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import boto3
import git
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError
from git.exc import InvalidGitRepositoryError

from .constants import (
    AWS_PROFILE,
    DEFAULT_CACHE_CONTROL,
    DEFAULT_NAME_PATTERN,
    HASHED_CACHE_CONTROL,
    MAX_WORKERS_PARALLEL_UPLOADS,
    S3_DEFAULT_BUCKET_LOCATION,
)
from .exceptions import NoGitDirectory
from .utils import fmt_seconds, fmt_size, info, is_junk_file, ppath, success, warning

hashed_filename_regex = re.compile(r"\.[a-f0-9]{8,32}\.")


def _find_git_repo(start):
    if str(start) == str(start.root):
        raise NoGitDirectory
    try:
        return git.Repo(start)
    except InvalidGitRepositoryError:
        return _find_git_repo(Path(start).parent)


def _has_hashed_filename(fn):
    return hashed_filename_regex.findall(os.path.basename(fn))


@dataclass(unsafe_hash=True)
class UploadTask:
    """All the relevant information for doing an upload"""

    key: str
    file_path: str
    size: int
    file_hash: str

    def __repr__(self):
        return repr(self.key)


def upload_site(directory, config):
    if isinstance(directory, str):
        directory = Path(directory)
    if not config.get("name"):
        try:
            repo = _find_git_repo(directory)
        except NoGitDirectory:
            raise NoGitDirectory(
                f"From {directory} can't find its git root directory "
                "which is needed to supply a default branchname."
            )
        active_branch = repo.active_branch
        if active_branch == "master" and config["lifecycle_days"]:
            warning(
                f"Warning! You're setting a lifecycle_days "
                f"({config['lifecycle_days']} days) on a build from a 'master' repo."
            )
        config["name"] = DEFAULT_NAME_PATTERN.format(
            username=getpass.getuser(),
            branchname=active_branch.name,
            date=datetime.datetime.utcnow().strftime("%Y%m%d"),
        )
    info(f"About to upload {ppath(directory)} to bucket {config['name']!r}")

    session = boto3.Session(profile_name=AWS_PROFILE)
    s3 = session.client("s3")

    # First make sure the bucket exists
    try:
        s3.head_bucket(Bucket=config["name"])
    except ClientError as error:
        # If a client error is thrown, then check that it was a 404 error.
        # If it was a 404 error, then the bucket does not exist.
        if error.response["Error"]["Code"] != "404":
            print(error.response)
            raise

        # Needs to be created.
        bucket_config = {}
        if S3_DEFAULT_BUCKET_LOCATION:
            bucket_config["LocationConstraint"] = "us-west-1"
        s3.create_bucket(
            Bucket=config["name"],
            ACL="public-read",
            CreateBucketConfiguration=bucket_config,
        )

    if config["lifecycle_days"]:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.put_bucket_lifecycle_configuration
        # https://docs.aws.amazon.com/code-samples/latest/catalog/python-s3-put_bucket_lifecyle_configuration.py.html
        s3.put_bucket_lifecycle_configuration(
            Bucket=config["name"],
            LifecycleConfiguration={
                "Rules": [
                    {
                        "Expiration": {"Days": config["lifecycle_days"]},
                        "Filter": {"Prefix": ""},
                        "Status": "Enabled",
                    }
                ]
            },
        )

    try:
        website_bucket = s3.get_bucket_website(Bucket=config["name"])
    except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchWebsiteConfiguration":
            raise
        # Define the website configuration
        website_configuration = {
            "ErrorDocument": {"Key": "404.html"},
            "IndexDocument": {"Suffix": "index.html"},
            "RoutingRules": [
                {
                    "Condition": {"KeyPrefixEquals": "/"},
                    "Redirect": {"ReplaceKeyWith": "index.html"},
                }
            ],
        }
        website_bucket = s3.put_bucket_website(
            Bucket=config["name"], WebsiteConfiguration=website_configuration
        )
        info(f"Created website bucket called {config['name']}")

    if config["debug"]:
        info(f"Website bucket: {website_bucket!r}")

    uploaded_already = {}

    if config["refresh"]:
        info("Refresh, so ignoring what was previously uploaded.")
    else:
        continuation_token = None
        while True:
            # Have to do this so that 'ContinuationToken' can be omitted if falsy
            list_kwargs = dict(Bucket=config["name"])
            if continuation_token:
                list_kwargs["ContinuationToken"] = continuation_token
            response = s3.list_objects_v2(**list_kwargs)
            for obj in response.get("Contents", []):
                uploaded_already[obj["Key"]] = obj
            if response["IsTruncated"]:
                continuation_token = response["NextContinuationToken"]
            else:
                break

        warning(f"{len(uploaded_already):,} files already uploaded.")

    transfer_config = TransferConfig()
    skipped = []

    to_upload_maybe = []
    to_upload_definitely = []
    for fp in directory.glob("**/*.*"):
        key = str(fp.relative_to(directory))
        # name = str(fp)
        size = os.stat(fp).st_size
        with open(fp, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        task = UploadTask(key, str(fp), size, file_hash)
        if is_junk_file(fp):
            skipped.append(task)
            continue

        if key not in uploaded_already or uploaded_already[key]["Size"] != size:
            # No doubt! We definitely didn't have this before or it's definitely
            # different.
            to_upload_definitely.append(task)
        else:
            # At this point, the key exists and the size hasn't changed.
            # However, for some files, that's not conclusive.
            # Image, a 'index.html' file might have this as its diff:
            #
            #    - <script src=/foo.a9bef19a0.js></script>
            #    + <script src=/foo.3e98ca01d.js></script>
            #
            # ...which means it definitely has changed but the file size is
            # exactly the same as before.
            # If this is the case, we're going to *maybe* upload it.
            # However, for files that are already digest hashed, we don't need
            # to bother checking.
            if _has_hashed_filename(key):
                skipped.append(task)
            else:
                to_upload_maybe.append(task)

    T0 = time.time()
    futures = {}
    total_threadpool_time = []
    uploaded = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=MAX_WORKERS_PARALLEL_UPLOADS
    ) as executor:

        if to_upload_maybe:
            info("About to consider " f"{len(to_upload_maybe):,} files")
        if to_upload_definitely:
            info("About to upload " f"{len(to_upload_definitely):,} files")

        bucket_name = config["name"]
        for list_, check_hash_first in (
            (to_upload_definitely, False),
            (to_upload_maybe, True),
        ):
            for task in list_:
                futures[
                    executor.submit(
                        _upload_file_maybe,
                        s3,
                        task,
                        bucket_name,
                        transfer_config,
                        check_hash_first,
                    )
                ] = task

        for future in concurrent.futures.as_completed(futures):
            was_uploaded, took = future.result()
            task = futures[future]
            uploaded[task] = (was_uploaded, took)
            total_threadpool_time.append(took)

    T1 = time.time()

    actually_uploaded = [k for k, v in uploaded.items() if v[0]]
    actually_skipped = [k for k, v in uploaded.items() if not v[0]]

    if skipped or actually_skipped:
        warning(f"Skipped uploading {len(skipped) + len(actually_skipped):,} files")

    if uploaded:
        if actually_uploaded:
            total_uploaded_size = sum([x.size for x in actually_uploaded])
            success(
                f"Uploaded {len(actually_uploaded):,} "
                f"{'file' if len(actually_uploaded) == 1 else 'files'} "
                f"(totalling {fmt_size(total_uploaded_size)}) "
                f"(~{fmt_size(total_uploaded_size / 60)}/s)"
            )

        if total_threadpool_time:
            info(
                "Sum of time to upload in thread pool "
                f"{fmt_seconds(sum(total_threadpool_time))}"
            )

    success(f"Done in {fmt_seconds(T1 - T0)}")

    return {"uploaded": uploaded, "skipped": skipped, "took": T1 - T0}


def _upload_file_maybe(s3, task, bucket_name, transfer_config, check_hash_first=False):
    t0 = time.time()

    if check_hash_first:
        try:
            object_data = s3.head_object(Bucket=bucket_name, Key=task.key)
            if object_data["Metadata"].get("filehash") == task.file_hash:
                # We can bail early!
                t1 = time.time()
                start = f"{fmt_size(task.size):} in {fmt_seconds(t1 - t0)}"
                info(f"Skipped  {start:>19}  {task.key}")
                return False, t1 - t0
        except ClientError as error:
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            if error.response["Error"]["Code"] != "404":
                raise

            # If it really was a 404, it means that the method that gathered
            # the existing list is out of sync.

    mime_type = mimetypes.guess_type(task.file_path)[0] or "binary/octet-stream"

    if os.path.basename(task.file_path) == "service-worker.js":
        cache_control = "no-cache"
    else:
        cache_control_seconds = DEFAULT_CACHE_CONTROL
        if _has_hashed_filename(task.file_path):
            cache_control_seconds = HASHED_CACHE_CONTROL
        cache_control = f"max-age={cache_control_seconds}, public"

    s3.upload_file(
        task.file_path,
        bucket_name,
        task.key,
        ExtraArgs={
            "ACL": "public-read",
            "ContentType": mime_type,
            "CacheControl": cache_control,
            "Metadata": {"filehash": task.file_hash},
        },
        Config=transfer_config,
    )
    t1 = time.time()

    start = f"{fmt_size(task.size)} in {fmt_seconds(t1 - t0)}"
    info(f"{'Updated' if check_hash_first else 'Uploaded'} {start:>20}  {task.key}")
    return True, t1 - t0
