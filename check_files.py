#!/usr/bin/env python

import os
import glob
import sys
import re
import datetime
import subprocess
import argparse
import hashlib
import signal
import getpass
import shutil

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
    readelfOutput = str(subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE).communicate())
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
        print "{0} has missing sections: {1}".format(filepath, ", ".join(missed))
        retval = False
    return retval

def get_hash_from_file_or_process(inpobj, hashfunc, blocksize=65356):
    typename = type(inpobj).__name__

    if typename == 'file': buf = inpobj.read(blocksize)
    elif typename == 'Popen': buf = inpobj.stdout.read(blocksize)
    else:
        print FAIL_COLOR + 'hashFromFile(): Wrong input object! need file or Popen' + END_COLOR
        return

    if len(buf) == 0:
        if typename == 'file':
            print WARNING_COLOR + 'get_hash_from_file_or_process(): empty input!', inpobj.name + END_COLOR
        else:
            print WARNING_COLOR + 'get_hash_from_file_or_process(): empty input (Popen object)!' + END_COLOR

    while len(buf) > 0:
        hashfunc.update(buf)
        if typename == 'file':
            buf = inpobj.read(blocksize)
        else:
            buf = inpobj.stdout.read(blocksize)
    return hashfunc.hexdigest()

#def md5_hashlib_v1(cmd):
#    """ Execute cmd and return MD5 of it's output using hashlib.md5 for stdout.read() """
#    global p
#    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#    ret = hashlib.md5(p.stdout.read()).hexdigest()
#    perr = p.stderr.read()
#    if (perr != ''):
#        print WARNING_COLOR + '\"' + ' '.join(cmd) + '\" stderr: \"' + perr[:-1] + '\"' + END_COLOR
#    #print 'md5_hashlib_v1: md5: ' + ret
#    return ret
#
#def md5_md5sum(cmd):
#    """ Execute cmd and return MD5 of it's output using md5sum utility """
#    global p
#    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#    p2 = subprocess.Popen('md5sum', stdin=p.stdout, stdout=subprocess.PIPE)
#    perr = p.stderr.read()
#    p.stdout.close() # Allow p to receive a SIGPIPE if p2 exits.
#    p2out = p2.communicate()[0]
#    if (perr != ''):
#        print WARNING_COLOR + '\"' + ' '.join(cmd) + '\" strerr: \"' + perr[:-1] + '\"' + END_COLOR
#    #print 'md5_md5sum: md5:     ' + p2out[:-4]
#    return p2out[:-4]
#

"""Check files existance at both mountpoints and than call to compare function"""

def mount_loop(AbsImgPath, MountPoint):
    cmd = ['sudo','mount', '-o', 'loop,ro', AbsImgPath, MountPoint]
    print ' '.join(cmd)
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
    END_COLOR    = '\033[0m'
else:
    # output is redirected
    WARNING_COLOR = ''
    FAIL_COLOR = ''
    OK_COLOR = ''
    END_COLOR    = ''

