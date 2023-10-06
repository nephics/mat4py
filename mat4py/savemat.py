"""savemat - save data in the Matlab (TM) MAT-file format

Copyright (c) 2011-2023 Nephics AB
The MIT License (MIT)
"""

__all__ = ['savemat']


import struct
import sys
import time
import zlib

try:
    from collections.abc import Sequence, Mapping
except ImportError:
    from collections import Sequence, Mapping

from itertools import chain, tee
try:
    from itertools import izip
    ispy2 = True
except ImportError:
    izip = zip
    basestring = str
    ispy2 = False
from io import BytesIO


# encode a string to bytes and vice versa
asbytes = lambda s: s.encode('latin1')
asstr = lambda b: b.decode('latin1')

# array element data types
etypes = {
    'miINT8': {'n': 1, 'fmt': 'b'},
    'miUINT8': {'n': 2, 'fmt': 'B'},
    'miINT16': {'n': 3, 'fmt': 'h'},
    'miUINT16': {'n': 4, 'fmt': 'H'},
    'miINT32': {'n': 5, 'fmt': 'i'},
    'miUINT32': {'n': 6, 'fmt': 'I'},
    'miSINGLE': {'n': 7, 'fmt': 'f'},
    'miDOUBLE': {'n': 9, 'fmt': 'd'},
    'miINT64': {'n': 12, 'fmt': 'q'},
    'miUINT64': {'n': 13, 'fmt': 'Q'},
    'miMATRIX': {'n': 14},
    'miCOMPRESSED': {'n': 15},
    'miUTF8': {'n': 16, 'fmt': 's'},
    'miUTF16': {'n': 17, 'fmt': 's'},
    'miUTF32': {'n': 18, 'fmt': 's'}
}

# inverse mapping of etypes
inv_etypes = dict((v['n'], k) for k, v in etypes.items())

# matrix array classes
mclasses = {
    'mxCELL_CLASS': 1,
    'mxSTRUCT_CLASS': 2,
    'mxOBJECT_CLASS': 3,
    'mxCHAR_CLASS': 4,
    'mxSPARSE_CLASS': 5,
    'mxDOUBLE_CLASS': 6,
    'mxSINGLE_CLASS': 7,
    'mxINT8_CLASS': 8,
    'mxUINT8_CLASS': 9,
    'mxINT16_CLASS': 10,
    'mxUINT16_CLASS': 11,
    'mxINT32_CLASS': 12,
    'mxUINT32_CLASS': 13,
    'mxINT64_CLASS': 14,
    'mxUINT64_CLASS': 15,
    'mxFUNCTION_CLASS': 16,
    'mxOPAQUE_CLASS': 17,
    'mxOBJECT_CLASS_FROM_MATRIX_H': 18
}

# map of numeric array classes to data types
numeric_class_etypes = {
    'mxDOUBLE_CLASS': 'miDOUBLE',
    'mxSINGLE_CLASS': 'miSINGLE',
    'mxINT8_CLASS': 'miINT8',
    'mxUINT8_CLASS': 'miUINT8',
    'mxINT16_CLASS': 'miINT16',
    'mxUINT16_CLASS': 'miUINT16',
    'mxINT32_CLASS': 'miINT32',
    'mxUINT32_CLASS': 'miUINT32',
    'mxINT64_CLASS': 'miINT64',
    'mxUINT64_CLASS': 'miUINT64'
}

inv_mclasses = dict((v, k) for k, v in mclasses.items())

# data types that may be used when writing numeric data
compressed_numeric = ['miINT32', 'miUINT16', 'miINT16', 'miUINT8']


INT32_MAX = 2 ** 31 - 1


def diff(iterable):
    """Diff elements of a sequence:
    s -> s0 - s1, s1 - s2, s2 - s3, ...
    """
    a, b = tee(iterable)
    next(b, None)
    return (i - j for i, j in izip(a, b))


#
# Utility functions
#


