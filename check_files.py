#!/usr/bin/env python

import os, glob, sys, re, datetime, subprocess, argparse, hashlib, signal, getpass

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
#if realpath utility is available, use it, instead of abspath
    result = os.path.abspath(fname)
    try:
        result = subprocess.check_output(['realpath', fname]).rstrip()
    except OSError, e:
        print 'realpath OSError:', e
    return result

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

def readelfCmd(path):
    """ Generate command list from file path """
    #sections = ['.nonexisting']
    sections = ['.text']

    command = [('-x' + i) for i in sections] # add -x to each section for hex-dump
    command.insert(0, 'readelf')             # add 'readelf' command
    command.append(path)

    return command

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
    cmd = ['sudo','mount', '-o', 'loop', AbsImgPath, MountPoint]
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

WARNING_COLOR = '\033[93m'
FAIL_COLOR = '\033[91m'
OK_COLOR = '\033[92m'
END_COLOR    = '\033[0m'

class AFSImageComparator:

    # file_check() result codes
    FILE_SAME = 0
    FILE_DIFF = 1
    FILE_MISS = 2
    FILE_MISS_ALLOWED = 3

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
        """ Compare md5 for shared object files """
        # Choose here what algo for md5 sum calculation to use
        # On Volodymyr Frolov's opinion md5_hashlib_v2 is the best choice
        sum1 = self.md5_hashlib(readelfCmd(file1))
        sum2 = self.md5_hashlib(readelfCmd(file2))
        if (sum1 == sum2):
            #print 'MD5 OK: ' + sum1
            return True
        else:
            #print FAIL_COLOR + file1 + ' ' + sum1 + '\n' + file2 + ' ' + sum2 + END_COLOR
            return False

    def del_tmp_dir(self, path):
        if os.path.isdir(path):
            subprocess.call(['rm','-rf',str(path)], shell=False)

    def process_apk(self, refer_ext, refer_loc, tmpDirComparison):
        """directly parser for *.apk and *.jar files (unpack to dex)"""
        root_dir = os.path.dirname(refer_loc)
        apk_dir=str(re.sub('\..*^','',os.path.basename(refer_loc)))+'/'
        self.del_tmp_dir(str(tmpDirComparison)+apk_dir)
        os.mkdir(tmpDirComparison+apk_dir)
        locDir = tmpDirComparison+apk_dir+'/loc/'
        extDir = tmpDirComparison+apk_dir+'/ext/'
        os.mkdir(locDir)
        os.mkdir(extDir)
        p1_unzip = subprocess.Popen(["unzip", refer_loc, "-d", locDir], stdout=subprocess.PIPE)
        p1_unzip.communicate()
        p2_unzip = subprocess.Popen(["unzip", refer_ext, "-d", extDir], stdout=subprocess.PIPE)
        p2_unzip.communicate()
        p_dex_loc = subprocess.Popen(["md5sum", str(locDir+'/classes.dex')], stdout=subprocess.PIPE)
        out_loc = p_dex_loc.communicate()[0]
        p_dex_ext = subprocess.Popen(["md5sum", str(extDir+'/classes.dex')], stdout=subprocess.PIPE)
        out_ext = p_dex_ext.communicate()[0]
        if (out_ext[:33]==out_loc[:33]):
            #print "Sources are OK "+apk_dir
            self.del_tmp_dir(tmpDirComparison+apk_dir)
            return True
        else:
            #print tmpDirComparison+apk_dir + FAIL_COLOR + " different sources!"+ END_COLOR
            #del_tmp_dir(tmpDirComparison+apk_dir)
            return False

    def cmp_and_process(self, ext_shared_objects,loc_shared_objects):
        p_ext = subprocess.Popen(['md5sum',ext_shared_objects], stdout=subprocess.PIPE)
        out_ext=p_ext.communicate()[0]
        p_loc = subprocess.Popen(['md5sum',loc_shared_objects], stdout=subprocess.PIPE)
        out_loc=p_loc.communicate()[0]
        if (out_ext[:33]==out_loc[:33]):
            #print "archives are OK"
            return True
        else:
            if self.process_apk(ext_shared_objects,loc_shared_objects,self.tmpDirComparison):
                return True
            else:
                return False

    def __init__(self, localImg, extImg, rootDirPath = '/tmp/'):
        self.gReadelfProc = None
        if not rootDirPath.endswith('/'):
            rootDirPath += '/'
        badWorkDirMsg = "Bad workdir"
        nowString = re.sub('\..*$','',datetime.datetime.now().isoformat('-'))
        self.workDirPath = rootDirPath + nowString + '/'
        try:
            if not (os.path.isdir(rootDirPath) and os.access(rootDirPath, os.W_OK)):
                print badWorkDirMsg
                return ()
            os.mkdir(self.workDirPath)
            self.localMountpointPath = self.workDirPath + 'local_root/'
            self.extMountpointPath = self.workDirPath + 'ext_root/'
            self.tmpDirComparison = self.workDirPath + 'jar_apk_cmp/'
            os.mkdir(self.localMountpointPath)
            os.mkdir(self.extMountpointPath)
            os.mkdir(self.tmpDirComparison)
            mount_loop(localImg, self.localMountpointPath)
            mount_loop(extImg, self.extMountpointPath)
            return
        except OSError:
            print badWorkDirMsg
            return

    cmpMetodDict = { "*.so":compare_shared_object, "*.jar": cmp_and_process, "*.apk": cmp_and_process }
    
    def __del__(self):
        self.umount_loop(self.localMountpointPath)
        self.umount_loop(self.extMountpointPath)

    def run(self):
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
    parser.add_argument("--tmp_dir", help="path to tmp-dir")
    args = parser.parse_args()
    local_img = args.local_img
    ext_img = args.ext_img
    tmp_root = args.tmp_dir
    print 'local_img = ' + args.local_img
    print 'ext_img = ' + args.ext_img
    #print 'tmp_dir = ' args.tmp_dir

    if not (os.path.isfile(local_img) and
        os.path.isfile(ext_img)):
        parser.print_help()
        print local_img
        print ext_img
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
