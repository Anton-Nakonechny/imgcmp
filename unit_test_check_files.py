#!/usr/bin/env python

import sys, unittest
from check_files import AFSImageComparator, FAIL_COLOR, WARNING_COLOR, OK_COLOR, END_COLOR

class UnitTest_check_files(unittest.TestCase):

    def test_compare_shared_object(self):
        tester = AFSImageComparator("","","")

        res = tester.compare_shared_object('unit_test_files/so_.text_same/local_camera.omap4.so', 'unit_test_files/so_.text_same/remote_camera.omap4.so')
        self.assertTrue(res)

        res = tester.compare_shared_object('unit_test_files/so_.text_differ/local_libbcc.so', 'unit_test_files/so_.text_differ/remote_libbcc.so')
        self.assertFalse(res)

if __name__ == '__main__':
    unittest.main()
