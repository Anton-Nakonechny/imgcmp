#!/usr/bin/env python

import subprocess, os, argparse, sys, tarfile, zipfile, re, datetime
from check_files import AFSImageComparator, FAIL_COLOR, WARNING_COLOR, OK_COLOR, END_COLOR, linux_like_find
from operator import itemgetter

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
        print 'extracting ' + systemImageArchivePathList[0] + '\nfrom ' + archive
        Package.extract(systemImageArchivePathList[0], extractTo)
        return linux_like_find(extractTo, ImageFilename)
    except:
        print "Exception when were extracting"
        return None 


def addCTimeKey(x):
    return [x, os.path.getctime(x)]

def findNewestBuild(folder, template):
#the addCTimeKey function in the next line is expected to return list of it's argument and hash-key (i.g. ctime) [x, hash(x)]
   FindedList =  sorted([addCTimeKey(x) for x in linux_like_find (folder, template)], key=itemgetter(1), reverse=True)
#   print FindedList
   return FindedList[0][0] 

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--internal_package", "-i", help="path to fresh build", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--external_package", "-e", help="path to latest daily build")
    group.add_argument("--external_dir", "-d", help="path to daily builds folder")
    parser.add_argument("--tmp-dir", help="path to tmp-dir", required=False)
    parser.add_argument("--pattern", "-p", help="archive package name pattern, used with -d option", required=False, default = "*.gz")
    args = parser.parse_args()

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
        print "Ext dir is " + args.external_dir
        externalPackage = findNewestBuild(args.external_dir, args.pattern)
    
    print "Comparing to " + externalPackage 
    if args.tmp_dir:
        tmpDir = args.tmp_dir if args.tmp_dir.endswith('/') else args.tmp_dir + '/'
    else:
        tmpDir = '/tmp/'
    workPath =  tmpDir + nowString + '/'
    os.mkdir(workPath)
    internalSysImageRetlist = extractSystemImage(args.internal_package, workPath)
    if internalSysImageRetlist is None:
        print FAIL_COLOR + 'Failed to extract internal sysImage' + END_COLOR + "\nfrom " + args.internal_package
        sys.exit(1)
    externalSysImageRetlist = extractSystemImage(externalPackage, workPath)
    if externalSysImageRetlist is None:
        print FAIL_COLOR + 'Failed to extract external sysImage' + END_COLOR + "\nfrom " + externalPackage
        sys.exit(1)
    
    systemComparator = AFSImageComparator(internalSysImageRetlist[0], externalSysImageRetlist[0], workPath)
    
    systemComparator.run()
    OK = systemComparator.run()
    del systemComparator
    if OK:
        print OK_COLOR + "SysImages are same" + END_COLOR
        result = 0
    else:
        result = 255

    print "You might want to cleanup\n    rm -rf " + workPath
    sys.exit(result)

if __name__ == '__main__':
    main()
