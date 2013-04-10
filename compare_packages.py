#!/usr/bin/env python

import subprocess
import os
import argparse
import sys
import tarfile
import zipfile
import re
import datetime
import signal
import shutil

from operator import itemgetter
from check_files import AFSImageComparator, FAIL_COLOR, WARNING_COLOR, OK_COLOR, END_COLOR, linux_like_find

def extractSystemImage(archive, folder):
    try:
        ImageFilename = 'system.img'
        if not os.access(folder, os.W_OK):
            print "No access to destination folder"
            return None
        Package = tarfile.open(archive)
        
        buildName = re.sub(".tar.*$", '', re.sub('^fastboot-','', os.path.basename(Package.name))) #cut-off 'fastboot' world an extension to obtain package name
        systemRegexp = re.compile(".*" + ImageFilename + "$") 
        systemImageArchivePathList = filter(systemRegexp.match, Package.getnames())
        if len(systemImageArchivePathList)!=1:
            print "Too much system.img in " + Package.name
            return None

        if not buildName:
            buildName = dummy
        extractTo = folder + buildName + '/'
        os.mkdir(extractTo)
        if AFSImageComparator.VERBOSE:
            print 'extracting ' + systemImageArchivePathList[0] + '\nfrom ' + archive
        Package.extract(systemImageArchivePathList[0], extractTo)
        return linux_like_find(extractTo, ImageFilename)
    except:
        print "Exception when were extracting"
        return None 


def addCTimeKey(x):
    return [x, os.path.getctime(x)]

def findNewestBuild(folder, template):
    #the addCTimeKey function in the next line is expected to return list of it's argument and hash-key (i.e. ctime) [x, hash(x)]
    FoundList =  sorted([addCTimeKey(x) for x in linux_like_find (folder, template)], key=itemgetter(1), reverse=True)
    #print FoundList
    return FoundList[0][0]

def cleanup():
    if AFSImageComparator.VERBOSE:
        print "Making extracted sysImages and workDir cleanup\nrm -rf", workPath
    if workPath and os.path.isdir(workPath):
        shutil.rmtree(workPath)

def signal_handler(signum, frame):
    global systemImageComparator
    try:
        if systemImageComparator:
            del systemImageComparator
    #Print termination message instead off falling to NameError exception
    #for non-existing object in corner case of early script termination.
    except NameError:
        pass
    exitstr = 'Exiting on signal: ' + str(signum)
    cleanup()
    sys.exit(exitstr)

def main():
    print 'Android burn package comparator v1.0 - GlobalLogic Ukraine, 2013\n'
    global systemImageComparator
    signal.signal(signal.SIGINT,  signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser()
    parser.add_argument("--internal_package", "-i", help="path to fresh build", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--external_package", "-e", help="path to latest daily build")
    group.add_argument("--external_dir", "-d", help="path to daily builds folder")
    parser.add_argument("--tmp-dir", help="path to tmp-dir", required=False)
    parser.add_argument("--pattern", "-p", help="archive package name pattern, used with -d option", required=False, default = "*.gz")
    parser.add_argument("-v", "--verbose", help="Verbose output", action="store_true")
    args = parser.parse_args()
    AFSImageComparator.VERBOSE = args.verbose

    nowString = re.sub('\..*$','',datetime.datetime.now().isoformat('-'))

    if not (os.path.isfile(args.internal_package) and os.access(args.internal_package, os.R_OK)):
        print FAIL_COLOR + "Problems with reading internal package" + END_COLOR + '\n'
        parser.print_help()
        sys.exit(1)

    if args.external_package:
        if not (os.path.isfile(args.external_package) and os.access(args.external_package, os.R_OK)):
            print FAIL_COLOR + "Problems with reading external package" + END_COLOR + '\n'
            parser.print_help()
            sys.exit(1)
        externalPackage = args.external_package
    else:
        if AFSImageComparator.VERBOSE:
            print "Ext dir is " + args.external_dir
        externalPackage = findNewestBuild(args.external_dir, args.pattern)
    if args.tmp_dir:
        tmpDir = args.tmp_dir if args.tmp_dir.endswith('/') else args.tmp_dir + '/'
    else:
        tmpDir = '/tmp/'
    global workPath;
    workPath = tmpDir + nowString + '/'
    os.mkdir(workPath)
    print "Comparing " + args.internal_package + " to " + externalPackage
    internalSysImageRetlist = extractSystemImage(args.internal_package, workPath)
    if internalSysImageRetlist is None:
        print FAIL_COLOR + 'Failed to extract internal sysImage' + END_COLOR + "\nfrom " + args.internal_package
        cleanup()
        sys.exit(1)
    externalSysImageRetlist = extractSystemImage(externalPackage, workPath)
    if externalSysImageRetlist is None:
        print FAIL_COLOR + 'Failed to extract external sysImage' + END_COLOR + "\nfrom " + externalPackage
        cleanup()
        sys.exit(1)

    systemImageComparator = AFSImageComparator(internalSysImageRetlist[0], externalSysImageRetlist[0], workPath)
    OK = systemImageComparator.run()
    del systemImageComparator

    if OK:
        print OK_COLOR + "SysImages are same" + END_COLOR
        result = 0
    else:
        result = 255

    cleanup()
    sys.exit(result)

if __name__ == '__main__':
    main()