def write_file_header(fd):
    # write file header
    desc = 'MATLAB 5.0 MAT-file, created with mat4py on: ' + \
           time.strftime("%a, %b %d %Y %H:%M:%S", time.localtime())
    fd.write(struct.pack('116s', desc.encode('latin1')))
    fd.write(struct.pack('8s', b' ' * 8))
    fd.write(struct.pack('H', 0x100))
    if sys.byteorder == 'big':
        fd.write(struct.pack('2s', b'MI'))
    else:
        fd.write(struct.pack('2s', b'IM'))

def write_elements(fd, mtp, data, is_name=False):
    """Write data element tag and data.

    The tag contains the array type and the number of
    bytes the array data will occupy when written to file.

    If data occupies 4 bytes or less, it is written immediately
    as a Small Data Element (SDE).
    """
    fmt = etypes[mtp]['fmt']
    if isinstance(data, Sequence):
        if fmt == 's' or is_name:
            if isinstance(data, bytes):
                if is_name and len(data) > 31:
                    raise ValueError(
                        'Name "{}" is too long (max. 31 '
                        'characters allowed)'.format(data))
                fmt = '{}s'.format(len(data))
                data = (data,)
            else:
                fmt = ''.join('{}s'.format(len(s)) for s in data)
        else:
            l = len(data)
            if l == 0:
                # empty array
                fmt = ''
            if l > 1:
                # more than one element to be written
                fmt = '{}{}'.format(l, fmt)
    else:
        data = (data,)
    num_bytes = struct.calcsize(fmt)
    if num_bytes <= 4:
        # write SDE
        if num_bytes < 4:
            # add pad bytes
            fmt += '{}x'.format(4 - num_bytes)
        fd.write(struct.pack('hh' + fmt, etypes[mtp]['n'],
                 *chain([num_bytes], data)))
        return
    # write tag: element type and number of bytes
    fd.write(struct.pack('b3xI', etypes[mtp]['n'], num_bytes))
    # add pad bytes to fmt, if needed
    mod8 = num_bytes % 8
    if mod8:
        fmt += '{}x'.format(8 - mod8)
    # write data
    fd.write(struct.pack(fmt, *data))

def write_var_header(fd, header):
    """Write variable header"""

    # write tag bytes,
    # and array flags + class and nzmax (null bytes)
    fd.write(struct.pack('b3xI', etypes['miUINT32']['n'], 8))
    fd.write(struct.pack('b3x4x', mclasses[header['mclass']]))

    # write dimensions array
    write_elements(fd, 'miINT32', header['dims'])

    # write var name
    write_elements(fd, 'miINT8', asbytes(header['name']), is_name=True)

def write_var_data(fd, data):
    """Write variable data to file"""
    # write array data elements (size info)
    fd.write(struct.pack('b3xI', etypes['miMATRIX']['n'], len(data)))

    # write the data
    fd.write(data)

def write_compressed_var_array(fd, array, name):
    """Write compressed variable data to file"""
    bd = BytesIO()

    write_var_array(bd, array, name)

    data = zlib.compress(bd.getvalue())
    bd.close()

    # write array data elements (size info)
    fd.write(struct.pack('b3xI', etypes['miCOMPRESSED']['n'], len(data)))

    # write the compressed data
    fd.write(data)

def write_numeric_array(fd, header, array):
    """Write the numeric array"""
    # make a memory file for writing array data
    bd = BytesIO()

    # write matrix header to memory file
    write_var_header(bd, header)

    if not isinstance(array, basestring) and header['dims'][0] > 1:
        # list array data in column major order
        array = list(chain.from_iterable(izip(*array)))

    # write matrix data to memory file
    write_elements(bd, header['mtp'], array)

    # write the variable to disk file
    data = bd.getvalue()
    bd.close()
    write_var_data(fd, data)

