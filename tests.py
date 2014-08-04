import unittest
import json
import os

import mat4py


test_data = json.load(open('data/test_data.json'))


class TestSequenceFunctions(unittest.TestCase):

    def test_loadmat(self):
        """Test reading mat files"""
        for filename, result in test_data['loadmat'].iteritems():
            data = mat4py.loadmat('data/' + filename, meta=False)
            self.assertEqual(data, result)

    def test_save_load_mat(self):
        """Test writing mat files, and reading them again"""
        for filename, result in test_data['loadmat'].iteritems():
            tempname = 'data/{}.temp'.format(filename)
            try:
                mat4py.savemat(tempname, result)
                data = mat4py.loadmat(tempname, meta=False)
            finally:
                os.remove(tempname)
            self.assertEqual(data, result)


if __name__ == '__main__':
    unittest.main()
