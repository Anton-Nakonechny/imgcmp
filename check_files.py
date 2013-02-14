#!/usr/bin/python
#/usr/bin/python3.2

import os, glob, sys ,re

def usage(retcode):
    print "Usage: " + os.path.basename(sys.argv[0]) + " <local_build_mountpoint> <external_build_mountpoint>."
    print "  Display android system.img conformity info"
    sys.exit(retcode)

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


def file_ok (rel_path, local_mountpoint, allowed_missings_list):
    if os.path.isfile(local_mountpoint + rel_path):
        return True
    return rel_path in allowed_missings_list


WARNING_COLOR = '\033[93m'
FAIL_COLOR = '\033[91m'
END_COLOR    = '\033[0m' 

#local_shared_objects = linux_like_find (local_root, "*.so")

if not ( len(sys.argv) == 3 and
    os.path.isdir(sys.argv[1]) and
    os.path.isdir(sys.argv[2])):
    local_root="/mnt/system-patch/"
    ext_root="/mnt/system-122/"
else:
    local_root = sys.argv[1]
    ext_root = sys.argv[2]
#    usage(1)


try:
    with open('diff') as missings_file:
        missings_list = missings_file.read().splitlines()
except IOError:
        print WARNING_COLOR + "Something went wrong when tried to read shared object files list difference" + END_COLOR
        missings_list = []
ext_shared_objects  = linux_like_find (ext_root, "*.so")

for so_wholename in ext_shared_objects:
    basename = re.sub(ext_root, '', so_wholename) 
    if not file_ok(basename, local_root, missings_list):
        print basename + FAIL_COLOR + " must be there!" + END_COLOR

