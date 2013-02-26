#!/usr/bin/python
#/usr/bin/python3.2

import os, glob, sys ,re, datetime, subprocess, argparse, hashlib, signal

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
    return subprocess.check_call(['sudo','mount', '-o', 'loop', AbsImgPath, MountPoint], shell=False)

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
    
    def file_ok(self, rel_path, local_mountpoint, ext_mountpoint, check_function, allowed_missings_list):
        local_filepath = re.sub('//', '/',local_mountpoint + rel_path)
        ext_filepath = re.sub('//', '/',ext_mountpoint + rel_path)
        if not os.path.isfile(local_filepath):
                # temp: Warn about missing files separately from error about different ones
            if not rel_path in allowed_missings_list:
                print rel_path + FAIL_COLOR + " MISSING!!!" + END_COLOR
            # temp: end
            return rel_path in allowed_missings_list
        if not os.path.isfile(ext_filepath):
            return False
#    print local_filepath

        return check_function(self, local_filepath, ext_filepath)
    def md5_hashlib_v2(self, cmd):
        """ Execute cmd and return MD5 of it's output using hashlib.md5 for communicate() result """
        self.gReadelfProc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        pout, perr = self.gReadelfProc.communicate()
        ret = hashlib.md5(pout).hexdigest()
        if (pout == ''):
            print WARNING_COLOR + '\"' + ' '.join(cmd) + '\" empty stdout' + END_COLOR
        if (perr != ''):
            print WARNING_COLOR + '\"' + ' '.join(cmd) + '\" strerr: \"' + perr[:-1] + '\"' + END_COLOR
        #print 'md5_hashlib_v2: md5: ' + ret
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
        sum1 = self.md5_hashlib_v2(readelfCmd(file1))
        sum2 = self.md5_hashlib_v2(readelfCmd(file2))
        if (sum1 == sum2):
            #print 'MD5 OK: ' + sum1
            return True
        else:
            #print FAIL_COLOR + file1 + ' ' + sum1 + '\n' + file2 + ' ' + sum2 + END_COLOR
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
            os.mkdir(self.localMountpointPath)
            os.mkdir(self.extMountpointPath)
            mount_loop(localImg, self.localMountpointPath)
            mount_loop(extImg, self.extMountpointPath)
            return
        except OSError:
            print badWorkDirMsg
            return

    cmpMetodDict = { "*.so":compare_shared_object }
    
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
                if not self.file_ok(basename, self.localMountpointPath, self.extMountpointPath, self.cmpMetodDict[extension_pattern] , missings_list):
                    print basename + FAIL_COLOR + " doesn't match!" + END_COLOR
                    areImagesSame = False
        return areImagesSame
def main():
    global tester
    signal.signal(signal.SIGINT,  signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    parser = argparse.ArgumentParser()
    parser.add_argument("local_img", help="path to local")
    parser.add_argument("ext_img", help="path to ext")
    #parser.add_argument("--tmp-dir", type=str, help="path to tmp-dir", required=True)
    args = parser.parse_args()
    local_img = args.local_img
    ext_img = args.ext_img
    print 'local_img = ' + args.local_img
    print 'ext_img = ' + args.ext_img
    #print 'tmp_dir = ' args.tmp_dir

    if not (os.path.isfile(local_img) and
        os.path.isfile(ext_img)):
        parser.print_help()
        print local_img
        print ext_img
        sys.exit(1)

    tester = AFSImageComparator(realpath(local_img), realpath(ext_img))
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
