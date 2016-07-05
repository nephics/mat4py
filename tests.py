
import sys
if sys.version_info[0] == 2:
    # unittest2 required with python2 for subTest() functionality
    import unittest2 as unittest
else:
    import unittest
import json
import os

import pdb

import mat4py


test_data = json.load(open('data/test_data.json'))


class TestSequenceFunctions(unittest.TestCase):

    def test_loadmat(self):
        """Test reading mat files"""
        for filename, result in test_data['loadmat'].items():
            with self.subTest(msg=filename):
                data = mat4py.loadmat('data/' + filename, meta=False)
                self.assertEqual(data, result)

    def test_save_load_mat(self):
        """Test writing mat files, and reading them again"""
        for filename, result in test_data['loadmat'].items():
            with self.subTest(msg=filename):
                if filename.startswith('struct_struct_string'):
                    pass #pdb.set_trace()
                tempname = 'data/{}.temp'.format(filename)
                try:
                    mat4py.savemat(tempname, result)
                    data = mat4py.loadmat(tempname, meta=False)
                finally:
                    os.remove(tempname)
                self.assertEqual(data, result)


if __name__ == '__main__':
    unittest.main()
