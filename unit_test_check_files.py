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
import os
import time
import signal

from subprocess import Popen, PIPE

from check_files import AFSImageComparator, FAIL_COLOR, WARNING_COLOR, OK_COLOR, END_COLOR, realpath, get_elf_sections, determine_missing_elf_sections

class GeneralScriptBehaviourTestSuite(unittest.TestCase):
    """
    This suite is intended to check:
        - workdir mounting
        - creating necessary dirs
        - cleaning workdir and tmp dirs after script run
    """
    @staticmethod
    def __are_images_mounted(mount_point1, mount_point2):
        res = False
        mounts = str(Popen(["mount"], stdout=PIPE).communicate()[0])
        if (mount_point1 in mounts) or (mount_point2 in mounts):
            res = True
        return res

    def test_posix_signals_handling(self):
        """
        Runs image checking, kills the script with SIGTERM and SIGINT and checks,
        if images are unmounted.
        If test fails, it makes sense to have a look at time.sleep arguments values.
        """
        imgdir = "unit_test_files/img_.same_allowed/"
        img1 = realpath(imgdir + "same_in_allowed_loc.img")
        img2 = realpath(imgdir + "same_in_allowed_ext.img")

        def run_compare_packages_script():
            args = ["python", "-u", "check_files.py", img1, img2, "-v"]
            process = Popen(args, stdout=PIPE)
            return process

        def umount(mount_point):
            args = ["sudo", "umount", mount_point]
            Popen(args)

        def check_signal_handling(sig):
            process = run_compare_packages_script()
            img_workdir1 = str(process.stdout.readline())[27:-2]
            img_workdir2 = str(process.stdout.readline())[27:-2]
            delay = 0
            while not(self.__are_images_mounted(img_workdir1, img_workdir2) or delay>=2):
                time.sleep(delay)
                delay += 0.1
            process.send_signal(sig)
            time.sleep(0.3)     # let script have time to umount loops after catching signal
            areMounted = self.__are_images_mounted(img_workdir1, img_workdir2)
            self.assertFalse(delay>=2)
            if areMounted:
                umount(img_workdir1)
                umount(img_workdir2)
            self.assertFalse(areMounted)

        signalsToCheck = [signal.SIGINT, signal.SIGTERM]
        for sig in signalsToCheck:
            check_signal_handling(sig)
            time.sleep(0.2)

    def test_preparation_and_cleaning_workdir(self):
        """
        Creates tester object and checks if images are mounted on loop.
        Checks if images are umounted and workDir is removed after deletion.
        """
        tester = AFSImageComparator("unit_test_files/img_.same_not_allowed/same_not_in_allowed_loc.img",
                                    "unit_test_files/img_.same_not_allowed/same_not_in_allowed_ext.img",
                                    "")
        res = os.path.isdir(tester.localMountpointPath)
        self.assertTrue(res)
        res = os.path.isdir(tester.extMountpointPath)
        self.assertTrue(res)
        img_workdir1 = tester.localMountpointPath
        img_workdir2 = tester.extMountpointPath
        res = self.__are_images_mounted(img_workdir1[:-1], img_workdir2[:-1])
        self.assertTrue(res)
        tester_WorkDir = tester.workDirPath
        del tester
        res = os.path.isdir(tester_WorkDir)
        self.assertFalse(res)
        res = self.__are_images_mounted(img_workdir1[:-1], img_workdir2[:-1])
        self.assertFalse(res)

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
        tester = AFSImageComparator("unit_test_files/img_.same_allowed/same_in_allowed_loc.img",
                                    "unit_test_files/img_.same_allowed/same_in_allowed_loc.img","")
        res = tester.run()
        self.assertTrue(res)


