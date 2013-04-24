#!/usr/bin/env python

import os
import glob
import sys
import re
import datetime
import subprocess
from subprocess import PIPE
import argparse
import hashlib
import signal
import getpass
import shutil
import cStringIO

def DFS(root, skip_symlinks = 1):
    """Depth first search traversal of directory structure."""
    stack = [root]
    visited = {}
    while stack:
        d = stack.pop()
        if d not in visited:  ## just to prevent any possible recursive
                              ## loops
            visited[d] = 1
            yield d
        stack.extend(subdirs(d, skip_symlinks))

def realpath(fname):
    return os.path.normpath(os.path.join(os.getcwd(), fname))

def subdirs(root, skip_symlinks = 1):
    """Given a root directory, returns the first-level subdirectories."""
    try:
        dirs = [os.path.join(root, x)
                for x in os.listdir(root)]
        dirs = filter(os.path.isdir, dirs)
        if skip_symlinks:
            dirs = filter(lambda x: not os.path.islink(x), dirs)
#        dirs.sort()
        return dirs
    except OSError: return []
    except IOError: return []

def linux_like_find(root, pattern):
    files = []
    for subdir in DFS(root):
        files += glob.glob(os.path.join (subdir, pattern))
        files.sort()
    return files

def file_in_list (rel_path, local_list):
    """finding file in list"""
    for local_file in local_list :
        if local_file.endswith(rel_path):
            return True
    return False

def get_elf_sections(path):
    """
    The function gets the list of all ELF sections and returns
    only the list of sections we're interested in:
     - .text (.rel.text, .init.text and other "*.text")
     - .data (and other "*.data")
     - .rodata (and other "*.rodata")
    """
    sections = []
    cmd = ["readelf", "-S", "-W", path]
    readelfOutput = str(subprocess.Popen(cmd, stdout=PIPE,
                                              stderr=PIPE).communicate())
    pattern = "(\s[a-zA-Z_\.]*)+(text|data|rodata)([\.:][A-Za-z_\.]*)*\s"
    matches = re.findall(pattern, readelfOutput)
    # Example of element in matches:
    # (' .rel.', 'text')
    for m in matches:
        section = "".join(m).strip()
        sections.append(section)
    return sections

def determine_missing_elf_sections(filepath, sections1, sections2):
    retval = True
    missed = sections2.difference(sections1) # sections2 - sections1
    if len(missed) != 0:
        if AFSImageComparator.VERBOSE:
            print "{0} {1}    has missing sections: {2}".format(datetime.datetime.now(), filepath, ", ".join(missed))
        else:
            print "   missing sections: {0}".format(", ".join(missed))
        retval = False
    return retval

def get_hash_from_file_or_process(inpobj, hashfunc, blocksize=65356):
    typename = type(inpobj).__name__

    if typename == 'file': buf = inpobj.read(blocksize)
    elif typename == 'Popen': buf = inpobj.stdout.read(blocksize)
    else:
        if AFSImageComparator.VERBOSE:
            print "{0} {1}hashFromFile(): Wrong input object! need file or Popen{2}".format(datetime.datetime.now(), FAIL_COLOR, END_COLOR)
        return

    if len(buf) == 0:
        if typename == 'file':
            if AFSImageComparator.VERBOSE:
                print "{0} {1}hashFromFile(): Wrong input object! need file or Popen {2}{3}".format(datetime.datetime.now(), WARNING_COLOR, inpobj.name, END_COLOR)
        else:
            if AFSImageComparator.VERBOSE:
                print "{0} {1}1get_hash_from_file_or_process(): empty input (Popen object)!{2}".format(datetime.datetime.now(), WARNING_COLOR, END_COLOR)

    while len(buf) > 0:
        hashfunc.update(buf)
        if typename == 'file':
            buf = inpobj.read(blocksize)
        else:
            buf = inpobj.stdout.read(blocksize)
    return hashfunc.hexdigest()

