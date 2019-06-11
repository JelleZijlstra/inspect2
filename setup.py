VERSION = '0.1.1'
DESCRIPTION = 'Backport of the Python 3.6 inspect module to Python 2.7-3.5'

classifiers = [
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: Python Software Foundation License',
    'Operating System :: OS Independent',
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3.2',
    'Programming Language :: Python :: 3.3',
    'Programming Language :: Python :: 3.4',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
    'Topic :: Software Development',
]

if __name__ == '__main__':
    try:
        from setuptools import setup
    except ImportError:
        from distutils.core import setup

    with open('README.md', 'r') as f:
        readme = f.read()

    setup(
        name='inspect2',
        version=VERSION,
        description=DESCRIPTION,
        long_description=readme,
        long_description_content_type='text/markdown',
        url='https://github.com/JelleZijlstra/inspect2',
        author='Jelle Zijlstra',
        author_email='jelle.zijlstra@gmail.com',
        license='PSF',
        py_modules=['inspect2'],
        keywords='inspect inspection backport',
        classifiers=classifiers,
    )
