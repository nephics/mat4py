from distutils.core import setup

def readme():
    with open('README.rst') as f:
        return f.read()

setup(
    name='mat4py',
    version='0.1.2',
    author='Jacob Sondergaard',
    author_email='jacob@nephics.com',
    packages=['mat4py'],
    url='https://bitbucket.org/nephics/mat4py/',
    license='MIT License',
    description='Load and save data in the Matlab (TM) MAT-file format.',
    long_description=readme(),
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.7',
        'Topic :: Scientific/Engineering'
    ]
)