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
    pattern = "(\s[a-z.]*\.)(text|data|rodata)(\.[a-z.]*)*\s"
    matches = re.findall(pattern, readelfOutput)
    # Example of element in matches:
    # (' .rel.', 'text')
    for m in matches:
        section = "".join(m).strip()
        sections.append(section)
    return sections

def readelfCmd(path):
    """ Generate command from retrieved section list file path """
    sections = get_elf_sections(path)

    command = [('-x' + i) for i in sections] # add -x to each section for hex-dump
    command.insert(0, 'readelf')             # add 'readelf' command
    command.append(path)

    return command

def hashFromFileOrProc(inpobj, hashfunc, blocksize=65356):
    typename = type(inpobj).__name__

    if typename == 'file': buf = inpobj.read(blocksize)
    elif typename == 'Popen': buf = inpobj.stdout.read(blocksize)
    else:
        print FAIL_COLOR + 'hashFromFile(): Wrong input object! need file or Popen' + END_COLOR
        return

    if len(buf) == 0:
        print WARNING_COLOR + 'hashFromFile(): empty input!' + END_COLOR

    while len(buf) > 0:
        hashfunc.update(buf)
        if typename == 'file': buf = inpobj.read(blocksize)
        else: buf = inpobj.stdout.read(blocksize)
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
#Print termination message instead off falling to NameError exception for non-existing object in corner case of early script termination.
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

    #compare_manifests() result codes
    MF_SAME = 1
    MF_DIFF = 0
    MF_NULL = -1

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
        ret = hashFromFileOrProc(self.gReadelfProc, hashlib.sha1()) # we can define here which of hashlib.algorithms to use
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
        cmd1 = readelfCmd(file1)
        cmd2 = readelfCmd(file2)

        sum1 = self.hashOfCmd(cmd1)
        sum2 = self.hashOfCmd(cmd2)

        if (sum1 == sum2):
            #print 'hash OK: ' + sum1
            return True
        else:
            #print FAIL_COLOR + file1 + ' ' + sum1 + '\n' + file2 + ' ' + sum2 + END_COLOR
            return False

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

    def are_apk_same(self, refer_ext, refer_loc):
        """directly parser for *.apk and *.jar files (unpack to dex)"""
        root_dir = os.path.dirname(refer_loc)
        apk_dir=str(self.tmpDirComparison)+str(re.sub('\..*^','',os.path.basename(refer_loc)))+'/'
        self.del_tmp_dir(apk_dir)
        os.mkdir(apk_dir)
        locDir = apk_dir+'/loc/'
        extDir = apk_dir+'/ext/'
        self.unzip(refer_loc,locDir)
        self.unzip(refer_ext,extDir)
        cmp_result = self.compare_manifests(locDir + '/META-INF/MANIFEST.MF', extDir + '/META-INF/MANIFEST.MF')
        if cmp_result == AFSImageComparator.MF_DIFF :
            return False
        elif cmp_result == AFSImageComparator.MF_NULL:
            #maybe manifests are NULL,thus try to take md5 directly
            return self.compare_classes(locDir + '/classes.dex', extDir + '/classes.dex')
        else:
            self.del_tmp_dir(apk_dir)
            return True

    def compare_classes(self,locPath,extPath):
        if not os.path.isfile(str(locPath)):
            return False #workaround. We have to discuss how to parse if no classes.dex and manifest.ml is empty
        else:
            with open (locPath) as class_loc:
                class_hash_loc = hashFromFileOrProc(class_loc,hashlib.sha1())
            with open (extPath) as class_ext:
                class_hash_ext = hashFromFileOrProc(class_ext,hashlib.sha1())
            if (class_hash_loc==class_hash_ext):
                return True
            else:
                print '\nManifest is null. classes.dex hashsums are different.'
                return False

    def parse_manifest(self,pathMF):
        manifestMF={}
        with open(pathMF,'r') as fileMF:
            lineMF = str(fileMF.readline())
            while (lineMF):
                lineMF = str(fileMF.readline())
                if (lineMF.startswith('Name')):
                    # skipping binary manifests.xml workaround
                    if (lineMF.endswith('AndroidManifest.xml\r\n')):
                        continue
                    lineMF_sha = str(fileMF.readline())
                    if (lineMF_sha.startswith('SHA1-Digest')):
                        manifestMF[lineMF[6:]] = lineMF_sha[13:]
        return manifestMF

    def compare_manifests(self,locPath,extPath):
        manifest_loc = self.parse_manifest(locPath)
        manifest_ext = self.parse_manifest(extPath)
        #maybe manifests are NULL,thus try to take md5 directly
        if not manifest_loc and not manifest_ext:
            return AFSImageComparator.MF_NULL
        for cheking_path in manifest_ext.keys():
            if not cheking_path in manifest_loc:
                print ('\nno such path: ' + cheking_path).rstrip()
                #print 'No such Attribute: '+ FAIL_COLOR +'Different sources, at least '+ END_COLOR, locDir+cheking_path
                return AFSImageComparator.MF_DIFF
            if (manifest_ext[cheking_path] == manifest_loc[cheking_path]):
                pass
            else:
                print ('\ndifference in: ' + cheking_path).rstrip()
                #print FAIL_COLOR +'Different sources hash '+ END_COLOR, locDir+cheking_path
                return AFSImageComparator.MF_DIFF
        #print locDir, 'Sources hash ore OK'

    def cmp_and_process_java(self, ext_shared_objects,loc_shared_objects):
        p_ext = subprocess.Popen(['md5sum',ext_shared_objects], stdout=subprocess.PIPE)
        out_ext=p_ext.communicate()[0]
        p_loc = subprocess.Popen(['md5sum',loc_shared_objects], stdout=subprocess.PIPE)
        out_loc=p_loc.communicate()[0]
        if (out_ext[:33]==out_loc[:33]):
            #print "archives are OK"
            return True
        else:
            return self.are_apk_same(ext_shared_objects,loc_shared_objects)

    cmpMetodDict = {"*.so": compare_shared_object, "*.ko": compare_shared_object,
                    "*.jar": cmp_and_process_java, "*.apk": cmp_and_process_java }
    
    def run(self):
        if (self.localMountpointPath is None) or (self.extMountpointPath is None):
            print FAIL_COLOR + "Cannot run dummy AFSImageComparator!" + END_COLOR + "\nInstances without .img files are for unit tests only."
            return False
        areImagesSame=True
        try:
            with open('allowed-missing-files') as missings_file:
                missings_list = missings_file.read().splitlines()
        #        print missings_list
        except IOError:
                print WARNING_COLOR + "Something went wrong when tried to read shared object files list difference" + END_COLOR
                missings_list = []

        for extension_pattern in self.cmpMetodDict.keys():
            ext_files_list = linux_like_find (self.extMountpointPath, extension_pattern)

            for file_wholename in ext_files_list:
                basename = re.sub(self.extMountpointPath, '/', file_wholename)
                checkret = self.file_check(basename, self.localMountpointPath, self.extMountpointPath, self.cmpMetodDict[extension_pattern] , missings_list)
                if checkret is AFSImageComparator.FILE_SAME:
                    pass
                elif checkret is AFSImageComparator.FILE_MISS_ALLOWED:
                    pass
                elif checkret is AFSImageComparator.FILE_DIFF:
                    areImagesSame = False
                    print basename + FAIL_COLOR + " doesn't match!" + END_COLOR
                elif checkret is AFSImageComparator.FILE_MISS:
                    areImagesSame = False
                    print basename + FAIL_COLOR + " missing!" + END_COLOR
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
    #print 'tmp_dir = ' args.tmp_dir

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
        result = 255
    sys.exit(result)


if __name__ == '__main__':
    main()