"""Check files existance at both mountpoints and than call to compare function"""

def mount_loop(AbsImgPath, MountPoint):
    cmd = ['sudo','mount', '-o', 'loop,ro', AbsImgPath, MountPoint]
    if AFSImageComparator.VERBOSE:
        print datetime.datetime.now(), ' '.join(cmd)
    return subprocess.check_call(cmd, shell=False)

def signal_handler(signum, frame):
    global tester
    try:
        if tester:
            del tester
    #Print termination message instead off falling to NameError exception
    #for non-existing object in corner case of early script termination.
    except NameError:
        pass
    exitstr = 'Exiting on signal: ' + str(signum)
    sys.exit(exitstr)

if sys.stdout.isatty():
    # output to console
    WARNING_COLOR = '\033[93m'
    FAIL_COLOR = '\033[91m'
    OK_COLOR = '\033[92m'
    END_COLOR = '\033[0m'
else:
    # output is redirected
    WARNING_COLOR = ''
    FAIL_COLOR = ''
    OK_COLOR = ''
    END_COLOR = ''

def timeStamp():
    if AFSImageComparator.VERBOSE:
        return datetime.datetime.now()
    else:
        return ''

class StdoutRedirector(object):
    def __enter__(self):
        self.so = sys.stdout
        self.buff = cStringIO.StringIO()
        sys.stdout = self.buff

    def __exit__(self, exc_type, exc_value, traceback):
        sys.stdout = self.so
        lines = self.buff.getvalue().splitlines()
        self.buff.close()
        timestamp_pattern = '(^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+ )'
        if len(lines) > 0:
            print "\n{0}".format(lines.pop().strip())
        for line in lines:
            if re.match(timestamp_pattern, line):
                print re.sub(timestamp_pattern, '\g<1>    ', line)
            else:
                print '   '+line

class AllowedDifferences(object):
    EXCLUSIONS_FILE_NAME = 'exclusions-list'
    EXCLUSIONS_FILE_PATH = os.path.dirname(sys.argv[0]) + '/' + EXCLUSIONS_FILE_NAME
    def __init__(self, filepath):
        self.excluded_files_list = []
        self.exclusion_rules = {}

        exclusions_file_content = []
        if os.access(filepath, os.R_OK):
            exclusions_file_content = [line.strip() for line in open(filepath)
                        if not (line.strip().startswith('#') or line.strip() == '')]

        # List of files that allowed to be different
        self.excluded_files_list = [line for line in exclusions_file_content if ':' not in line]
        # Dictionary of rules for files to be skipped
        for line in exclusions_file_content:
            if ':' in line:
                key, value = line.split(':')
                # Add "*" to the beginning and replace "*" by ".*" for regular expressions work
                key_RE = re.sub('\*.', '.*', '*' + key)
                self.exclusion_rules[key_RE.strip()] = [it.strip() for it in value.split(',')]

    def getList(self):
        return self.excluded_files_list

    def getListForFile(self, filename):
        skiplist = []
        for key, val in self.exclusion_rules.iteritems():
            if re.match(key, filename):
                skiplist += val
        return skiplist

