#!/usr/bin/env python

import subprocess, os, argparse, sys, tarfile, zipfile, re, datetime
from check_files import AFSImageComparator, FAIL_COLOR, WARNING_COLOR, OK_COLOR, END_COLOR, linux_like_find

def extractSystemImage(archive, folder):
    try:
        ImageFilename = 'system.img'
        if not os.access(folder, os.W_OK):
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
        return None 

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--internal_package", "-i", help="path to fresh build", required=True)
    parser.add_argument("--external_package", "-e", help="path to latest daily build", required=True)
    parser.add_argument("--tmp-dir", help="path to tmp-dir", required=False)
    args = parser.parse_args()

    nowString = re.sub('\..*$','',datetime.datetime.now().isoformat('-'))
   
    if not (os.path.isfile(args.internal_package) and os.access(args.internal_package, os.R_OK)
        and os.path.isfile(args.external_package) and os.access(args.external_package, os.R_OK)):
        
        print FAIL_COLOR + "Problems when reading packages" + END_COLOR + '\n'
        parser.print_help()
        sys.exit(1)
    if args.tmp_dir:
        tmpDir = args.tmp_dir if args.tmp_dir.endswith('/') else args.tmp_dir + '/'
    else:
        tmpDir = '/tmp/'
    workPath =  tmpDir + nowString + '/'
    os.mkdir(workPath)
    internalSysImageRetlist = extractSystemImage(args.internal_package, workPath)
    if internalSysImageRetlist is None:
        print FAIL_COLOR + 'Failed to extract sysImage' + END_COLOR + "\nfrom " + args.internal_package
        sys.exit(1)
    externalSysImageRetlist = extractSystemImage(args.external_package, workPath)
    if externalSysImageRetlist is None:
        print FAIL_COLOR + 'Failed to extract sysImage' + END_COLOR + "\nfrom " + args.external_package
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