def write_cell_array(fd, header, array):
    # make a memory file for writing array data
    bd = BytesIO()

    # write matrix header to memory file
    write_var_header(bd, header)

    for row in range(header['dims'][0]):
        for col in range(header['dims'][1]):
            if header['dims'][0] > 1:
                vdata = array[row][col]
            else:
                # array is squeezed on the row dimension
                vdata = array[col]
            write_var_array(bd, vdata)

    # write the variable to disk file
    data = bd.getvalue()
    bd.close()
    write_var_data(fd, data)

def write_struct_array(fd, header, array):
    # make a memory file for writing array data
    bd = BytesIO()

    # write matrix header to memory file
    write_var_header(bd, header)

    fieldnames = list(array.keys())

    field_names_sizes = [(f, len(f)) for f in (asbytes(s)
                         for s in fieldnames)]

    # write field name length (the str length + a null byte)
    field_length = max(i[1] for i in field_names_sizes) + 1
    if field_length > 32:
        raise ValueError('Struct field names are too long')
    write_elements(bd, 'miINT32', field_length)

    # write fieldnames
    write_elements(
        bd, 'miINT8',
        [f + (field_length - l % field_length) * b'\0'
         for f, l in field_names_sizes],
        is_name=True)

    # wrap each field in a cell
    for row in range(header['dims'][0]):
        for col in range(header['dims'][1]):
            for field in fieldnames:
                if header['dims'][0] > 1:
                    vdata = array[field][col][row]
                elif header['dims'][1] > 1:
                    vdata = array[field][col]
                else:
                    vdata = array[field]
                write_var_array(bd, vdata)

    # write the variable to disk file
    data = bd.getvalue()
    bd.close()
    write_var_data(fd, data)

def write_char_array(fd, header, array):
    if isinstance(array, basestring):
        # split string into chars
        array = [asbytes(c) for c in array]
    else:
        # split each string in list into chars
        array = [[asbytes(c) for c in s] for s in array]
    return write_numeric_array(fd, header, array)

def write_var_array(fd, array, name=''):
    """Write variable array (of any supported type)"""
    header, array = guess_header(array, name)
    mc = header['mclass']
    if mc in numeric_class_etypes:
        return write_numeric_array(fd, header, array)
    elif mc == 'mxCHAR_CLASS':
        return write_char_array(fd, header, array)
    elif mc == 'mxCELL_CLASS':
        return write_cell_array(fd, header, array)
    elif mc == 'mxSTRUCT_CLASS':
        return write_struct_array(fd, header, array)
    else:
        raise ValueError('Unknown mclass {}'.format(mc))

def isarray(array, test, dim=2):
    """Returns True if test is True for all array elements.
    Otherwise, returns False.
    """
    if dim > 1:
        return all(isarray(array[i], test, dim - 1)
                   for i in range(len(array)))
    return all(test(i) for i in array)

