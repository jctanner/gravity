#!/usr/bin/env python

import argparse
import os
import shutil
import sys

from sh import createrepo
from sh import find
from sh import git
from sh import make


MODULE_WHITELIST = [
    'modules/__init__.py',
]


MODULE_UTIL_WHITELIST = [
    'module_utils/__init__.py',
    'module_utils/common',
    'module_utils/compat',
    'module_utils/facts',
    'module_utils/parsing',
    '_text',
    'basic',
    'connection.py',
    'json_utils',
    'pycompat24',
    'six',
    'urls',
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--noclean', action='store_true')
    args = parser.parse_args()

    src_repo = 'https://github.com/jctanner/ansible'
    src_branch = 'MAZER_DEMO_BRANCH'
    src_dir = '/tmp/ansible.mazer.checkout'
    dst_dir = '/tmp/ansible.mazer.build'

    if not args.noclean:

        if not os.path.exists(src_dir):
            git.clone('--branch=%s' % src_branch, src_repo, src_dir)

        if os.path.exists(dst_dir):
            shutil.rmtree(dst_dir)
        shutil.copytree(src_dir, dst_dir)

        module_files = find(os.path.join(dst_dir, 'lib', 'ansible', 'modules'))
        module_files = [x.strip() for x in module_files]
        for mf in module_files:
            if mf.endswith('/modules'):
                continue
            if not os.path.exists(mf):
                continue
            found = False
            for wl in MODULE_WHITELIST:
                if wl in mf:
                    found = True
                    break
            if not found:
                if os.path.isdir(mf):
                    shutil.rmtree(mf)
                else:
                    os.remove(mf)

        module_util_files = find(os.path.join(dst_dir, 'lib', 'ansible', 'module_utils'))
        module_util_files = [x.strip() for x in module_util_files]
        for muf in module_util_files:
            if muf.endswith('/module_utils'):
                continue
            if not os.path.exists(muf):
                continue
            found = False
            for wl in MODULE_UTIL_WHITELIST:
                if wl in muf:
                    found = True
                    break
            if not found:
                if os.path.isdir(muf):
                    shutil.rmtree(muf)
                else:
                    os.remove(muf)

        try:
            make.clean(_cwd=dst_dir)
            make('rpm', _cwd=dst_dir)
        except Exception as e:
            print(e.stdout)
            sys.exit(1)

    repodir = '/var/cache/gravity/repos/rpm'
    repodata_dir = os.path.join(repodir, 'repodata')
    if os.path.exists(repodata_dir):
        shutil.rmtree(repodata_dir)

    rpms = find(
        repodir,
        '-maxdepth',
        '1',
        '-name',
        '*MAZERDEMO*.rpm')
    for rpm in rpms:
        os.remove(rpm.strip())

    rpms = find(
        os.path.join(dst_dir, 'rpm-build'),
        '-maxdepth',
        '1',
        '-name',
        '*.rpm')
    for rpm in rpms:
        shutil.copy(rpm.strip(), repodir)

    createrepo('.', _cwd=repodir)


if __name__ == "__main__":
    main()
