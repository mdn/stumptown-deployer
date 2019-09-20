# stumptown-deployer

Ship a Stumptown static site for web hosting.

Don't tell anyone, but for now it's all AWS as the backend but that's an
implementation detail.

## Limitations and caveats

* Redirects

* GitHub integration

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
