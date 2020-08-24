"""Simple setup script."""

from setuptools import setup, find_packages


def readme():
    """Read the README file."""
    return open('README.md').read()


setup(name='pywolfprot',
      version='0.2',
      description='send and receive wolfvision wolfprot commands',
      long_description_content_type="text/markdown",
      long_description=readme(),
      classifiers=[
          'Development Status :: 3 - Alpha',
          'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
          'Programming Language :: Python :: 3',
          'Intended Audience :: Developers',
          'Topic :: Software Development :: Build Tools',
      ],
      keywords='Wolfvision wolfprot cynap',
      url='https://github.com/stefanu21/pywolfprot',
      author='Stefan Ursella',
      author_email='stefan.ursella@wolfvision.net',
      license='GPLv2',
      packages=['wolfprot'],
      python_requires='>=3.6',
      install_requires=[
          'websocket-client',
      ],
      project_urls={
          'Bug Reports': 'https://github.com/stefanu21/pywolfprot',
          'Source': 'https://github.com/stefanu21/pywolfprot',
      },
      zip_safe=False)
