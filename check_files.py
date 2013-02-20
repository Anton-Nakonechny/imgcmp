#!/usr/bin/python
#/usr/bin/python3.2

import os, glob, sys ,re, datetime, subprocess, argparse

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
    result = str(os.popen("realpath " + fname).read()).rstrip()
    if result:
        return result
    else:
        return os.path.abspath(fname)

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
    #sections = ['.dynsym', '.dynstr', '.hash', '.rel.dyn', '.rel.plt', '.plt', '.text', '.ARM.exidx', '.ARM.extab', '.rodata', '.data.rel.ro.local', '.init_array', '.data.rel.ro', '.fini_array', '.dynamic', '.got', '.data', '.bss', '.comment', '.note.gnu.gold-version', '.ARM.attributes',  '.gnu_debuglink', '.shstrtab']
    #sections = ['.text', '.gnu_debuglink']
    sections = ['.text','.dynsym']

    command = [('-x' + i) for i in sections] # add -x to each section for hex-dump
    command.insert(0, 'readelf')             # add 'readelf' command
    command.append(path)

    return command

def md5Cmd(cmd):
    """ Execute cmd and return MD5 of it's output """
    # pipe1: command execution
    pipe1 = subprocess.Popen(cmd, stdout=subprocess.PIPE)

    # pipe2: md5sum of command output
    pipe2 = subprocess.Popen('md5sum', stdin=pipe1.stdout, stdout=subprocess.PIPE)
    pipe1.stdout.close() # Allow pipe1 to receive a SIGPIPE if pipe2 exits.

    output = pipe2.communicate()[0]
    return (output[:-4]) # cut out last four symbols: (  -\n) from output

"""dummy compare md5 function returning true allways"""
def compare_shared_object(dummy1, dummy2):
    return True

"""Check files existance at both mountpoints and than call to compare function"""
def file_ok(rel_path, local_mountpoint, ext_mountpoint, check_function, allowed_missings_list):
    local_filepath = re.sub('//', '/',local_mountpoint + rel_path)
    ext_filepath = re.sub('//', '/',ext_mountpoint + rel_path)
    if not os.path.isfile(local_filepath):
        return rel_path in allowed_missings_list
    if not os.path.isfile(ext_filepath):
        return False
#    print local_filepath

    return check_function(local_filepath, ext_filepath)


def mount_loop(AbsImgPath, MountPoint):
    return subprocess.check_call(['sudo','mount', '-o', 'loop', AbsImgPath, MountPoint], shell=False)

def umount_loop(MountPoint):
    return subprocess.check_call(['sudo','umount', MountPoint], shell=False)

def prepare(rootDirPath, localImg, extImg):
    if not rootDirPath.endswith('/'):
        rootDirPath += '/'
    badWorkDirMsg = "Bad workdir"
    workDirPath = rootDirPath + nowString + '/'
    try:
        if not (os.path.isdir(rootDirPath) and os.access(rootDirPath, os.W_OK)):
            print badWorkDirMsg
            return ()
        os.mkdir(workDirPath)
        localMountpointPath = workDirPath + 'local_root/'
        extMountpointPath = workDirPath + 'ext_root/'
        os.mkdir(localMountpointPath)
        os.mkdir(extMountpointPath)
        mount_loop(localImg, localMountpointPath)
        mount_loop(extImg, extMountpointPath)
        return (localMountpointPath, extMountpointPath)
    except OSError:
        print badWorkDirMsg
        return ()

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

WARNING_COLOR = '\033[93m'
FAIL_COLOR = '\033[91m'
END_COLOR    = '\033[0m' 

#local_shared_objects = linux_like_find (local_root, "*.so")

nowString = re.sub('\..*$','',datetime.datetime.now().isoformat('-'))

cmpMetodDict = { "*.so":compare_shared_object }

if not (os.path.isfile(local_img) and
    os.path.isfile(ext_img)):
    parser.print_help()
    print local_img 
    print ext_img
    sys.exit(1)
#    localImgRealpath = '/home/x0169011/afs/main-moto-jb/out/target/product/cdma_spyder-p1c_spyder/system.img'
#    extImgRealPath = '/home/x0169011/daily/p1c_spyder-cdma_spyder_mmi-userdebug-4.1.2-9.8.2O_122-2074-test-keys-Verizon-US/system.img'

rootDirPath = '/tmp/'
dirs = prepare(rootDirPath, realpath(local_img), realpath(ext_img))
local_root=dirs[0]
ext_root=dirs[1]

try:
    with open('allowed-missing-files') as missings_file:
        missings_list = missings_file.read().splitlines()
#        print missings_list
except IOError:
        print WARNING_COLOR + "Something went wrong when tried to read shared object files list difference" + END_COLOR
        missings_list = []

for extension_pattern in cmpMetodDict.keys():
    ext_files_list = linux_like_find (ext_root, extension_pattern)

    for file_wholename in ext_files_list:
        basename = re.sub(ext_root , '/', file_wholename) 
        if not file_ok(basename, local_root, ext_root, compare_shared_object, missings_list):
            print basename + FAIL_COLOR + " doesn't match!" + END_COLOR

umount_loop(dirs[0])
umount_loop(dirs[1])