class AFSImageComparator(object):
    VERBOSE = False
    INT_PACKAGE = ''
    EXT_PACKAGE = ''
    # file_check() result codes
    FILE_SAME = 0
    FILE_DIFF = 1
    FILE_MISS = 2
    FILE_DIFF_ALLOWED = 3

    def __init__(self, localImg, extImg, rootDirPath):
        self.gReadelfProc = None
        self.localMountpointPath = None
        self.extMountpointPath = None
        self.prepare_work_dir(localImg, extImg, rootDirPath)
        self.AllowedDiff = AllowedDifferences(AllowedDifferences.EXCLUSIONS_FILE_PATH)

    def __del__(self):
        if self.localMountpointPath:
            self.umount_loop(self.localMountpointPath)
        if self.extMountpointPath:
            self.umount_loop(self.extMountpointPath)
        if self.workDirPath:
            shutil.rmtree(self.workDirPath)
            if AFSImageComparator.VERBOSE:
                print datetime.datetime.now(), "removed " + self.workDirPath

    def prepare_work_dir(self, localImg, extImg, rootDirPath):
        if (rootDirPath is None) or (not rootDirPath):
            rootDirPath = '/tmp/'
        elif not rootDirPath.endswith('/'):
            rootDirPath += '/'
        badWorkDirMsg = FAIL_COLOR + "Bad workdir" + END_COLOR
        nowString = re.sub('\..*$','',datetime.datetime.now().isoformat('-'))
        self.workDirPath = rootDirPath + nowString
        new_dir_path = self.workDirPath
        index = 1;
        while os.path.exists(new_dir_path):
            if new_dir_path[-3] == ":":
                new_dir_path = new_dir_path + '-' + str(index)
            else:
                old_index_len = len(str(index-1))
                new_dir_path = new_dir_path[:-(old_index_len+1)] + '-' + str(index)
                index += 1
        self.workDirPath = new_dir_path + '/'
        try:
            if not (os.path.isdir(rootDirPath) and os.access(rootDirPath, os.W_OK)):
                print badWorkDirMsg
                return
            os.mkdir(self.workDirPath)
            self.tmpDirComparison = self.workDirPath + 'jar_apk_cmp/'
            os.mkdir(self.tmpDirComparison)

            if (not localImg) or (not extImg) or (localImg is None) or (extImg is None):
                self.localMountpointPath = None
                self.extMountpointPath = None
            else:
                self.localMountpointPath = self.workDirPath + 'local_root/'
                self.extMountpointPath = self.workDirPath + 'ext_root/'
                os.mkdir(self.localMountpointPath)
                os.mkdir(self.extMountpointPath)
                if AFSImageComparator.VERBOSE:
                    print datetime.datetime.now(), self.localMountpointPath
                    print datetime.datetime.now(), self.extMountpointPath
                mount_loop(localImg, self.localMountpointPath)
                mount_loop(extImg, self.extMountpointPath)
        except OSError:
            print datetime.datetime.now(), badWorkDirMsg

    def file_check(self, rel_path, local_mountpoint, ext_mountpoint, check_function):
        local_filepath = re.sub('//', '/',local_mountpoint + rel_path)
        ext_filepath = re.sub('//', '/',ext_mountpoint + rel_path)

        if rel_path not in self.AllowedDiff.getList():
            # Check file
            if not os.path.isfile(local_filepath):
                ret = AFSImageComparator.FILE_MISS
            elif check_function(self, local_filepath, ext_filepath) is True:
                ret = AFSImageComparator.FILE_SAME
            else:
                ret = AFSImageComparator.FILE_DIFF
        else:
            # Don't check file and implicitly return FILE_SAME
            ret = AFSImageComparator.FILE_DIFF_ALLOWED
            if AFSImageComparator.VERBOSE:
                print "{0} {1} was not compared! It is in exlusions list".format(datetime.datetime.now(), rel_path)
        return ret

    # Deprecated method
    def md5_hashlib(self, cmd):
        """ Execute cmd and return MD5 of it's output using hashlib.md5 for communicate() result """
        self.gReadelfProc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE)
        pout, perr = self.gReadelfProc.communicate()
        ret = hashlib.md5(pout).hexdigest()
        if (pout == ''):
            if AFSImageComparator.VERBOSE:
                print datetime.datetime.now(), WARNING_COLOR + '\"' + ' '.join(cmd) + '\" empty stdout' + END_COLOR
        if (perr != ''):
            if AFSImageComparator.VERBOSE:
                print datetime.datetime.now(), WARNING_COLOR + '\"' + ' '.join(cmd) + '\" strerr: \"' + perr[:-1] + '\"' + END_COLOR
        #print 'md5: ' + ret
        return ret

    def hashOfCmd(self, cmd):
        """ Execute cmd and return hash of it's output using one of hashlib functions """
        self.gReadelfProc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE)
        ret = get_hash_from_file_or_process(self.gReadelfProc, hashlib.sha1()) # we can define here which of hashlib.algorithms to use
        err = self.gReadelfProc.stderr.read()

        self.gReadelfProc.stdout.close()
        self.gReadelfProc.stderr.close()

        if len(err) > 0:
            if AFSImageComparator.VERBOSE:
                print datetime.datetime.now(), WARNING_COLOR + ' '.join(cmd) + ' : ' + err + END_COLOR

        return ret

    def umount_loop(self, MountPoint):
        try:
            if self.gReadelfProc:
                if (self.gReadelfProc.poll() is None):
                    self.gReadelfProc.terminate()
            subprocess.check_call(['sudo','umount', MountPoint])
        except subprocess.CalledProcessError, e:
            print datetime.datetime.now(), 'umount exited with code:', e.returncode, 'see lsof output:'
            subprocess.call(['lsof', MountPoint])

    def compare_shared_object(self, file1, file2):
        """ Compare hash for shared object files """
        result = True
        sections1 = set(get_elf_sections(file1))
        sections2 = set(get_elf_sections(file2))
        result = determine_missing_elf_sections(file1, sections1, sections2) \
                 and determine_missing_elf_sections(file2, sections2, sections1)

        sections = sections1.intersection(sections2) # common section list
        iterator = 0
        for section in sections:
            cmd1 = ["readelf", "-x", section, file1]
            cmd2 = ["readelf", "-x", section, file2]
            sum1 = self.hashOfCmd(cmd1)
            sum2 = self.hashOfCmd(cmd2)
            if (sum1 != sum2):
                iterator += 1
                if AFSImageComparator.VERBOSE:
                    print "{0} {1}{2}) {3} has different {4} ELF section{5}".format(datetime.datetime.now(), FAIL_COLOR, iterator, file1, section, END_COLOR)
                else:
                    print "{0}{1}) different {2} ELF section{3}".format(FAIL_COLOR, iterator, section, END_COLOR)
                result = False
        return result

    def del_tmp_dir(self, path):
        if os.path.isdir(path):
            subprocess.call(['rm','-rf',str(path)], shell=False)

    def unzip (self,src,dst):
        if not os.path.isfile(src):
            if AFSImageComparator.VERBOSE:
                print datetime.datetime.now(), "no such file: {0}".format(src)
            return
        os.mkdir(dst)
        with open(os.devnull, 'w') as dev_null:
            subprocess.call(["unzip", src, "-d", dst], stdout = dev_null)

    def compare_and_process_java(self, loc_file, ext_file):
        with open(loc_file) as f_loc:
            sum_loc = get_hash_from_file_or_process(f_loc, hashlib.sha1())
        with open(ext_file) as f_ext:
            sum_ext = get_hash_from_file_or_process(f_ext, hashlib.sha1())

        if (sum_loc == sum_ext):
            #print "archives are OK", loc_file
            return True
        elif self.compare_aapt_results(loc_file, ext_file):
            return self.compare_packages_by_content(loc_file, ext_file)
        else:
            return False

    def get_aapt_results(self, package_path):
        # quoted from: http://elinux.org/Android_aapt
        # aapt list -a: This is similar to doing the following three commands in sequence:
        # aapt list <pkg> ; aapt dump resources <pkg> ; aapt dump xmltree <pkg> AndroidManifest.xml.
        command = ['aapt', 'list', '-a', package_path]
        try:
            out, err = subprocess.Popen(command, stdout=PIPE, stderr=PIPE).communicate()
            if len(err) > 0:
                if AFSImageComparator.VERBOSE:
                    print "{0} {1}{2}{3}".format(datetime.datetime.now(), FAIL_COLOR, err, END_COLOR)
            if len(out) == 0:
                if AFSImageComparator.VERBOSE:
                    print "{0} {1}empty aapt output!{2}".format(datetime.datetime.now(), WARNING_COLOR, END_COLOR)
                return out

            # Truncate android:versionName to three main digits, for example: 4.1.2
            #pattern = '(android:versionName.*?[0-9]\.[0-9]\.[0-9])(.*?)(\")'
            #m = re.search(pattern, out)
            #if m is not None:
            #    out = re.sub(m.group(2), '', out)
            out = re.sub('(android:versionName.*?[0-9]\.[0-9]\.[0-9])(.*?)(\" \(Raw: \"[0-9]\.[0-9]\.[0-9])(.*?)(\"\))', '\g<1>\g<3>\g<5>', out)
            # Turn output to list of lines and sort it, because sometimes list are same but order differs
            outlist = out.splitlines()
            outlist.sort()
            return outlist
        except:
            return None

    def aapt_diffs_to_file(self, set_aapt, aapt_out_file_branched, package):
        with open (aapt_out_file_branched,'w+') as file_aapt_diff:
            file_aapt_diff.write('Package:'+package+'\n')
            list_aapt = list(set_aapt)
            list_aapt.sort()
            for line in list_aapt:
                file_aapt_diff.write(line+'\n')

    def show_and_compare_aapt_diffs(self, list1, list2, branch, filepath):
        MAX_AAPT_OUTPUT_LINES_PRINTED = 10
        aapt_file_out = os.path.basename(filepath)
        diffs = list( set(list1) - set(list2) )
        if len(diffs) > 0:
            print "{0}{1}Branch {2} differences: {3}{4}".format(timeStamp(), END_COLOR, branch, len(diffs), END_COLOR)
            index = 1
            for diff in diffs:
                if (index == MAX_AAPT_OUTPUT_LINES_PRINTED) and (len(diffs) >= MAX_AAPT_OUTPUT_LINES_PRINTED) and (not AFSImageComparator.VERBOSE):
                    print "{0}   ...{1}".format(FAIL_COLOR, END_COLOR)
                    print "{0}Difference is too large to be displayed - please,"\
                          " find details in the following files:{1}".format(FAIL_COLOR, END_COLOR)
                    print "{0}Internal Motorola branch (main-jb-omap-tablet): "\
                          "./app_{1}.appt__main-jb-omap-tablet.txt{2}".format(FAIL_COLOR, aapt_file_out, END_COLOR)
                    self.aapt_diffs_to_file(set(list1),'app_'+aapt_file_out+'__main-jb-omap-tablet.txt', AFSImageComparator.INT_PACKAGE)
                    print "{0}External Motorola branch (omap-bringup-jb-tablet): "\
                          "./app_{1}.appt__omap-bringup-jb-tablet.txt{2}".format(FAIL_COLOR, aapt_file_out, END_COLOR)
                    self.aapt_diffs_to_file(set(list2),'app_'+aapt_file_out+'__omap-bringup-jb-tablet.txt', AFSImageComparator.EXT_PACKAGE)
                elif (AFSImageComparator.VERBOSE) or (index < MAX_AAPT_OUTPUT_LINES_PRINTED):
                    print "{0}{1}   {2}) {3}{4}".format(timeStamp(),FAIL_COLOR, index, diff, END_COLOR)
                index += 1
            return False
        return True

    def compare_aapt_results(self, package_path1, package_path2):
        lineslist1 = self.get_aapt_results(package_path1)
        lineslist2 = self.get_aapt_results(package_path2)
        return self.show_and_compare_aapt_diffs(lineslist1, lineslist2, "main-jb-omap-tablet",package_path1) \
               and self.show_and_compare_aapt_diffs(lineslist2, lineslist1, "omap-bringup-jb-tablet", package_path1)

    def compare_packages_by_content(self, loc_path, ext_path):
        # get files lists using aapt
        filelist     = subprocess.Popen(['aapt', 'list', loc_path], stdout=PIPE).communicate()[0]
        filelist_ext = subprocess.Popen(['aapt', 'list', ext_path], stdout=PIPE).communicate()[0]
        filelist     = filelist.splitlines()
        filelist_ext = filelist_ext.splitlines()
        filelist.sort()
        filelist_ext.sort()

        if filelist != filelist_ext:
            #print FAIL_COLOR + 'file-lists obtained by aapt differ!: ' + loc_path + END_COLOR
            return False

        apk_dir = str(self.tmpDirComparison) + str(re.sub('\..*^','',os.path.basename(loc_path)))+'/'
        self.del_tmp_dir(apk_dir)
        os.mkdir(apk_dir)
        locDir = apk_dir + '/loc/'
        extDir = apk_dir + '/ext/'
        self.unzip(loc_path, locDir)
        self.unzip(ext_path, extDir)

        retval = True
        iterator = 0
        skiplist = self.AllowedDiff.getListForFile(loc_path)
        for f in filelist:
            if os.path.isfile(locDir + f) and f not in skiplist:
                with open(locDir + f) as f1:
                    sum1 = get_hash_from_file_or_process(f1, hashlib.sha1())
                with open(extDir + f) as f2:
                    sum2 = get_hash_from_file_or_process(f2, hashlib.sha1())
                if sum1 != sum2:
                    iterator += 1
                    retval = False
                    if AFSImageComparator.VERBOSE:
                        print "{0} {1}{2}) checksums differ! {3}{4}{5}".format(datetime.datetime.now(), FAIL_COLOR, iterator, locDir, f, END_COLOR)
                    else:
                        print "{0}{1}) different {2}{3}".format(FAIL_COLOR, iterator, f, END_COLOR)
                #else:
                    #print locDir + filelist[i] + ' checksums same - ok'

        if retval:
            self.del_tmp_dir(apk_dir)
        return retval

    compareMethodDictionary = {"*.so": compare_shared_object, "*.ko": compare_shared_object,
                               "*.jar": compare_and_process_java, "*.apk": compare_and_process_java }
    totalCountDictionary = {"*.so": 0, "*.ko": 0, "*.jar": 0, "*.apk": 0}
    differentCountDictionary = {"*.so": 0, "*.ko": 0, "*.jar": 0, "*.apk": 0}

    def run(self):
        EXAMINED_BUILD_BRANCH_NAME = 'omap-bringup-jb-tablet'
        if (self.localMountpointPath is None) or (self.extMountpointPath is None):
            print timeStamp(), FAIL_COLOR + "Cannot run dummy AFSImageComparator!" + END_COLOR + "\nInstances without .img files are for unit tests only."
            return False
        areImagesSame=True

        aapt_available = True
        if subprocess.call(['which', 'aapt'], stdout=PIPE, stderr=PIPE) != 0:
            aapt_available = False
            del self.compareMethodDictionary['*.jar']
            del self.compareMethodDictionary['*.apk']
            print timeStamp(), FAIL_COLOR + 'No aapt utility found, so do not compare java files and fail implicitly at the end' + END_COLOR

        for extension_pattern in self.compareMethodDictionary.keys():
            print "\n==========================="
            print "Comparing {0} files... ".format(extension_pattern)
            print "==========================="
            ext_files_list = linux_like_find (self.extMountpointPath, extension_pattern)
            self.totalCountDictionary[extension_pattern] = len(ext_files_list)

            for file_wholename in ext_files_list:
                with StdoutRedirector() as stdout_redirector:
                    basename = re.sub(self.extMountpointPath, '/', file_wholename)
                    checkret = self.file_check(basename, self.localMountpointPath, self.extMountpointPath, self.compareMethodDictionary[extension_pattern])
                    if checkret is AFSImageComparator.FILE_SAME:
                        pass
                    elif checkret is AFSImageComparator.FILE_DIFF_ALLOWED:
                        pass
                    elif checkret is AFSImageComparator.FILE_DIFF:
                        areImagesSame = False
                        self.differentCountDictionary[extension_pattern] += 1
                        print "{1} {0:<4}{2} {3}doesn't match!{4}".format(str(self.differentCountDictionary[extension_pattern]) + ".",
                                                                               timeStamp(), basename, FAIL_COLOR, END_COLOR)
                    elif checkret is AFSImageComparator.FILE_MISS:
                        areImagesSame = False
                        self.differentCountDictionary[extension_pattern] += 1
                        print "{1} {0:<4}{2} {3}missing in branch {4}!{5}".format(
                                                                    str(self.differentCountDictionary[extension_pattern]) + ".",
                                                                    timeStamp(),
                                                                    basename, FAIL_COLOR, EXAMINED_BUILD_BRANCH_NAME, END_COLOR
                                                                        )
            print "\nFinished comparing {1} \'{0}\' files".format(extension_pattern, self.totalCountDictionary[extension_pattern])

        if aapt_available is not True:
            areImagesSame = False   # implicitly set to False
                                    # java files were not compared without aapt

        with open(AllowedDifferences.EXCLUSIONS_FILE_PATH) as exclusions_file:
            exclusions_list = exclusions_file.read()
            print '\n****************** Exclusion rules ******************\n', exclusions_list
        print '\n----------------- Summary -----------------'
        for key in self.totalCountDictionary.keys():
            if self.totalCountDictionary[key] > 0:
                group_perc = self.differentCountDictionary[key] / float(self.totalCountDictionary[key]) * 100
            else:
                group_perc = 0
            print '{0:>3} {1:<5} files differ:{2:>5}% ({0}/{3})'.format(self.differentCountDictionary[key],
                                                                        key, round(group_perc, 1),
                                                                        self.totalCountDictionary[key])
        if sum(self.totalCountDictionary.values()) > 0:
            total_perc = sum(self.differentCountDictionary.values()) / float(sum(self.totalCountDictionary.values())) * 100
        else:
            total_perc = 0
        print '\n Total difference:{0:>5}% ({1}/{2})'.format(round(total_perc, 1),
                                                             sum(self.differentCountDictionary.values()),
                                                             sum(self.totalCountDictionary.values()))
        print '-------------------------------------------\n'

        return areImagesSame