class AFSImageComparator:

    # file_check() result codes
    FILE_SAME = 0
    FILE_DIFF = 1
    FILE_MISS = 2
    FILE_MISS_ALLOWED = 3

    def __init__(self, localImg, extImg, rootDirPath):
        self.gReadelfProc = None
        self.localMountpointPath = None
        self.extMountpointPath = None
        self.prepare_work_dir(localImg, extImg, rootDirPath)

    def __del__(self):
        if self.localMountpointPath:
            self.umount_loop(self.localMountpointPath)
        if self.extMountpointPath:
            self.umount_loop(self.extMountpointPath)
        if self.workDirPath:
            shutil.rmtree(self.workDirPath)
            print "removed " + self.workDirPath

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
                mount_loop(localImg, self.localMountpointPath)
                mount_loop(extImg, self.extMountpointPath)
        except OSError:
            print badWorkDirMsg

    def file_check(self, rel_path, local_mountpoint, ext_mountpoint, check_function, allowed_missings_list):
        local_filepath = re.sub('//', '/',local_mountpoint + rel_path)
        ext_filepath = re.sub('//', '/',ext_mountpoint + rel_path)
        if not os.path.isfile(local_filepath):
            if (rel_path in allowed_missings_list):
                return AFSImageComparator.FILE_MISS_ALLOWED
            else:
                return AFSImageComparator.FILE_MISS
        if check_function(self, local_filepath, ext_filepath) is True:
            return AFSImageComparator.FILE_SAME
        else:
            return AFSImageComparator.FILE_DIFF

    # Deprecated method
    def md5_hashlib(self, cmd):
        """ Execute cmd and return MD5 of it's output using hashlib.md5 for communicate() result """
        self.gReadelfProc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        pout, perr = self.gReadelfProc.communicate()
        ret = hashlib.md5(pout).hexdigest()
        if (pout == ''):
            print WARNING_COLOR + '\"' + ' '.join(cmd) + '\" empty stdout' + END_COLOR
        if (perr != ''):
            print WARNING_COLOR + '\"' + ' '.join(cmd) + '\" strerr: \"' + perr[:-1] + '\"' + END_COLOR
        #print 'md5: ' + ret
        return ret

    def hashOfCmd(self, cmd):
        """ Execute cmd and return hash of it's output using one of hashlib functions """
        self.gReadelfProc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ret = get_hash_from_file_or_process(self.gReadelfProc, hashlib.sha1()) # we can define here which of hashlib.algorithms to use
        err = self.gReadelfProc.stderr.read()

        self.gReadelfProc.stdout.close()
        self.gReadelfProc.stderr.close()

        if len(err) > 0:
            print WARNING_COLOR + ' '.join(cmd) + ' : ' + err + END_COLOR

        return ret

    def umount_loop(self, MountPoint):
        try:
            if self.gReadelfProc:
                if (self.gReadelfProc.poll() is None):
                    self.gReadelfProc.terminate()
            subprocess.check_call(['sudo','umount', MountPoint])
        except subprocess.CalledProcessError, e:
            print 'umount exited with code:', e.returncode, 'see lsof output:'
            subprocess.call(['lsof', MountPoint])

    def compare_shared_object(self, file1, file2):
        """ Compare hash for shared object files """
        result = True
        sections1 = set(get_elf_sections(file1))
        sections2 = set(get_elf_sections(file2))
        result = determine_missing_elf_sections(file1, sections1, sections2) and determine_missing_elf_sections(file2, sections2, sections1)

        sections = sections1.intersection(sections2) # common section list
        for section in sections:
            cmd1 = ["readelf", "-x", section, file1]
            cmd2 = ["readelf", "-x", section, file2]
            sum1 = self.hashOfCmd(cmd1)
            sum2 = self.hashOfCmd(cmd2)
            if (sum1 != sum2):
                print "{0}{1} has different {2} ELF section{3}".format(FAIL_COLOR, file1, section, END_COLOR)
                result = False
        return result

    def del_tmp_dir(self, path):
        if os.path.isdir(path):
            subprocess.call(['rm','-rf',str(path)], shell=False)

    def unzip (self,src,dst):
        if not os.path.isfile(src):
            print 'no such file: '+src
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
            return self.compare_packages_by_contents(loc_file, ext_file)
        else:
            return False

    def get_aapt_results(self, package_path):
        # quoted from: http://elinux.org/Android_aapt
        # aapt list -a: This is similar to doing the following three commands in sequence:
        # aapt list <pkg> ; aapt dump resources <pkg> ; aapt dump xmltree <pkg> AndroidManifest.xml.
        command = ['aapt', 'list', '-a', package_path]
        try:
            out, err = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
            if len(err) > 0:
                print FAIL_COLOR + err + END_COLOR
            if len(out) == 0:
                print WARNING_COLOR + 'empty aapt output!' + END_COLOR
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

    def compare_aapt_results(self, package_path1, package_path2):
        lineslist1 = self.get_aapt_results(package_path1)
        lineslist2 = self.get_aapt_results(package_path2)
        if not lineslist1 or not lineslist2 or (len(lineslist1) == 0):
            print FAIL_COLOR + 'aapt results are empty!' + END_COLOR
            return False
        if len(lineslist1) != len(lineslist2):
            print FAIL_COLOR + 'aapt results are of different lenghts!', len(lineslist1), len(lineslist2), package_path1, END_COLOR
            return False

        retval = True
        for i in range(len(lineslist1)):
            if lineslist1[i] != lineslist2[i]:
                retval = False
                print FAIL_COLOR + 'aapt results have different lines!\n' + lineslist1[i] + '\n' + lineslist2[i] + END_COLOR
                break

        return retval

    def need_to_skip_line(self, path):
        '''used to skip directories; and files from skiplist'''
        if not os.path.isfile(path):
            return True
        skiplist = ['AndroidManifest.xml','MANIFEST.MF', 'CERT.RSA', 'CERT.SF']
        for sk in skiplist:
            if path.endswith(sk):
                return True
        return False

    def compare_packages_by_contents(self, loc_path, ext_path):
        # get files lists using aapt
        filelist     = subprocess.Popen(['aapt', 'list', loc_path], stdout=subprocess.PIPE).communicate()[0]
        filelist_ext = subprocess.Popen(['aapt', 'list', ext_path], stdout=subprocess.PIPE).communicate()[0]
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
        for i in range(len(filelist)):
            if not self.need_to_skip_line(locDir+filelist[i]):
                with open(locDir + filelist[i]) as f1:
                    sum1 = get_hash_from_file_or_process(f1, hashlib.sha1())
                with open(extDir + filelist[i]) as f2:
                    sum2 = get_hash_from_file_or_process(f2, hashlib.sha1())
                if sum1 != sum2:
                    retval = False
                    print FAIL_COLOR + 'checksums differ! ' + locDir + filelist[i] + END_COLOR
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
        if (self.localMountpointPath is None) or (self.extMountpointPath is None):
            print FAIL_COLOR + "Cannot run dummy AFSImageComparator!" + END_COLOR + "\nInstances without .img files are for unit tests only."
            return False
        areImagesSame=True
        try:
            #Assume there must be such 'allowed-missing-files' file in the same dir.
            script_parent_dir = os.path.dirname(sys.argv[0])
            with open('allowed-missing-files') as missings_file:
                missings_list = missings_file.read().splitlines()
        except IOError:
                print WARNING_COLOR + "Something went wrong when tried to read shared object files list difference" + END_COLOR
                missings_list = []

        aapt_available = True
        if subprocess.call(['which', 'aapt']) != 0:
            aapt_available = False
            del self.compareMethodDictionary['*.jar']
            del self.compareMethodDictionary['*.apk']
            print FAIL_COLOR + 'No aapt utility found, so do not compare java files and fail implicitly at the end' + END_COLOR

        for extension_pattern in self.compareMethodDictionary.keys():
            ext_files_list = linux_like_find (self.extMountpointPath, extension_pattern)
            self.totalCountDictionary[extension_pattern] = len(ext_files_list)

            for file_wholename in ext_files_list:
                basename = re.sub(self.extMountpointPath, '/', file_wholename)
                checkret = self.file_check(basename, self.localMountpointPath, self.extMountpointPath, self.compareMethodDictionary[extension_pattern] , missings_list)
                if checkret is AFSImageComparator.FILE_SAME:
                    pass
                elif checkret is AFSImageComparator.FILE_MISS_ALLOWED:
                    pass
                elif checkret is AFSImageComparator.FILE_DIFF:
                    areImagesSame = False
                    self.differentCountDictionary[extension_pattern] += 1
                    print basename + FAIL_COLOR + " doesn't match!" + END_COLOR
                elif checkret is AFSImageComparator.FILE_MISS:
                    areImagesSame = False
                    self.differentCountDictionary[extension_pattern] += 1
                    print basename + FAIL_COLOR + " missing!" + END_COLOR

        if aapt_available is not True:
            areImagesSame = False   # implicitly set to False
                                    # java files were not compared without aapt

        if areImagesSame is not True:
            print '\n----------------- Summary -----------------'
            for key in self.totalCountDictionary.keys():
                print '{0:>3} {1:<5} files differ (compared: {2:>3})'.format(self.differentCountDictionary[key], key, self.totalCountDictionary[key])
            print '-------------------------------------------\n'

        return areImagesSame

def main():
    global tester
    signal.signal(signal.SIGINT,  signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    parser = argparse.ArgumentParser()
    parser.add_argument("local_img", help="path to local")
    parser.add_argument("ext_img", help="path to ext")
    parser.add_argument("--tmp-dir", help="path to tmp-dir")
    args = parser.parse_args()
    local_img = args.local_img
    ext_img = args.ext_img
    tmp_root = args.tmp_dir
    print 'local_img = ' + args.local_img
    print 'ext_img = ' + args.ext_img

    if not (os.path.isfile(local_img) and
        os.path.isfile(ext_img)):
        print FAIL_COLOR + "Toubles while accessing system images." + END_COLOR
        print local_img
        print ext_img
        parser.print_help()
        sys.exit(1)

    tester = AFSImageComparator(realpath(local_img), realpath(ext_img), tmp_root)
    OK = tester.run()
    del tester
    if OK:
        print OK_COLOR + "Images are same" + END_COLOR
        result = 0
    else:
        print FAIL_COLOR + "Images are different" + END_COLOR
        result = 255
    sys.exit(result)


if __name__ == '__main__':
    main()
