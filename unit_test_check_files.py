#!/usr/bin/env python

"""
Test cases can be run hierarchically:
all_suites_we_have -> certain_suite -> certain_test_in_suite

In the case of python unittest module suite is a separate class, inherited
from unittest.TestCase. Test case is a method of suite class.

Tests may be run as follows:

1. Run all test suites:
    $ python -m unittest unit_test_check_files
    or
    $ ./unit_test_check_files.py

2. Run all tests of a separate suite
    $ python -m unittest unit_test_check_files.CompareJava

3. Run a certain test
    $ python -m unittest unit_test_check_files.CompareJava.CompareJar
"""

import sys
import unittest

from check_files import AFSImageComparator, FAIL_COLOR, WARNING_COLOR, OK_COLOR, END_COLOR

class GeneralScriptBehaviourTestSuite(unittest.TestCase):
    """
    This suite is intended to check:
        - workdir mounting
        - creating necessary dirs
        - cleaning workdir and tmp dirs after script run
    """

    def test_posix_signals_handling(self):
        """
        Runs image checking, kills the script with SIGTERM and SIGINT and checks,
        if images are unmounted and workdir is removed.
        """
        # not implemented yet
        pass

    def test_preparation_and_cleaning_workdir(self):
        # not implemented yet
        pass

    def test_lots_of_dummy_AFSImageComparator_instances(self):
        tester = AFSImageComparator("","","")
        tester2 = AFSImageComparator("","","")
        tester3 = AFSImageComparator("","","")
        tester4 = AFSImageComparator("","","")
        tester5 = AFSImageComparator("","","")
        tester6 = AFSImageComparator("","","")
        tester7 = AFSImageComparator("","","")
        tester8 = AFSImageComparator("","","")
        tester9 = AFSImageComparator("","","")
        tester10 = AFSImageComparator("","","")
        tester11 = AFSImageComparator("","","")

class CompareImagesTestSuite(unittest.TestCase):
    """ This suite is intended to check test images """

    def test_file_miss(self):
        """
        compares two images, in one of which some files
        are missing and they are not in allowed list
        """
        tester = AFSImageComparator("unit_test_files/img_.missed_not_allowed/missed_not_in_allowed_loc.img",
                                    "unit_test_files/img_.missed_not_allowed/missed_not_in_allowed_ext.img","")
        res = tester.run()
        self.assertFalse(res)

        tester = AFSImageComparator("unit_test_files/img_.same_not_allowed/same_not_in_allowed_loc.img",
                                    "unit_test_files/img_.same_not_allowed/same_not_in_allowed_ext.img","")
        res = tester.run()
        self.assertTrue(res)

    def test_file_miss_allowed(self):
        """
        compares two images, in one of which some files
        are missing and they are in allowed list
        """
        tester = AFSImageComparator("unit_test_files/img_.missed_allowed/missed_in_allowed_loc.img",
                                    "unit_test_files/img_.missed_allowed/missed_in_allowed_ext.img","")
        res = tester.run()
        self.assertTrue(res)

        tester = AFSImageComparator("unit_test_files/img_.same_allowed/same_in_allowed_loc.img",
                                    "unit_test_files/img_.same_allowed/same_in_allowed_ext.img","")
        res = tester.run()
        self.assertTrue(res)

    def test_equal_images(self):
        """ compares two equal images """
        # not implemented yet
        pass


class CompareJavaTestSuite(unittest.TestCase):
    """ This suite is intended to check Java (.apk and .jar) comparison """

    def test_jar_comparison(self):
        tester = AFSImageComparator("","","")

        res = tester.cmp_and_process_java('unit_test_files/jar_.mf_differ_no_classes/qewl_ext.jar',
                                          'unit_test_files/jar_.mf_differ_no_classes/qewl_loc.jar')
        self.assertFalse(res)

        res = tester.cmp_and_process_java('unit_test_files/jar_.mf_same_no_classes/qewl_ext_same.jar',
                                          'unit_test_files/jar_.mf_same_no_classes/qewl_loc_same.jar')
        self.assertTrue(res)

        res = tester.cmp_and_process_java('unit_test_files/jar_.classes_differ_no_mf/apache-xml_ext.jar',
                                          'unit_test_files/jar_.classes_differ_no_mf/apache-xml_loc.jar')
        self.assertFalse(res)

        res = tester.cmp_and_process_java('unit_test_files/jar_.classes_same_no_mf/apache-xml_ext_same.jar',
                                          'unit_test_files/jar_.classes_same_no_mf/apache-xml_loc_same.jar')
        self.assertTrue(res)

    def test_apk_comparison(self):
        tester = AFSImageComparator("","","")

        res = tester.cmp_and_process_java('unit_test_files/apk_.mf_differ_classes_differ/Browser_ext.apk',
                                         'unit_test_files/apk_.mf_differ_classes_differ/Browser_loc.apk')
        self.assertFalse(res)

        res = tester.cmp_and_process_java('unit_test_files/apk_.mf_same_classes_same/Browser_ext_same.apk',
                                          'unit_test_files/apk_.mf_same_classes_same/Browser_loc_same.apk')
        self.assertTrue(res)

        res = tester.cmp_and_process_java('unit_test_files/apk_.mf_length_differ/DemoMode_ext.apk',
                                          'unit_test_files/apk_.mf_length_differ/DemoMode_loc.apk')
        self.assertFalse(res)

        res = tester.cmp_and_process_java('unit_test_files/apk_.mf_length_same/DemoMode_ext_same.apk',
                                          'unit_test_files/apk_.mf_length_same/DemoMode_loc_same.apk')
        self.assertTrue(res)


class CompareSharedLibrariesTestSuite(unittest.TestCase):
    """ This suite is intended to check shared libraries comparison """

    def test_compare_shared_object(self):
        tester = AFSImageComparator("","","")

        res = tester.compare_shared_object('unit_test_files/so_.text_same/local_camera.omap4.so',
                                           'unit_test_files/so_.text_same/remote_camera.omap4.so')
        self.assertTrue(res)

        res = tester.compare_shared_object('unit_test_files/so_.text_differ/local_libbcc.so',
                                           'unit_test_files/so_.text_differ/remote_libbcc.so')
        self.assertFalse(res)


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(GeneralScriptBehaviourTestSuite)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase(CompareImagesTestSuite)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase(CompareJavaTestSuite)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase(CompareSharedLibrariesTestSuite)
    unittest.TextTestRunner(verbosity=2).run(suite)
