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

__version__ = '0.2.1'
__all__ = ['loadmat', 'savemat']
__license__ = """The MIT License (MIT), Copyright (c) 2011-2015 Nephics AB"""


import struct
import sys
import time
import zlib

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


def diff(iterable):
    """Diff elements of a sequence:
    s -> s0 - s1, s1 - s2, s2 - s3, ...
    """
    a, b = tee(iterable)
    next(b, None)
    return (i - j for i, j in izip(a, b))


#
# Read from MAT file
#


class ParseError(Exception):
    pass


def loadmat(filename, meta=False):
    """Load data from MAT-file:

    data = loadmat(filename, meta=False)

    The returned parameter ``data`` is a dict with the variables found
    in the MAT file.

    Call ``loadmat`` with parameter meta=True to include meta data, such
    as file header information and list of globals.

    A ``ParseError`` exception is raised if the MAT-file is corrupt or
    contains a data type that cannot be parsed.
    """

    def unpack(fmt, data):
        """Unpack a byte string to the given format. If the byte string
        contains more bytes than required for the given format, the function
        returns a tuple of values.
        """
        if fmt == 's':
            # read data as an array of chars
            val = struct.unpack(''.join([endian, str(len(data)), 's']),
                                data)[0]
        else:
            # read a number of values
            num = len(data) // struct.calcsize(fmt)
            val = struct.unpack(''.join([endian, str(num), fmt]), data)
            if len(val) == 1:
                val = val[0]
        return val

    def read_file_header(fd):
        """Read mat 5 file header of the file fd.
        Returns a dict with header values.
        """
        fields = [
            ('description', 's', 116),
            ('subsystem_offset', 's', 8),
            ('version', 'H', 2),
            ('endian_test', 's', 2)
        ]
        hdict = {}
        for name, fmt, num_bytes in fields:
            data = fd.read(num_bytes)
            hdict[name] = unpack(fmt, data)
        hdict['description'] = hdict['description'].strip()
        v_major = hdict['version'] >> 8
        v_minor = hdict['version'] & 0xFF
        hdict['__version__'] = '%d.%d' % (v_major, v_minor)
        return hdict

    def read_element_tag(fd):
        """Read data element tag: type and number of bytes.
        If tag is of the Small Data Element (SDE) type the element data
        is also returned.
        """
        data = fd.read(8)
        mtpn = unpack('I', data[:4])
        # The most significant two bytes of mtpn will always be 0,
        # if they are not, this must be SDE format
        num_bytes = mtpn >> 16
        if num_bytes > 0:
            # small data element format
            mtpn = mtpn & 0xFFFF
            if num_bytes > 4:
                raise ParseError('Error parsing Small Data Element (SDE) '
                                 'formatted data')
            data = data[4:4 + num_bytes]
        else:
            # regular element
            num_bytes = unpack('I', data[4:])
            data = None
        return (mtpn, num_bytes, data)

    def read_elements(fd, mtps, is_name=False):
        """Read elements from the file.

        If list of possible matrix data types mtps is provided, the data type
        of the elements are verified.
        """
        mtpn, num_bytes, data = read_element_tag(fd)
        if mtps and mtpn not in [etypes[mtp]['n'] for mtp in mtps]:
            raise ParseError('Expected {} type number {}, got {}'
                             .format(mtp, etypes[mtp]['n'], mtpn))
        if not data:
            # full format, read data
            data = fd.read(num_bytes)
            # Seek to next 64-bit boundary
            mod8 = num_bytes % 8
            if mod8:
                fd.seek(8 - mod8, 1)

        # parse data and return values
        if is_name:
            # names are stored as miINT8 bytes
            fmt = 's'
            val = [unpack(fmt, s)
                   for s in data.split(b'\0') if s]
            if len(val) == 0:
                val = ''
            elif len(val) == 1:
                val = asstr(val[0])
            else:
                val = [asstr(s) for s in val]
        else:
            fmt = etypes[inv_etypes[mtpn]]['fmt']
            val = unpack(fmt, data)
        return val

    def read_header(fd):
        """Read and return the matrix header."""
        flag_class, nzmax = read_elements(fd, ['miUINT32'])
        header = {
            'mclass': flag_class & 0x0FF,
            'is_logical': (flag_class >> 9 & 1) == 1,
            'is_global': (flag_class >> 10 & 1) == 1,
            'is_complex': (flag_class >> 11 & 1) == 1,
            'nzmax': nzmax
        }
        header['dims'] = read_elements(fd, ['miINT32'])
        header['n_dims'] = len(header['dims'])
        if header['n_dims'] != 2:
            raise ParseError('Only matrices with dimension 2 are supported.')
        header['name'] = read_elements(fd, ['miINT8'], is_name=True)
        return header

    def read_var_header(fd):
        """Read full header tag.

        Return a dict with the parsed header, the file position of next tag,
        a file like object for reading the uncompressed element data.
        """
        mtpn, num_bytes = unpack('II', fd.read(8))
        next_pos = fd.tell() + num_bytes

        if mtpn == etypes['miCOMPRESSED']['n']:
            # read compressed data
            data = fd.read(num_bytes)
            dcor = zlib.decompressobj()
            # from here, read of the decompressed data
            fd_var = BytesIO(dcor.decompress(data))
            del data
            fd = fd_var
            # Check the stream is not so broken as to leave cruft behind
            if dcor.flush() != b'':
                raise ParseError('Error in compressed data.')
            # read full tag from the uncompressed data
            mtpn, num_bytes = unpack('II', fd.read(8))

        if mtpn != etypes['miMATRIX']['n']:
            raise ParseError('Expecting miMATRIX type number {}, '
                             'got {}'.format(etypes['miMATRIX']['n'], mtpn))
        # read the header
        header = read_header(fd)
        return header, next_pos, fd

    def squeeze(array):
        """Return array contents if array contains only one element.
        Otherwise, return the full array.
        """
        if len(array) == 1:
            array = array[0]
        return array

    def read_numeric_array(fd, header, data_etypes):
        """Read a numeric matrix.
        Returns an array with rows of the numeric matrix.
        """
        if header['is_complex']:
            raise ParseError('Complex arrays are not supported')
        # read array data (stored as column-major)
        data = read_elements(fd, data_etypes)
        if not isinstance(data, Sequence):
            # not an array, just a value
            return data
        # transform column major data continous array to
        # a row major array of nested lists
        rowcount = header['dims'][0]
        colcount = header['dims'][1]
        array = [list(data[c * rowcount + r] for c in range(colcount))
                 for r in range(rowcount)]
        # pack and return the array
        return squeeze(array)

    def read_cell_array(fd, header):
        """Read a cell array.
        Returns an array with rows of the cell array.
        """
        array = [list() for i in range(header['dims'][0])]
        for row in range(header['dims'][0]):
            for col in range(header['dims'][1]):
                # read the matrix header and array
                vheader, next_pos, fd_var = read_var_header(fd)
                varray = read_var_array(fd_var, vheader)
                array[row].append(varray)
                # move on to next field
                fd.seek(next_pos)
        # pack and return the array
        if header['dims'][0] == 1:
            return squeeze(array[0])
        return squeeze(array)

    def read_struct_array(fd, header):
        """Read a struct array.
        Returns a dict with fields of the struct array.
        """
        # read field name length (unused, as strings are null terminated)
        field_name_length = read_elements(fd, ['miINT32'])
        if field_name_length > 32:
            raise ParseError('Unexpected field name length: {}'.format(
                             field_name_length))

        # read field names
        fields = read_elements(fd, ['miINT8'], is_name=True)
        if isinstance(fields, basestring):
            fields = [fields]

        # read rows and columns of each field
        empty = lambda: [list() for i in range(header['dims'][0])]
        array = {}
        for row in range(header['dims'][0]):
            for col in range(header['dims'][1]):
                for field in fields:
                    # read the matrix header and array
                    vheader, next_pos, fd_var = read_var_header(fd)
                    data = read_var_array(fd_var, vheader)
                    if field not in array:
                        array[field] = empty()
                    array[field][row].append(data)
                    # move on to next field
                    fd.seek(next_pos)
        # pack the nested arrays
        for field in fields:
            rows = array[field]
            for i in range(header['dims'][0]):
                rows[i] = squeeze(rows[i])
            array[field] = squeeze(array[field])
        return array

    def read_char_array(fd, header):
        array = read_numeric_array(fd, header, ['miUTF8'])
        if header['dims'][0] > 1:
            # collapse rows of chars into a list of strings
            array = [asstr(bytearray(i)) for i in array]
        else:
            # collaps row of chars into a single string
            array = asstr(bytearray(array))
        return array

    def read_var_array(fd, header):
        """Read variable array (of any supported type)."""
        mc = inv_mclasses[header['mclass']]

        if mc in numeric_class_etypes:
            return read_numeric_array(
                fd,
                header,
                set(compressed_numeric).union([numeric_class_etypes[mc]])
            )
        elif mc == 'mxSPARSE_CLASS':
            raise ParseError('Sparse matrices not supported')
        elif mc == 'mxCHAR_CLASS':
            return read_char_array(fd, header)
        elif mc == 'mxCELL_CLASS':
            return read_cell_array(fd, header)
        elif mc == 'mxSTRUCT_CLASS':
            return read_struct_array(fd, header)
        elif mc == 'mxOBJECT_CLASS':
            raise ParseError('Object classes not supported')
        elif mc == 'mxFUNCTION_CLASS':
            raise ParseError('Function classes not supported')
        elif mc == 'mxOPAQUE_CLASS':
            raise ParseError('Anonymous function classes not supported')

    def eof(fd):
        """Determine if end-of-file is reached for file fd."""
        b = fd.read(1)
        end = len(b) == 0
        if not end:
            curpos = fd.tell()
            fd.seek(curpos - 1)
        return end

    #
    # loadmat main
    #

    fd = open(filename, 'rb')

    # Check mat file format is version 5
    # For 5 format we need to read an integer in the header.
    # Bytes 124 through 128 contain a version integer and an
    # endian test string
    fd.seek(124)
    tst_str = fd.read(4)
    little_endian = (tst_str[2:4] == b'IM')
    endian = ''
    if (sys.byteorder == 'little' and little_endian) or \
       (sys.byteorder == 'big' and not little_endian):
        # no byte swapping same endian
        pass
    elif sys.byteorder == 'little':
        # byte swapping
        endian = '>'
    else:
        # byte swapping
        endian = '<'
    maj_ind = int(little_endian)
    # major version number
    maj_val = ord(tst_str[maj_ind]) if ispy2 else tst_str[maj_ind]
    if maj_val != 1:
        raise ParseError('Can only read from Matlab level 5 MAT-files')
    # the minor version number (unused value)
    # min_val = ord(tst_str[1 - maj_ind]) if ispy2 else tst_str[1 - maj_ind]

    mdict = {}
    if meta:
        # read the file header
        fd.seek(0)
        mdict['__header__'] = read_file_header(fd)
        mdict['__globals__'] = []

    # read data elements
    while not eof(fd):
        hdr, next_position, fd_var = read_var_header(fd)
        name = hdr['name']
        if name in mdict:
            raise ParseError('Duplicate variable name "{}" in mat file.'
                             .format(name))

        # read the matrix
        mdict[name] = read_var_array(fd_var, hdr)
        if meta and hdr['is_global']:
            mdict['__globals__'].append(name)

        # move on to next entry in file
        fd.seek(next_position)

    fd.close()
    return mdict


#
# Write to MAT file
#


def savemat(filename, data):
    """Save data to MAT-file:

    savemat(filename, data)

    The parameter ``data`` shall be a dict with the variables.

    A ``ValueError`` exception is raised if data has invalid format, or if the
    data structure cannot be mapped to a known MAT array type.
    """

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
            header.update({
                'mclass': 'mxINT32_CLASS', 'mtp': 'miINT32', 'dims': (1, 1)})

        elif isinstance(array, float):
            header.update({
                'mclass': 'mxDOUBLE_CLASS', 'mtp': 'miDOUBLE', 'dims': (1, 1)})

        elif isinstance(array, Sequence):

            if isarray(array, lambda i: isinstance(i, int), 1):
                # 1D int array
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
                    'dims': (1, len(next(array.values())))})

        if not header:
            raise ValueError(
                'Only dicts, two dimensional numeric, '
                'and char arrays are currently supported')
        header['name'] = name
        return header, array

    #
    #  savemat main
    #

    if not isinstance(data, Mapping):
        raise ValueError('Data should be a dict of variable arrays')
    fd = open(filename, 'wb')

    write_file_header(fd)

    # write variables
    for name, array in data.items():
        write_compressed_var_array(fd, array, name)

    fd.close()
