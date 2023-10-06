"""load data in the Matlab (TM) MAT-file format

Copyright (c) 2011-2023 Nephics AB
The MIT License (MIT)
"""

__all__ = ['loadmat']


import struct
import sys
import zlib

try:
    from collections.abc import Sequence
except ImportError:
    from collections import Sequence

from itertools import tee
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
# Uitlity functions
#

def unpack(endian, fmt, data):
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


def read_file_header(fd, endian):
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
        hdict[name] = unpack(endian, fmt, data)
    hdict['description'] = hdict['description'].strip()
    v_major = hdict['version'] >> 8
    v_minor = hdict['version'] & 0xFF
    hdict['__version__'] = '%d.%d' % (v_major, v_minor)
    return hdict


def read_element_tag(fd, endian):
    """Read data element tag: type and number of bytes.
    If tag is of the Small Data Element (SDE) type the element data
    is also returned.
    """
    data = fd.read(8)
    mtpn = unpack(endian, 'I', data[:4])
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
        num_bytes = unpack(endian, 'I', data[4:])
        data = None
    return (mtpn, num_bytes, data)


def read_elements(fd, endian, mtps, is_name=False):
    """Read elements from the file.

    If list of possible matrix data types mtps is provided, the data type
    of the elements are verified.
    """
    mtpn, num_bytes, data = read_element_tag(fd, endian)
    if mtps and mtpn not in [etypes[mtp]['n'] for mtp in mtps]:
        raise ParseError('Got type {}, expected {}'.format(
            mtpn, ' / '.join('{} ({})'.format(
                etypes[mtp]['n'], mtp) for mtp in mtps)))
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
        val = [unpack(endian, fmt, s)
               for s in data.split(b'\0') if s]
        if len(val) == 0:
            val = ''
        elif len(val) == 1:
            val = asstr(val[0])
        else:
            val = [asstr(s) for s in val]
    else:
        fmt = etypes[inv_etypes[mtpn]]['fmt']
        val = unpack(endian, fmt, data)
    return val


def read_header(fd, endian):
    """Read and return the matrix header."""
    flag_class, nzmax = read_elements(fd, endian, ['miUINT32'])
    header = {
        'mclass': flag_class & 0x0FF,
        'is_logical': (flag_class >> 9 & 1) == 1,
        'is_global': (flag_class >> 10 & 1) == 1,
        'is_complex': (flag_class >> 11 & 1) == 1,
        'nzmax': nzmax
    }
    header['dims'] = read_elements(fd, endian, ['miINT32'])
    header['n_dims'] = len(header['dims'])
    if header['n_dims'] != 2:
        raise ParseError('Only matrices with dimension 2 are supported.')
    header['name'] = read_elements(fd, endian, ['miINT8'], is_name=True)
    return header


def read_var_header(fd, endian):
    """Read full header tag.

    Return a dict with the parsed header, the file position of next tag,
    a file like object for reading the uncompressed element data.
    """
    mtpn, num_bytes = unpack(endian, 'II', fd.read(8))
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
        mtpn, num_bytes = unpack(endian, 'II', fd.read(8))

    if mtpn != etypes['miMATRIX']['n']:
        raise ParseError('Expecting miMATRIX type number {}, '
                         'got {}'.format(etypes['miMATRIX']['n'], mtpn))
    # read the header
    header = read_header(fd, endian)
    return header, next_pos, fd


def squeeze(array):
    """Return array contents if array contains only one element.
    Otherwise, return the full array.
    """
    if len(array) == 1:
        array = array[0]
    return array


def read_numeric_array(fd, endian, header, data_etypes):
    """Read a numeric matrix.
    Returns an array with rows of the numeric matrix.
    """
    if header['is_complex']:
        raise ParseError('Complex arrays are not supported')
    # read array data (stored as column-major)
    data = read_elements(fd, endian, data_etypes)
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


def read_cell_array(fd, endian, header):
    """Read a cell array.
    Returns an array with rows of the cell array.
    """
    array = [list() for i in range(header['dims'][0])]
    for row in range(header['dims'][0]):
        for col in range(header['dims'][1]):
            # read the matrix header and array
            vheader, next_pos, fd_var = read_var_header(fd, endian)
            varray = read_var_array(fd_var, endian, vheader)
            array[row].append(varray)
            # move on to next field
            fd.seek(next_pos)
    # pack and return the array
    if header['dims'][0] == 1:
        return squeeze(array[0])
    return squeeze(array)


def read_struct_array(fd, endian, header):
    """Read a struct array.
    Returns a dict with fields of the struct array.
    """
    # read field name length (unused, as strings are null terminated)
    field_name_length = read_elements(fd, endian, ['miINT32'])
    if field_name_length > 32:
        raise ParseError('Unexpected field name length: {}'.format(
                         field_name_length))

    # read field names
    fields = read_elements(fd, endian, ['miINT8'], is_name=True)
    if isinstance(fields, basestring):
        fields = [fields]

    # read rows and columns of each field
    empty = lambda: [list() for i in range(header['dims'][0])]
    array = {}
    for row in range(header['dims'][0]):
        for col in range(header['dims'][1]):
            for field in fields:
                # read the matrix header and array
                vheader, next_pos, fd_var = read_var_header(fd, endian)
                data = read_var_array(fd_var, endian, vheader)
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


def read_char_array(fd, endian, header):
    array = read_numeric_array(fd, endian, header, ['miUTF8'])
    if header['dims'][0] > 1:
        # collapse rows of chars into a list of strings
        array = [asstr(bytearray(i)) for i in array]
    else:
        # collaps row of chars into a single string
        array = asstr(bytearray(array))
    return array


def read_var_array(fd, endian, header):
    """Read variable array (of any supported type)."""
    mc = inv_mclasses[header['mclass']]

    if mc in numeric_class_etypes:
        return read_numeric_array(
            fd, endian, header,
            set(compressed_numeric).union([numeric_class_etypes[mc]])
        )
    elif mc == 'mxSPARSE_CLASS':
        raise ParseError('Sparse matrices not supported')
    elif mc == 'mxCHAR_CLASS':
        return read_char_array(fd, endian, header)
    elif mc == 'mxCELL_CLASS':
        return read_cell_array(fd, endian, header)
    elif mc == 'mxSTRUCT_CLASS':
        return read_struct_array(fd, endian, header)
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


class ParseError(Exception):
    pass


#
# Read from MAT file
#


def loadmat(filename, meta=False):
    """Load data from MAT-file:

    data = loadmat(filename, meta=False)

    The filename argument is either a string with the filename, or
    a file like object.

    The returned parameter ``data`` is a dict with the variables found
    in the MAT file.

    Call ``loadmat`` with parameter meta=True to include meta data, such
    as file header information and list of globals.

    A ``ParseError`` exception is raised if the MAT-file is corrupt or
    contains a data type that cannot be parsed.
    """

    if isinstance(filename, basestring):
        fd = open(filename, 'rb')
    else:
        fd = filename

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
        mdict['__header__'] = read_file_header(fd, endian)
        mdict['__globals__'] = []

    # read data elements
    while not eof(fd):
        hdr, next_position, fd_var = read_var_header(fd, endian)
        name = hdr['name']
        if name in mdict:
            raise ParseError('Duplicate variable name "{}" in mat file.'
                             .format(name))

        # read the matrix
        mdict[name] = read_var_array(fd_var, endian, hdr)
        if meta and hdr['is_global']:
            mdict['__globals__'].append(name)

        # move on to next entry in file
        fd.seek(next_position)

    fd.close()
    return mdict
