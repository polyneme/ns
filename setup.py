import setuptools

with open("README.md") as f:
    long_description = f.read()

setuptools.setup(
    name="xyz_polyneme_ns",
    url="https://github.com/polyneme/ns",
    packages=setuptools.find_packages(exclude=["tests"]),
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    author="Donny Winston",
    author_email="donny@polyneme.xyz",
    description="A namespace manager and ARK resolver service",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "termeric = xyz_polyneme_ns.cli.main:app",
        ]
    },
)
