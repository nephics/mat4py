mat4py - load and save data in the Matlab (TM) MAT-file format.
===============================================================

The package provides the mat4py module with the functions ``loadmat`` and
``savemat`` that allows for reading resp. writing data in the Matlab (TM)
MAT-file format.

Matlab data is loaded into basic Python data types. Matrices are stored row-major using lists of lists. Matlab structs and cells are represented using Python dicts.

The package can be run from the command line, in which case, it provides a routine for converting Matlab MAT-files to/from JSON files.


Load data from MAT-file
-----------------------

The function ``loadmat`` loads all variables stored in the MAT-file into
a simple Python data structure, using only Python's dict and list
objects. Numeric and cell arrays are converted to row-ordered nested lists. Arrays are squeezed to eliminate arrays with only one element.
The resulting data structure is composed of simple types that are compatible
with the JSON format.

Example: Load a MAT-file into a Python data structure::

   data = loadmat('datafile.mat')

The variable ``data`` is a dict with the variables and values contained in the MAT-file.


Save Python data structure to a MAT-file
----------------------------------------

Python data can be saved to a MAT-file, with the function ``savemat``. Data has
to be structured in the same way as for ``loadmat``, i.e. it should be composed
of simple data types, like dict, list, str, int and float.


Example: Save a Python data structure to a MAT-file::

   savemat('datafile.mat', data)

The parameter ``data`` shall be a dict with the variables.


Command line usage
------------------

The package can be run from the command line, in which case, it provides
a routine for converting Matlab MAT-files to/from JSON files.

Call::

    python -m mat4py.cmd -h

to get help with command line usage.


Known limitations
-----------------

The following Matlab data structures/types are not supported:

- Arrays with more than 2 dimensions
- Arrays with complex numbers
- Sparse arrays
- Function arrays
- Object classes
- Anonymous function classes


License
-------

The MIT License (MIT)
Copyright (c) 2011-2023 Nephics AB

See the ``LICENSE.txt`` file.
