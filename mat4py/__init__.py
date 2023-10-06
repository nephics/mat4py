"""mat4py - load and save data in the Matlab (TM) MAT-file format

This module provides the following two functions for loading and saving
data in Matlab (TM) MAT-file format:

    data = loadmat(filename, meta=False)

    savemat(filename, data)

The function ``loadmat`` loads all variables stored in the MAT-file into
a simple Python data structure, using only Python's dict and list
objects. Numeric and cell arrays are converted to row-ordered nested lists.
Arrays are squeezed to eliminate arrays with only one element.
The resulting data structure is composed of simple types that are compatible
with the JSON format.

Python data can be saved to a MAT-file, with the function ``savemat``. Data has
to be structured in the same way as for ``loadmat``, i.e. it should be composed
of simple data types, like dict, list, str, int and float.

The following Matlab data structures/types are not supported:

* Arrays with more than 2 dimensions
* Arrays with complex numbers
* Sparse arrays
* Function arrays
* Object classes
* Anonymous function classes

"""
from .loadmat import loadmat
from .savemat import savemat

__version__ = '0.6.0'
__all__ = ['loadmat', 'savemat']
__license__ = """The MIT License (MIT), Copyright (c) 2011-2023 Nephics AB"""


if __name__ == '__main__':
    import cmd
    cmd.main()
