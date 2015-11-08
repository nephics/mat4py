"""Command line utility for mat4py.

Provides a routine for converting Matlab MAT-files to/from JSON files.

Call

    python -m mat4py.cmd -h

to get help with command line usage.
"""

import argparse
import json
import os
import sys

from mat4py import loadmat, savemat


def main():
    #
    # get arguments and invoke the conversion routines
    #

    parser = argparse.ArgumentParser(
        description='Convert Matlab '
        'MAT-files to JSON formated text files, and the other way around.')

    parser.add_argument(
        'file', nargs='+',
        help='path to a Matlab MAT-file or a JSON file')
    parser.add_argument(
        '--remove-input', action='store_const', const=True,
        default=False, help='remove input file after conversion')
    parser.add_argument(
        '-f', '--force', action='store_const', const=True,
        default=False, help='overwrite existing files when converting')
    args = parser.parse_args()

    for path in args.file:
        spl = os.path.splitext(path)
        ext = spl[1].lower()

        if ext == '.mat':
            dest = spl[0] + '.json'
            try:
                if os.path.exists(dest) and not args.force:
                    raise Exception('File {} already exists.'.format(dest))
                data = loadmat(path)
                with open(dest, 'w') as fp:
                    json.dump(data, fp)
                if args.remove_input:
                    os.remove(path)
            except Exception as e:
                print('Error: {}'.format(e))
                sys.exit(1)

        elif ext == '.json':
            dest = spl[0] + '.mat'
            try:
                if os.path.exists(dest) and not args.force:
                    raise Exception('File {} already exists.'.format(dest))
                with open(path) as fp:
                    data = json.load(fp)
                savemat(dest, data)
                if args.remove_input:
                    os.remove(path)
            except RuntimeError as e:
                print('Error: {}'.format(e))
                sys.exit(1)
        else:
            print('Unsupported file extension on file: {}'.format(path))
            sys.exit(1)


if __name__ == '__main__':
    main()
