from setuptools import setup
import os
import sys

this_dir = os.path.abspath(os.path.dirname(__file__))
description = "pynose fixes nose to extend unittest and make testing easier"
long_description = None
total_description = None
try:
    with open(os.path.join(this_dir, "README.md"), "rb") as f:
        total_description = f.read().decode("utf-8")
    description_lines = total_description.split("\n")
    long_description_lines = []
    for line in description_lines:
        if not line.startswith("<meta ") and not line.startswith("<link "):
            long_description_lines.append(line)
    long_description = "\n".join(long_description_lines)
except IOError:
    long_description = description

about = {}
# Get the package version from the nose/__version__.py file
with open(os.path.join(this_dir, "nose", "__version__.py"), "rb") as f:
    exec(f.read().decode("utf-8"), about)
VERSION = about["__version__"]

if sys.argv[-1] == "publish":
    reply = None
    input_method = input
    confirm_text = ">>> Confirm release PUBLISH to PyPI? (yes/no): "
    reply = str(input_method(confirm_text)).lower().strip()
    if reply == "yes":
        if sys.version_info < (3, 9):
            print("\nERROR! Publishing to PyPI requires Python>=3.9")
            sys.exit()
        print("\n*** Checking code health with flake8:\n")
        os.system("python -m pip install 'flake8==6.1.0'")
        flake8_status = os.system("flake8 --exclude=recordings,temp")
        if flake8_status != 0:
            print("\nERROR! Fix flake8 issues before publishing to PyPI!\n")
            sys.exit()
        else:
            print("*** No flake8 issues detected. Continuing...")
        print("\n*** Removing existing distribution packages: ***\n")
        os.system("rm -f dist/*.egg; rm -f dist/*.tar.gz; rm -f dist/*.whl")
        os.system("rm -rf build/bdist.*; rm -rf build/lib")
        print("\n*** Installing build: *** (Required for PyPI uploads)\n")
        os.system("python -m pip install --upgrade 'build'")
        print("\n*** Installing pkginfo: *** (Required for PyPI uploads)\n")
        os.system("python -m pip install --upgrade 'pkginfo'")
        print("\n*** Installing readme-renderer: *** (For PyPI uploads)\n")
        os.system("python -m pip install --upgrade 'readme-renderer'")
        print("\n*** Installing jaraco.classes: *** (For PyPI uploads)\n")
        os.system("python -m pip install --upgrade 'jaraco.classes'")
        print("\n*** Installing more-itertools: *** (For PyPI uploads)\n")
        os.system("python -m pip install --upgrade 'more-itertools'")
        print("\n*** Installing zipp: *** (Required for PyPI uploads)\n")
        os.system("python -m pip install --upgrade 'zipp'")
        print("\n*** Installing importlib-metadata: *** (For PyPI uploads)\n")
        os.system("python -m pip install --upgrade 'importlib-metadata'")
        print("\n*** Installing keyring, requests-toolbelt: *** (For PyPI)\n")
        os.system("python -m pip install --upgrade keyring requests-toolbelt")
        print("\n*** Installing twine: *** (Required for PyPI uploads)\n")
        os.system("python -m pip install --upgrade 'twine'")
        print("\n*** Rebuilding distribution packages: ***\n")
        os.system("python -m build")  # Create new tar/wheel
        print("\n*** Publishing The Release to PyPI: ***\n")
        os.system("python -m twine upload dist/*")  # Requires ~/.pypirc Keys
        print("\n*** The Release was PUBLISHED SUCCESSFULLY to PyPI! :) ***\n")
    else:
        print("\n>>> The Release was NOT PUBLISHED to PyPI! <<<\n")
    sys.exit()

addl_args = {
    "packages": ["nose", "nose.plugins", "nose.sphinx", "nose.tools"],
    "entry_points": {
        "console_scripts": [
            "nosetests = nose.core:run_exit",
            "pynose = nose.core:run_exit",
        ]
    },
}

setup(
    name="pynose",
    version=VERSION,
    author="Michael Mintz",
    author_email="mdmintz@gmail.com",
    description=description,
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    keywords="test unittest doctest automatic discovery",
    url="https://github.com/mdmintz/pynose",
    project_urls={
        "Download": "https://pypi.org/project/pynose/#files",
        "PyPI": "https://pypi.org/project/pynose/",
        "Source": "https://github.com/mdmintz/pynose",
        "Documentation": "https://nose.readthedocs.io/en/latest/",
    },
    package_data={"": ["*.txt"]},
    python_requires=">=3.6",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Environment :: MacOS X",
        "Environment :: Win32 (MS Windows)",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Testing",
    ],
    **addl_args
)
