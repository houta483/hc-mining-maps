"""Setup script for Box to Google Earth Pipeline."""

from setuptools import find_packages, setup

setup(
    name="borehole-analysis-pipeline",
    version="1.0.0",
    description="Automated pipeline for processing Box Excel files to Google Earth",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "boxsdk>=3.9.0",
        "openpyxl>=3.1.2",
        "pandas>=2.1.0",
        "simplekml>=1.3.6",
        "boto3>=1.28.0",
        "pyyaml>=6.0.1",
        "python-dateutil>=2.8.2",
    ],
)
