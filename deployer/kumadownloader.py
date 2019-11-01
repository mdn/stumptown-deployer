import concurrent.futures
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import boto3
from botocore.exceptions import ClientError

from .constants import AWS_PROFILE, MAX_WORKERS_PARALLEL_KUMADOWNLOADS


def download_kuma_s3_bucket(
    destination: Path,
    s3url: str,
    searchfilter: (str) = (),
    check_for_existence=False,
    refresh=False,
):
    session = boto3.Session(profile_name=AWS_PROFILE)
    s3 = session.client("s3")
    url_parsed = urlparse(s3url)
    bucket_name = url_parsed.netloc
    prefix = url_parsed.path[1:]
    assert s3.head_bucket(Bucket=bucket_name)

    etags_cache_file = destination / "_etags_cache.txt"
    new_files_file = destination / "_new_files.txt"

    downloaded_etags = {}
    try:
        with open(etags_cache_file) as f:
            for line in f:
                etag, rel_path = line.strip().split("\t", 1)
                downloaded_etags[etag] = rel_path
    except FileNotFoundError:
        # Starting afresh!
        pass

    if refresh:
        print("Ignoring any downloaded etags.")
    else:
        print(f"We know of {len(downloaded_etags):,} downloaded etags.")

    def exists(rel_path):
        return (destination / rel_path).exists()

    new_etags = {}

    continuation_token = None
    total_took = []
    total_cum_took = []
    total_size = []
    try:
        t0 = time.time()
        page = 1
        while True:
            # Have to do this so that 'ContinuationToken' can be omitted if falsy
            list_kwargs = dict(Bucket=bucket_name)
            if continuation_token:
                list_kwargs["ContinuationToken"] = continuation_token
            if prefix:
                list_kwargs["Prefix"] = prefix
            # list_kwargs["MaxKeys"] = 100

            response = s3.list_objects_v2(**list_kwargs)
            objs = response.get("Contents", [])
            todo = {}
            for obj in objs:
                key, etag = obj["Key"], obj["ETag"]
                if searchfilter:
                    # Skip this one unless one of the searchfilters match.
                    if not any([x in key for x in searchfilter]):
                        continue

                # There's only about 5 of these in existence.
                # https://github.com/mdn/kuma/issues/6076
                key = key.replace("//", "/")

                if (
                    refresh
                    or etag not in downloaded_etags
                    or (check_for_existence and not exists(downloaded_etags[etag]))
                ):
                    todo[key] = etag

            if todo:
                done, took, cum_took, size = download(
                    s3,
                    bucket_name,
                    destination,
                    todo,
                    max_workers=MAX_WORKERS_PARALLEL_KUMADOWNLOADS,
                )
                total_took.append(took)
                total_cum_took.append(cum_took)
                total_size.append(size)
                new_etags.update(done)

                print(
                    f"(Page {page:>3}) "
                    f"Downloaded {len(todo):,} files ({fmt_size(size)}) "
                    f"in {fmt_time(took)} (distributed {fmt_time(cum_took)})"
                )
            else:
                print(f"(Page {page:>3}) Nothing to do with in this batch")

            if response["IsTruncated"]:
                continuation_token = response["NextContinuationToken"]
            else:
                break
            page += 1
        t1 = time.time()
    finally:
        if new_etags:
            print(f"Discovered {len(new_etags):,} NEW keys.")

            # Also write a new file exclusively for the new ones
            with open(new_files_file, "w") as f:
                for rel_path in new_etags.values():
                    f.write(f"{rel_path}\n")
            print(f"Wrote down {len(new_etags):,} in {new_files_file}")

            downloaded_etags.update(new_etags)
            # Write down everything!
            count_lines = 0
            with open(etags_cache_file, "w") as f:
                for etag, rel_path in downloaded_etags.items():
                    f.write(f"{etag}\t{rel_path}\n")
                    count_lines += 1
            print(f"Wrote {count_lines:,} lines to {etags_cache_file}")

        else:
            print("No new keys downloaded.")

    print(f"Total time {fmt_time(t1 - t0)}.")
    print(f"Total download size {fmt_size(sum(total_size))}.")


def fmt_time(seconds):
    if seconds < 1:
        return f"{seconds * 1000:.2f}ms"
    elif seconds > 60:
        return f"{seconds/60:.0f}m{seconds % 60:.0f}s"
    return f"{seconds:.1f}s"


def fmt_size(b):
    if b > 1024 * 1024 * 1024:
        return f"{b / 1024 / 1024 / 1024:.1f}GB"
    if b > 1024 * 1024:
        return f"{b / 1024 / 1024:.1f}MB"
    if b > 1024:
        return f"{b / 1024:.1f}KB"
    return f"{b}B"


def download(s3, bucket_name, destination, todo, max_workers=None):
    # Mapping of Etag to relative path on disk
    done = {}

    T0 = time.time()

    # First create all the necessary directories
    directories: {Path} = set()
    for key in todo:
        directories.add(destination / Path(unquote(key)).parent)

    # Do this synchronously first to avoid race conditions, in the thread pool,
    # of trying to create the same directory.
    for directory in directories:
        directory.mkdir(exist_ok=True, parents=True)

    futures = {}
    total_threadpool_time = []
    total_threadpool_size = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for key in todo:
            futures[
                executor.submit(_download_file, s3, bucket_name, key, destination)
            ] = key

        for future in concurrent.futures.as_completed(futures):
            path, took = future.result()
            key = futures[future]
            done[todo[key]] = path.relative_to(destination)
            # print(key, "TOOK", took)
            total_threadpool_time.append(took)
            total_threadpool_size.append(path.stat().st_size)

    T1 = time.time()
    return done, T1 - T0, sum(total_threadpool_time), sum(total_threadpool_size)


def _download_file(s3, bucket_name: str, key: str, destination: Path):
    t0 = time.time()
    file_destination = destination / Path(unquote(key))
    with open(file_destination, "wb") as f:
        try:
            s3.download_fileobj(bucket_name, key, f)
        except ClientError as error:
            if error.response["Error"]["Code"] == "404":
                print(f"Warning! Key {key} no longer exists in the bucket. Ignoring.")
            else:
                raise
    t1 = time.time()
    return file_destination, t1 - t0