class CompareJavaTestSuite(unittest.TestCase):
    """ This suite is intended to check Java (.apk and .jar) comparison """

    def test_jar_comparison(self):
        tester = AFSImageComparator("","","")

        res = tester.compare_and_process_java('unit_test_files/jar_.list_same_data_differ/qewl_ext.jar',
                                              'unit_test_files/jar_.list_same_data_differ/qewl_loc.jar')
        self.assertFalse(res)

        res = tester.compare_and_process_java('unit_test_files/jar_.list_same_data_same/qewl_ext_same.jar',
                                              'unit_test_files/jar_.list_same_data_same/qewl_loc_same.jar')
        self.assertTrue(res)

        res = tester.compare_and_process_java('unit_test_files/jar_.file_sha_differ/apache-xml_ext.jar',
                                              'unit_test_files/jar_.file_sha_differ/apache-xml_loc.jar')
        self.assertFalse(res)

        res = tester.compare_and_process_java('unit_test_files/jar_.file_sha_same/apache-xml_ext_same.jar',
                                              'unit_test_files/jar_.file_sha_same/apache-xml_loc_same.jar')
        self.assertTrue(res)

    def test_apk_comparison(self):
        tester = AFSImageComparator("","","")

        res = tester.compare_and_process_java('unit_test_files/apk_.sha_differ/Browser_ext.apk',
                                              'unit_test_files/apk_.sha_differ/Browser_loc.apk')
        self.assertFalse(res)

        res = tester.compare_and_process_java('unit_test_files/apk_.sha_same/Browser_ext_same.apk',
                                              'unit_test_files/apk_.sha_same/Browser_loc_same.apk')
        self.assertTrue(res)

        res = tester.compare_and_process_java('unit_test_files/apk_.list_length_differ/DemoMode_ext.apk',
                                              'unit_test_files/apk_.list_length_differ/DemoMode_loc.apk')
        self.assertFalse(res)

        res = tester.compare_and_process_java('unit_test_files/apk_.list_length_same/DemoMode_ext_same.apk',
                                              'unit_test_files/apk_.list_length_same/DemoMode_loc_same.apk')
        self.assertTrue(res)


class CompareELFObjectsTestSuite(unittest.TestCase):
    """ This suite is intended to check shared libraries comparison """

    def test_elf_sections_not_empty(self):
        sections = get_elf_sections('unit_test_files/ko_.testmodules/nfs.ko')
        res = len(sections) != 0
        self.assertTrue(res)

    def test_missing_elf_sections(self):
        sections1 = set(['.text', '.data', '.rodata'])
        sections2 = set(['.text', '.data', '.rodata'])
        res = determine_missing_elf_sections('sections1', sections1, sections2)
        self.assertTrue(res)

        sections2 = set(['.text', '.data', '.rodata', '.rel.text'])
        res = determine_missing_elf_sections('sections1', sections1, sections2)
        self.assertFalse(res)

        res = determine_missing_elf_sections('sections2', sections2, sections1)
        self.assertTrue(res)

    def test_compare_shared_object(self):
        tester = AFSImageComparator("","","")

        res = tester.compare_shared_object('unit_test_files/so_.text_same/local_camera.omap4.so',
                                           'unit_test_files/so_.text_same/remote_camera.omap4.so')
        self.assertTrue(res)

        res = tester.compare_shared_object('unit_test_files/so_.text_differ/local_libbcc.so',
                                           'unit_test_files/so_.text_differ/remote_libbcc.so')
        self.assertFalse(res)

    def test_compare_kernel_modules(self):
        tester = AFSImageComparator("","","")

        res = tester.compare_shared_object('unit_test_files/ko_.testmodules/local_lib80211_same.ko',
                                           'unit_test_files/ko_.testmodules/remote_lib80211_same.ko')
        self.assertTrue(res)

        res = tester.compare_shared_object('unit_test_files/ko_.testmodules/local_lib80211_same.ko',
                                           'unit_test_files/ko_.testmodules/nfs.ko')
        self.assertFalse(res)

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(GeneralScriptBehaviourTestSuite)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase(CompareImagesTestSuite)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase(CompareJavaTestSuite)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase(CompareELFObjectsTestSuite)
    unittest.TextTestRunner(verbosity=2).run(suite)