def main():
    print 'Android image comparator v1.0 - GlobalLogic Ukraine, 2013\n'
    global tester
    signal.signal(signal.SIGINT,  signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    parser = argparse.ArgumentParser()
    parser.add_argument("local_img", help="path to local")
    parser.add_argument("ext_img", help="path to ext")
    parser.add_argument("--tmp-dir", help="path to tmp-dir")
    parser.add_argument("-v", "--verbose", help="verbose output", action="store_true")
    args = parser.parse_args()
    AFSImageComparator.VERBOSE = args.verbose
    local_img = args.local_img
    ext_img = args.ext_img
    tmp_root = args.tmp_dir

    if not (os.path.isfile(local_img) and
        os.path.isfile(ext_img)):
        print datetime.datetime.now(), FAIL_COLOR + "Toubles while accessing system images." + END_COLOR
        if AFSImageComparator.VERBOSE:
            print datetime.datetime.now(), local_img
            print datetime.datetime.now(), ext_img
        parser.print_help()
        sys.exit(1)

    tester = AFSImageComparator(realpath(local_img), realpath(ext_img), tmp_root)
    OK = tester.run()
    del tester
    if OK:
        print '{0}Images are same \n{1}\n{2}{3}'.format(OK_COLOR, local_img, ext_img, END_COLOR)
        result = 0
    else:
        print '{0}Images are different \n{1}\n{2}{3}'.format(FAIL_COLOR, local_img, ext_img, END_COLOR)
        result = 255
    sys.exit(result)


if __name__ == '__main__':
    main()
