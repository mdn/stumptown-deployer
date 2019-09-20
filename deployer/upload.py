import datetime
import os
import time
import getpass
import shutil
import mimetypes
from pathlib import Path
import concurrent.futures

import boto3
import git

from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError
from git.exc import InvalidGitRepositoryError

from .constants import (
    AWS_PROFILE,
    DEFAULT_NAME_PATTERN,
    S3_DEFAULT_BUCKET_LOCATION,
    MAX_WORKERS_PARALLEL_UPLOADS,
)
from .exceptions import NoGitDirectory
from .utils import info, is_junk_file, ppath, success, warning, fmt_size, fmt_seconds


def center(msg):
    t_width, _ = shutil.get_terminal_size(fallback=(80, 24))
    warning(f"-----  {msg}  ".ljust(t_width, "-"))


def _find_git_repo(start):
    if str(start) == str(start.root):
        raise NoGitDirectory
    try:
        return git.Repo(start)
    except InvalidGitRepositoryError:
        return _find_git_repo(Path(start).parent)


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
        config["name"] = DEFAULT_NAME_PATTERN.format(
            username=getpass.getuser(),
            branchname=active_branch.name,
            date=datetime.datetime.utcnow().strftime("%Y%m%d"),
        )
    info(f"About to upload {ppath(directory)} to {config['name']}")

    session = boto3.Session(profile_name=AWS_PROFILE)
    s3 = session.client("s3")

    # First make sure the bucket exists
    try:
        s3.head_bucket(Bucket=config["name"])
        # # print("BUCKET;;", repr(bucket), type(bucket))
        # bucket_policy = s3.get_bucket_acl(Bucket=config["name"])
        # info(f"Bucket policy: {bucket_policy}")
        # if config["debug"]:
        #     info(f"Bucket policy: {bucket_policy}")
    except ClientError as error:
        # If a client error is thrown, then check that it was a 404 error.
        # If it was a 404 error, then the bucket does not exist.
        if error.response["Error"]["Code"] != "404":
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

    try:
        website_bucket = s3.get_bucket_website(Bucket=config["name"])
    except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchWebsiteConfiguration":
            raise
        # Define the website configuration
        website_configuration = {
            "ErrorDocument": {"Key": "error.html"},
            "IndexDocument": {"Suffix": "index.html"},
        }
        website_bucket = s3.put_bucket_website(
            Bucket=config["name"],
            WebsiteConfiguration=website_configuration,
            # XXX Would be nice to set expiration here
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

    to_upload = []
    for fp in directory.glob("**/*.*"):
        key = str(fp.relative_to(directory))
        name = str(fp)
        size = os.stat(fp).st_size
        task = (key, name, size)
        if is_junk_file(fp):
            skipped.append(task)
            continue

        if key not in uploaded_already or uploaded_already[key]["Size"] != size:
            to_upload.append((key, name, size))
        else:
            skipped.append(task)

    def _upload_file(s3, filepath, size, bucket_name, object_name, global_progress):
        t0 = time.time()
        mime_type = mimetypes.guess_type(filepath)[0] or "binary/octet-stream"
        # print(os.path.basename(filepath), "-->", mime_type)
        s3.upload_file(
            filepath,
            config["name"],
            object_name,
            ExtraArgs={"ACL": "public-read", "ContentType": mime_type},
            Config=transfer_config,
        )
        t1 = time.time()
        info(f"Uploaded {object_name} ({fmt_size(size)}) in {fmt_seconds(t1 - t0)}")
        return t1 - t0

    global_progress = {}
    T0 = time.time()
    futures = {}
    total_threadpool_time = []
    uploaded = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=MAX_WORKERS_PARALLEL_UPLOADS
    ) as executor:
        info(f"About to upload {len(to_upload):,} files")
        for key, filepath, size in to_upload:
            futures[
                executor.submit(
                    _upload_file,
                    s3,
                    filepath,
                    size,
                    config["name"],
                    key,
                    global_progress,
                )
            ] = (key, filepath, size)

        for future in concurrent.futures.as_completed(futures):
            took = future.result()
            task = futures[future]
            uploaded[task] = took
            total_threadpool_time.append(took)

    T1 = time.time()

    if skipped:
        warning(f"Skipped uploading {len(skipped):,} files")

    if uploaded:
        total_uploaded_size = sum([x[2] for x in uploaded])
        success(
            f"Uploaded {len(uploaded):,} files "
            f"(totalling {fmt_size(total_uploaded_size)}) "
            f"in {fmt_seconds(T1 - T0)} "
            f"(~{fmt_size(total_uploaded_size / 60)}/s)"
        )
        if total_threadpool_time:
            info(
                "Sum of time to upload in thread pool "
                f"{fmt_seconds(sum(total_threadpool_time))}"
            )
