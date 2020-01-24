# stumptown-deployer

Ship a Stumptown static site for web hosting.

Don't tell anyone, but for now it's all AWS as the backend but that's an
implementation detail that shouldn't prevent us from one day moving to Google Cloud
Platform or Azure or Fastly.

## Limitations and caveats

- Redirects - in the build directory we're supposed to have `/en-us/_redirects.txt`

- Preferred names - file systems might not be allowed to call a folder a certain thing
  but that's not necessarily what we want the key to be called in S3.

- GitHub integration

## How it works

This project's goal is ultimately to take a big directory of files and upload them to
S3. But there are some more advanced features so as turning `_redirects.txt` files
into S3 redirect keys. And there might be file system names that don't match exactly
what we need the S3 key to be called exactly. Also, the directory is bound to contain
"junk" that should be omitted. For example, Yari produces `index.hash` files which
are used to remember the checksum when it built the `index.html`.

All deployments, generally, all go into the one same S3 bucket. But in that bucket
you always have a "prefix" (aka. a root folder) which gets used by CloudFront so you
can have N CloudFront distributions for 1 S3 bucket. For example, one prefix might
be called `master` which'll be the production site. Another prefix might be
`peterbe-pr12345`.

So every deployment has a prefix (aka. the "name") which can be automatically
generated based on the name of the current branch, which'd be known to something
like TravisCI. The first thing it does is that it downloads a complete listing of
every known key in the bucket under that prefix and each key's size. (That's all
you get from `bucket.list_objects_v2`). Now, it starts to walk the local directory
and for each _file_ it applies the following logic:

- Does it S3 key _not_ exist at all? --> Upload brand new S3 key!
- Does the S3 key _exist_?
  - Is the file size different from the S3 key size? --> Upload changed S3 key!
  - Is the file size exactly the same as the S3 key size? --> Download the
    S3 key's `Metadata->filehash`.
    - Is the hash exactly the same as the file's hash? --> Do nothing!
    - Is the hash different? --> Upload changed S3 key!

When it uploads an S3 key, _always_ compute the local file's hash and include that
as a piece of S3 key Metadata.

## Getting started

You can install it globally or in a virtualen environment. Whatever floats
float fancy.

    pip install stumptown-deployer
    stumptown-deployer --help

Please refer to the [`boto3` documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/quickstart.html#configuration) with regards to configuring AWS access
credentials.

## Goal

To be dead-easy to use and powerful at the same time.

## Contributing

Clone this repo then run:

    pip install -e ".[dev]"

That should have installed the CLI `stumptown-deployer`

    stumptown-deployer --help

If you wanna make a PR, make sure it's formatted with `black` and passes `flake8`.

You can check that all files are `flake8` fine by running:

    flake8 deployer

And to check that all files are formatted according to `black` run:

    black --check deployer

All of the code style stuff can be simplified by installing `therapist`. It should
get installed by default, but setting it up as a `git` `pre-commit` hook is optional.
Here's how you set it up once:

    therapist install

Now, next time you try to commit a `.py` file with a `black` or `flake8` violation
it will remind you and block the commit. You can override it like this:

    git commit -a -m "I know what I'm doing"

To run _all_ code style and lint checkers you can also use `therapist` with:

    therapist run --use-tracked-files

Some things can't be automatically fixed, but `black` violations can for example:

    therapist run --use-tracked-files --fix

## Contributing and using

If you like to use the globally installed executable `stumptown-deployer`
but don't want to depend on a new PyPI release for every change you want
to try, use this:

    # If you use a virtualenv, deactivate it first
    deactive
    # Use the global pip (or pip3) on your system
    pip3 install -e .

If you do this, you can use this repo to install in your system.
