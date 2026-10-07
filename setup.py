from setuptools import setup, find_packages

with open("requirements.txt", "r") as f:
    install_requires = [line.strip() for line in f if line.strip()]

setup(
    name="accelerator_laserai",
    version="0.1.0",
    description="accelerator source laserai spreadsheet ingest",
    author="Mike Conway",
    author_email="mike.conway@nih.gov",
    url="https://github.com/NIEHS/accelerator_laserai",
    packages=find_packages(),
    install_requires=[open("requirements.txt").read()],
    license="BSD 3-Clause",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    package_data={"accelerator_laserai": ["accelerator_laserai/templates/*.jinja", "accelerator_laserai/resources/*"]},
    include_package_data=True,
)
