
from invoke import task


@task
def build(ctx):
    ctx.run("python3 setup.py sdist bdist_wheel")


@task
def upload(ctx):
    ctx.run("twine upload dist/*")
