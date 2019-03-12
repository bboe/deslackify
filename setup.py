"""deslackify setup.py."""
import re
from codecs import open
from os import path
from setuptools import setup


PACKAGE_NAME = "deslackify"
HERE = path.abspath(path.dirname(__file__))
with open(path.join(HERE, "README.md"), encoding="utf-8") as fp:
    README = fp.read()
with open(
    path.join(HERE, PACKAGE_NAME, "__init__.py"), encoding="utf-8"
) as fp:
    VERSION = re.search("__version__ = '([^']+)'", fp.read()).group(1)


extras_require = {
    "dev": ["pre-commit"],
    "lint": ["black", "flake8"],
    "test": ["pytest"],
}
extras_require["dev"] = sorted(set(sum(extras_require.values(), [])))


setup(
    name=PACKAGE_NAME,
    author="Bryce Boe",
    author_email="bbzbryce@gmail.com",
    classifiers=[
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
    ],
    description="A program to delete old slack messages.",
    entry_points={"console_scripts": ["deslackify = deslackify:main"]},
    extras_require=extras_require,
    install_requires=["slacker >=0.12, <0.13"],
    keywords="slack",
    license="Simplified BSD License",
    long_description=README,
    long_description_content_type="text/markdown",
    packages=[PACKAGE_NAME],
    url="https://github.com/bboe/deslackify",
    version=VERSION,
)