def guess_header(array, name=''):
    """Guess the array header information.
    Returns a header dict, with class, data type, and size information.
    """
    header = {}

    if isinstance(array, Sequence) and len(array) == 1:
        # sequence with only one element, squeeze the array
        array = array[0]

    if isinstance(array, basestring):
        header.update({
            'mclass': 'mxCHAR_CLASS', 'mtp': 'miUTF8',
            'dims': (1 if len(array) > 0 else 0, len(array))})

    elif isinstance(array, Sequence) and len(array) == 0:
        # empty (int) array
        header.update({
            'mclass': 'mxINT32_CLASS', 'mtp': 'miINT32', 'dims': (0, 0)})

    elif isinstance(array, Mapping):
        # test if cells (values) of all fields are of equal type and
        # have equal length
        field_types = [type(j) for j in array.values()]
        field_lengths = [1 if isinstance(j, (basestring, int, float))
                         else len(j) for j in array.values()]
        if len(field_lengths) == 1:
            equal_lengths = True
            equal_types = True
        else:
            equal_lengths = not any(diff(field_lengths))
            equal_types = all([field_types[0] == f for f in field_types])

        # if of unqeual lengths or unequal types, then treat each value
        # as a cell in a 1x1 struct
        header.update({
            'mclass': 'mxSTRUCT_CLASS',
            'dims': (
                1,
                field_lengths[0] if equal_lengths and equal_types else 1)}
            )

    elif isinstance(array, int):
        if array > INT32_MAX:
            header.update({
                'mclass': 'mxINT64_CLASS', 'mtp': 'miINT64', 'dims': (1, 1)})
        else:
            header.update({
                'mclass': 'mxINT32_CLASS', 'mtp': 'miINT32', 'dims': (1, 1)})

    elif isinstance(array, float):
        header.update({
            'mclass': 'mxDOUBLE_CLASS', 'mtp': 'miDOUBLE', 'dims': (1, 1)})

    elif isinstance(array, Sequence):

        if isarray(array, lambda i: isinstance(i, int), 1):
            # 1D int array
            if max(array) > INT32_MAX:
                header.update({
                    'mclass': 'mxINT64_CLASS', 'mtp': 'miINT64',
                    'dims': (1, len(array))})
            else:
                header.update({
                    'mclass': 'mxINT32_CLASS', 'mtp': 'miINT32',
                    'dims': (1, len(array))})

        elif isarray(array, lambda i: isinstance(i, (int, float)), 1):
            # 1D double array
            header.update({
                'mclass': 'mxDOUBLE_CLASS', 'mtp': 'miDOUBLE',
                'dims': (1, len(array))})

        elif (isarray(array, lambda i: isinstance(i, Sequence), 1) and
                any(diff(len(s) for s in array))):
            # sequence of unequal length, assume cell array
            header.update({
                'mclass': 'mxCELL_CLASS',
                'dims': (1, len(array))
            })

        elif isarray(array, lambda i: isinstance(i, basestring), 1):
            # char array
            header.update({
                'mclass': 'mxCHAR_CLASS', 'mtp': 'miUTF8',
                'dims': (len(array), len(array[0]))})

        elif isarray(array, lambda i: isinstance(i, Sequence), 1):
            # 2D array

            if any(diff(len(j) for j in array)):
                # rows are of unequal length, make it a cell array
                header.update({
                    'mclass': 'mxCELL_CLASS',
                    'dims': (len(array), len(array[0]))})

            elif isarray(array, lambda i: isinstance(i, int)):
                # 2D int array
                if max([max(inner_array) for inner_array in array]) > INT32_MAX:
                    header.update({
                        'mclass': 'mxINT64_CLASS', 'mtp': 'miINT64',
                        'dims': (len(array), len(array[0]))})
                else:
                    header.update({
                        'mclass': 'mxINT32_CLASS', 'mtp': 'miINT32',
                        'dims': (len(array), len(array[0]))})

            elif isarray(array, lambda i: isinstance(i, (int, float))):
                # 2D double array
                header.update({
                    'mclass': 'mxDOUBLE_CLASS',
                    'mtp': 'miDOUBLE',
                    'dims': (len(array), len(array[0]))})

        elif isarray(array, lambda i: isinstance(
                i, (int, float, basestring, Sequence, Mapping))):
            # mixed contents, make it a cell array
            header.update({
                'mclass': 'mxCELL_CLASS',
                'dims': (1, len(array))})

    if not header:
        raise ValueError(
            'Only dicts, two dimensional numeric, '
            'and char arrays are currently supported')
    header['name'] = name
    return header, array


#
# Write to MAT file
#


def savemat(filename, data):
    """Save data to MAT-file:

    savemat(filename, data)

    The filename argument is either a string with the filename, or
    a file like object.

    The parameter ``data`` shall be a dict with the variables.

    A ``ValueError`` exception is raised if data has invalid format, or if the
    data structure cannot be mapped to a known MAT array type.
    """

    if not isinstance(data, Mapping):
        raise ValueError('Data should be a dict of variable arrays')

    if isinstance(filename, basestring):
        fd = open(filename, 'wb')
    else:
        fd = filename

    write_file_header(fd)

    # write variables
    for name, array in data.items():
        write_compressed_var_array(fd, array, name)

    fd.close()
