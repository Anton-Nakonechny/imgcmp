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

    def test_cmp_and_process_java(self):
        tester = AFSImageComparator("","","")

        res = tester.cmp_and_process_java('unit_test_files/jar_.mf_differ_no_classes/qewl_ext.jar', 'unit_test_files/jar_.mf_differ_no_classes/qewl_loc.jar')
        self.assertFalse(res)

        res = tester.cmp_and_process_java('unit_test_files/jar_.mf_same_no_classes/qewl_ext_same.jar', 'unit_test_files/jar_.mf_same_no_classes/qewl_loc_same.jar')
        self.assertTrue(res)

        res = tester.cmp_and_process_java('unit_test_files/jar_.classes_differ_no_mf/apache-xml_ext.jar', 'unit_test_files/jar_.classes_differ_no_mf/apache-xml_loc.jar')
        self.assertFalse(res)

        res = tester.cmp_and_process_java('unit_test_files/jar_.classes_same_no_mf/apache-xml_ext_same.jar', 'unit_test_files/jar_.classes_same_no_mf/apache-xml_loc_same.jar')
        self.assertTrue(res)

        res = tester.cmp_and_process_java('unit_test_files/apk_.mf_differ_classes_differ/Browser_ext.apk', 'unit_test_files/apk_.mf_differ_classes_differ/Browser_loc.apk')
        self.assertFalse(res)

        res = tester.cmp_and_process_java('unit_test_files/apk_.mf_same_classes_same/Browser_ext_same.apk', 'unit_test_files/apk_.mf_same_classes_same/Browser_loc_same.apk')
        self.assertTrue(res)

        res = tester.cmp_and_process_java('unit_test_files/apk_.mf_length_differ/DemoMode_ext.apk', 'unit_test_files/apk_.mf_length_differ/DemoMode_loc.apk')
        self.assertFalse(res)

        res = tester.cmp_and_process_java('unit_test_files/apk_.mf_length_same/DemoMode_ext_same.apk', 'unit_test_files/apk_.mf_length_same/DemoMode_loc_same.apk')
        self.assertTrue(res)

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(UnitTest_check_files)
    unittest.TextTestRunner(verbosity=2).run(suite)
