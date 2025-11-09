from setuptools import setup, find_packages

setup(
    name='queuectl',
    version='1.0.0',
    description='Background job queue system with worker pools, retries, and DLQ',
    author='Your Name',
    packages=find_packages(),
    install_requires=[
        'click>=8.0.0',
        'tabulate>=0.9.0'
    ],
    entry_points={
        'console_scripts': [
            'queuectl=queuectl.cli:cli',
        ],
    },
    python_requires='>=3.7',
)

