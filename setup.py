from distutils.core import setup

setup(
    name='mat4py',
    version='0.1.0',
    author='Jacob Sondergaard',
    author_email='jacob@nephics.com',
    packages=['mat4py'],
    url='http://pypi.python.org/pypi/mat4py/',
    license='MIT License',
    description='Load and save data in the Matlab (TM) MAT-file format.',
    long_description=open('README.rst').read(),
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.7',
        'Topic :: Scientific/Engineering'
    ]
)