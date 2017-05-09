
import sys
if sys.version_info[0] == 2:
    # unittest2 required with python2 for subTest() functionality
    import unittest2 as unittest
else:
    import unittest
import json
import os

import mat4py


test_data = json.load(open('data/test_data.json'))


class TestSequenceFunctions(unittest.TestCase):

    def test_loadmat1(self):
        """Test reading mat files"""
        for filename, result in test_data['loadmat'].items():
            with self.subTest(msg=filename):
                data = mat4py.loadmat('data/' + filename, meta=False)
                self.assertEqual(data, result)

    def test_loadmat2(self):
        """Test reading mat files using a fileobject"""
        for filename, result in test_data['loadmat'].items():
            with self.subTest(msg=filename):
                with open('data/' + filename, 'rb') as fileobj:
                    data = mat4py.loadmat(fileobj, meta=False)
                self.assertEqual(data, result)

    def test_save_load_mat1(self):
        """Test writing mat files, and reading them again"""
        for filename, result in test_data['loadmat'].items():
            with self.subTest(msg=filename):
                tempname = 'data/{}.temp'.format(filename)
                try:
                    mat4py.savemat(tempname, result)
                    data = mat4py.loadmat(tempname, meta=False)
                finally:
                    os.remove(tempname)
                self.assertEqual(data, result)

    def test_save_load_mat2(self):
        """Test writing mat files, and reading them again, using fileobjects"""
        for filename, result in test_data['loadmat'].items():
            with self.subTest(msg=filename):
                tempname = 'data/{}.temp'.format(filename)
                try:
                    with open(tempname, 'wb') as fileobj:
                        mat4py.savemat(fileobj, result)
                    with open(tempname, 'rb') as fileobj:
                        data = mat4py.loadmat(fileobj, meta=False)
                finally:
                    os.remove(tempname)
                self.assertEqual(data, result)


if __name__ == '__main__':
    unittest.main()
