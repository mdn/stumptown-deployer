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


# @dataclass(unsafe_hash=True)
@dataclass()
class UploadTask:
    """All the relevant information for doing an upload"""

    key: str
    file_path: Path
    size: int
    file_hash: str
    needs_hash_check: bool

    def __repr__(self):
        return repr(self.key)

    def set_file_hash(self):
        with open(self.file_path, "rb") as f:
            self.file_hash = hashlib.md5(f.read()).hexdigest()


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
    skipped = 0

    counts = {"uploaded": 0, "not_uploaded": 0}

    total_size = []

    def update_uploaded_stats(stats):
        counts["uploaded"] += stats["counts"].get("uploaded")
        counts["not_uploaded"] += stats["counts"].get("not_uploaded")
        total_size.append(stats["total_size_uploaded"])

    T0 = time.time()
    total_count = 0
    batch = []
    for fp in pwalk(directory):
        if is_junk_file(fp):
            skipped += 1
            continue
        # This assumes  that it can saved in S3 as a key that is the filename.
        key_path = fp.relative_to(directory)
        if key_path.name == "index.redirect":
            # Call these index.html when they go into S3
            key_path = key_path.parent / "index.html"
        key = str(key_path)

        size = fp.stat().st_size
        # with open(fp, "rb") as f:
        #     file_hash = hashlib.md5(f.read()).hexdigest()
        task = UploadTask(key, fp, size, None, False)
        if key not in uploaded_already or uploaded_already[key]["Size"] != size:
            # No doubt! We definitely didn't have this before or it's definitely
            # different.
            batch.append(task)

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
                # skipped.append(task)
                skipped += 1
                continue
            else:
                task.needs_hash_check = True
                batch.append(task)

        if len(batch) >= 1000:
            # Fire off these
            update_uploaded_stats(_start_uploads(s3, config, batch, transfer_config))
            total_count += len(batch)
            batch = []

    if batch:
        update_uploaded_stats(_start_uploads(s3, config, batch, transfer_config))
        total_count += len(batch)

    T1 = time.time()
    print(counts)
    success(f"Uploaded {fmt_size(sum(total_size))}.")
    success(f"Done in {fmt_seconds(T1 - T0)}.")


def _start_uploads(s3, config, batch, transfer_config):
    T0 = time.time()
    futures = {}
    total_threadpool_time = []
    # uploaded = {}
    counts = {"uploaded": 0, "not_uploaded": 0}
    total_size_uploaded = 0
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=MAX_WORKERS_PARALLEL_UPLOADS
    ) as executor:
        bucket_name = config["name"]
        quiet = config["quiet"]
        for task in batch:
            futures[
                executor.submit(
                    _upload_file_maybe,
                    s3,
                    task,
                    bucket_name,
                    transfer_config,
                    quiet=quiet,
                )
            ] = task

        for future in concurrent.futures.as_completed(futures):
            was_uploaded, took = future.result()
            task = futures[future]
            # uploaded[task] = (was_uploaded, took)
            total_threadpool_time.append(took)
            if was_uploaded:
                counts["uploaded"] += 1
            else:
                counts["not_uploaded"] += 1

    T1 = time.time()

    return {
        "counts": counts,
        "took": T1 - T0,
        "total_time": sum(total_threadpool_time),
        "total_size_uploaded": total_size_uploaded,
    }


def pwalk(start):
    for entry in os.scandir(start):
        if entry.is_dir():
            for p in pwalk(entry):
                yield p
        else:
            yield Path(entry)


def _upload_file_maybe(s3, task, bucket_name, transfer_config, quiet=False):
    t0 = time.time()
    if not task.file_hash:
        task.set_file_hash()
    if task.needs_hash_check:
        try:
            object_data = s3.head_object(Bucket=bucket_name, Key=task.key)
            if object_data["Metadata"].get("filehash") == task.file_hash:
                # We can bail early!
                t1 = time.time()
                if not quiet:
                    start = f"{fmt_size(task.size):} in {fmt_seconds(t1 - t0)}"
                    info(f"{'Skipped':<9} {start:>19} {task.key}")
                return False, t1 - t0
        except ClientError as error:
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            if error.response["Error"]["Code"] != "404":
                raise

            # If it really was a 404, it means that the method that gathered
            # the existing list is out of sync.

    mime_type = mimetypes.guess_type(str(task.file_path))[0] or "binary/octet-stream"

    if os.path.basename(task.file_path) == "service-worker.js":
        cache_control = "no-cache"
    else:
        cache_control_seconds = DEFAULT_CACHE_CONTROL
        if _has_hashed_filename(task.file_path):
            cache_control_seconds = HASHED_CACHE_CONTROL
        cache_control = f"max-age={cache_control_seconds}, public"

    ExtraArgs = {
        "ACL": "public-read",
        "ContentType": mime_type,
        "CacheControl": cache_control,
        "Metadata": {"filehash": task.file_hash},
    }
    if task.file_path.name == "index.redirect":
        with open(task.file_path) as f:
            redirect_url = f.read().strip()
            ExtraArgs["WebsiteRedirectLocation"] = redirect_url

    s3.upload_file(
        str(task.file_path),
        bucket_name,
        task.key,
        ExtraArgs=ExtraArgs,
        Config=transfer_config,
    )
    t1 = time.time()

    if not quiet:
        start = f"{fmt_size(task.size)} in {fmt_seconds(t1 - t0)}"
        info(
            f"{'Updated' if task.needs_hash_check else 'Uploaded':<9} "
            f"{start:>20} {task.key}"
        )
    return True, t1 - t0
