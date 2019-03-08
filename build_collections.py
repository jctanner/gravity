#!/usr/bin/env python

import argparse
import json
#import logging
import glob
import os
import requests
import shutil
import subprocess
import sys
import yaml

from bs4 import BeautifulSoup
from logzero import logger
from sh import createrepo
from sh import git


DEVEL_URL = 'https://github.com/nitzmahone/ansible.git'
DEVEL_BRANCH = 'collection_content_load'

#VARDIR = os.environ.get('GRAVITY_VAR_DIR', '/var/cache/gravity')
VARDIR = os.environ.get('GRAVITY_VAR_DIR', 'cache')
COLLECTION_NAMESPACE = 'builtins'
COLLECTION_PACKAGE_PREFIX = 'ansible-collection-'
COLLECTION_PREFIX = ''
COLLECTION_INSTALL_PATH = '/usr/share/ansible/content/ansible_collections'
MODULE_UTIL_BLACKLIST = [
    '_text',
    'basic',
    'common.collections',
    'common.dict_transformations',
    'common.removed',
    'config',
    'legacy',
    'parsing.convert_bool',
    'six',
    'six.moves',
    'six.moves.http_client',
    'six.moves.urllib',
    'six.moves.urllib.error',
    'six.moves.urllib.parse',
    'facts',
    'facts.timeout',
    'urls'
]


def _run_command(cmd):
    logger.debug(cmd)
    p = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    (so, se) = p.communicate()
    so = so.decode('utf-8')
    se = se.decode('utf-8')
    return (p.returncode, so, se)


def run_command(cmd=None):
    (rc, so, se) = _run_command(cmd)
    return {
        'rc': rc,
        'so': so,
        'se': se
    }


def version_from_tar(tb):
    istar = True
    if not tb.endswith('tar.gz') or tb.endswith('.git'):
        istar = False

    logger.info('assemble %s' % tb)
    tbbn = os.path.basename(tb)

    if istar:
        edir = tbbn.replace('.tar.gz', '')
    else:
        edir = tb

    if istar:
        eversion = edir.replace('ansible-', '')
    else:
        rfile = os.path.join(VARDIR, 'releases', tb, 'lib', 'ansible', 'release.py')
        with open(rfile, 'r') as f:
            flines = f.readlines()
        for fline in flines:
            if fline.startswith('__version__'):
                eversion = fline.strip().split()[-1].replace('"', '').replace("'", '')
                break
    return eversion


def is_current_tar(tarfile):
    thisversion = tarfile.replace('ansible-', '')
    if thisversion[0] != '2':
        return False
    if thisversion[2] not in ['7']:
        return False
    return True


def get_releases():
    baseurl = 'https://releases.ansible.com/ansible/'
    logger.info('fetch %s' % baseurl)
    rr = requests.get(baseurl)
    soup = BeautifulSoup(rr.text, u'html.parser')
    links = soup.findAll('a')
    hrefs = [x.attrs['href'] for x in links]
    tarballs = [x for x in hrefs if x.endswith('tar.gz')]
    tarballs = [x for x in tarballs if 'latest' not in x]
    tarballs = [x for x in tarballs if 'dev' not in x]
    tarballs = [x for x in tarballs if 'beta' not in x]
    tarballs = [x for x in tarballs if 'alpha' not in x]
    tarballs = [x for x in tarballs if '0a' not in x]
    tarballs = [x for x in tarballs if '0b' not in x]
    tarballs = [x for x in tarballs if 'rc' not in x]
    #tarballs = [x for x in tarballs if x.startswith('ansible-2')]
    tarballs = [x for x in tarballs if is_current_tar(x)]
    tarballs = sorted(tarballs)
    logger.info('%s tarballs found' % len(tarballs))

    cachedir = os.path.join(VARDIR, 'releases')
    if not os.path.exists(cachedir):
        os.makedirs(cachedir)

    for tb in tarballs:
        # fetch the tarball
        logger.info('release tarball %s' % tb)
        url = baseurl + '/' + tb
        dst = os.path.join(cachedir, tb)
        if not os.path.exists(dst):
            logger.info('fetching %s' % url)
            rr = requests.get(url, allow_redirects=True)
            open(dst, 'wb').write(rr.content)

        # extract the tarball
        edir = tb.replace('.tar.gz', '')
        epath = os.path.join(cachedir, edir)
        if not os.path.exists(epath):
            logger.info('extracting %s' % tb)
            cmd = 'cd %s; tar xzvf %s' % (cachedir, tb)
            p = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            (so, se) = p.communicate()


    # make a devel checkout
    dpath = os.path.join(cachedir, 'devel.git')
    cmd = 'git clone %s %s' % (DEVEL_URL, dpath)
    logger.info(cmd)
    if not os.path.exists(dpath):
        git.clone(DEVEL_URL, dpath)
    if DEVEL_BRANCH:
        (rc, so, se) = _run_command('cd %s; git branch | egrep --color=never ^\\* | head -n1' % dpath)
        thisbranch = so.replace('*', '').strip()
        if thisbranch != DEVEL_BRANCH:
            logger.debug('%s != %s' % (thisbranch, DEVEL_BRANCH))
            (rc, so, se) = _run_command('cd %s; git checkout %s' % (dpath, DEVEL_BRANCH))
            assert rc == 0

    return {}


def index_collections(devel_only=False, refresh=False):
    #cachedir = os.path.join(VARDIR, 'collections')
    rpmdir = os.path.join(VARDIR, 'repos', 'rpm')
    releasedir = os.path.join(VARDIR, 'releases')
    colbasedir = os.path.join(VARDIR, 'collections')

    tarballs = []
    if not devel_only:
        tarballs += glob.glob('%s/*.tar.gz' % releasedir)
    tarballs += ['devel.git']

    tarballs = sorted(tarballs)

    for tb in tarballs:
        _index_collections(tb, releasedir, colbasedir, refresh=refresh)


def _index_collections(tb, releasedir, colbasedir, refresh=False):

    metadir = os.path.join(VARDIR, 'meta')
    if not os.path.exists(metadir):
        os.makedirs(metadir)

    istar = True
    if not tb.endswith('tar.gz') or tb.endswith('.git'):
        istar = False

    logger.info('assemble %s' % tb)
    tbbn = os.path.basename(tb)

    if istar:
        edir = tbbn.replace('.tar.gz', '')
    else:
        edir = tb

    eversion = version_from_tar(tb)

    jf = os.path.join(metadir, 'ansible-' + eversion + '-meta.json')
    if os.path.exists(jf) and not refresh:
        return

    cmd = 'cd %s/lib/ansible/modules ; find . -type d' % os.path.join(releasedir, edir)
    logger.info(cmd)
    (rc, so, se) = _run_command(cmd)
    logger.info('%s rc: %s' % (cmd, rc))
    if rc != 0:
        logger.info(se)
    dirs = [x.strip() for x in so.split('\n')if x.strip()]

    cmd = 'cd %s/lib/ansible/modules ; find . -type f' % os.path.join(releasedir, edir)
    logger.info(cmd)
    (rc, so, se) = _run_command(cmd)
    logger.info('%s rc: %s' % (cmd, rc))
    if rc != 0:
        logger.info(se)
    files = [x.strip() for x in so.split('\n') if x.strip()]

    collections = {}
    for dirn in dirs:
        dirn = dirn.lstrip('./')
        if not dirn:
            continue
        collections[dirn] = {}
        collections[dirn]['basedir'] = os.path.join(releasedir, edir)
        collections[dirn]['name'] = COLLECTION_PREFIX + dirn.replace('/', '_')
        collections[dirn]['version'] = eversion
        collections[dirn]['action'] = []
        collections[dirn]['modules'] = []
        collections[dirn]['module_utils'] = []
        collections[dirn]['docs_fragments'] = []

    for fn in files:
        logger.info(fn)
        fn = fn.lstrip('./')
        dirn = os.path.dirname(fn)
        if not dirn:
            continue
        if os.path.basename(fn) == '__init__.py':
            continue
        collections[dirn]['modules'].append(fn)
        mfn = os.path.join(releasedir, edir, 'lib', 'ansible', 'modules', fn)

        #from random import randint
        #from ansible.module_utils.basic import AnsibleModule
        #from ansible.module_utils._text import to_text, to_native
        #from ansible.module_utils.vmware import ...
        cmd = 'fgrep "from ansible.module_utils" %s' % mfn
        (rc, so, se) = _run_command(cmd)
        if rc != 0:
            logger.info('%s rc:%s' % (cmd, rc))
            logger.info(se)
        logger.info(so)
        mutils = so.split('\n')
        mutils = [x.strip() for x in mutils if x.strip()]
        mutils = [x.split()[1] for x in mutils]

        for idx,x in enumerate(mutils):
            try:
                parts = x.split('.')
                mutils[idx] = '.'.join(parts[2:])
            except:
                logger.info('can not split %s' % x)

        collections[dirn]['module_utils'] += mutils
        collections[dirn]['module_utils'] = \
            sorted(set(collections[dirn]['module_utils']))

        if mfn.endswith('.py'):
            docs = []
            indocs = False
            with open(mfn, 'r') as f:
                for line in f.readlines():
                    if line.startswith('DOCUMENTATION'):
                        indocs = True
                    if line.lstrip().startswith("'''") or line.lstrip().startswith('"""'):
                        break
                    if indocs:
                        docs.append(line)

            fragments = None
            try:
                ydocs = yaml.load(''.join(docs[1:]))
                if ydocs is not None and 'extends_documentation_fragment' in ydocs:
                    fragments = \
                        ydocs['extends_documentation_fragment']
            except Exception as e:
                fragment_index = None
                for idx,x in enumerate(docs):
                    if 'extends_documentation_fragment' in x:
                        fragment_index = idx
                        break
                if fragment_index is not None:
                    try:
                        fdoc = yaml.load(''.join(docs[fragment_index:]))
                    except Exception as e:
                        import epdb; epdb.st()
                    fragments = fdoc.get('extends_documentation_fragment')
                    #import epdb; epdb.st()

            if fragments is not None and not isinstance(fragments, list):
                fragments = [fragments]
                #print(fragments)
                #import epdb; epdb.st()

                #if 'ipa.documentation' in fragments:
                #    import epdb; epdb.st()

            if fragments is not None:
                collections[dirn]['docs_fragments'] += fragments
                collections[dirn]['docs_fragments'] = \
                    sorted(set(collections[dirn]['docs_fragments']))

    '''TBD
    # look for action plugins
    cmd = 'cd %s/lib/ansible/plugins/action ; find . -type f' % os.path.join(releasedir, edir)
    (rc, so, se) = _run_command(cmd)
    filens = [x.strip() for x in so.split('\n') if x.strip()]
    filens = [x.replace('./', '', 1) for x in filens]
    for filen in filens:
        import epdb; epdb.st()
    '''

    # store the meta ...
    jf = os.path.join(metadir, 'ansible-' + eversion + '-meta.json')
    with open(jf, 'w') as f:
        f.write(json.dumps(collections, indent=2, sort_keys=True))

    #import epdb; epdb.st()

def assemble_collections(refresh=False, devel_only=False):
    #cachedir = os.path.join(VARDIR, 'collections')
    rpmdir = os.path.join(VARDIR, 'repos', 'rpm')
    releasedir = os.path.join(VARDIR, 'releases')
    colbasedir = os.path.join(VARDIR, 'collections')
    metadir = os.path.join(VARDIR, 'meta')

    tarballs = []
    if not devel_only:
        tarballs += glob.glob('%s/*.tar.gz' % releasedir)
    tarballs += ['devel.git']

    tarballs = sorted(tarballs)

    for tb in tarballs:
        eversion = version_from_tar(tb)
        jf = os.path.join(metadir, 'ansible-' + eversion + '-meta.json')
        with open(jf, 'r') as f:
            collections = json.loads(f.read())

        _assemble_collections(collections, refresh=refresh)


def _assemble_collections(collections, refresh=False):
    rpmdir = os.path.join(VARDIR, 'repos', 'rpm')
    releasedir = os.path.join(VARDIR, 'releases')
    colbasedir = os.path.join(VARDIR, 'collections')
    metadir = os.path.join(VARDIR, 'meta')

    # create the -versioned- collections ...
    for k,v in collections.items():
        if k == '':
            continue
        if not [x for x in v['modules'] if not x.endswith('__init__.py')]:
            continue
        cdir = os.path.join(colbasedir, v['name'], v['version'])
        if refresh and os.path.exists(cdir):
            shutil.rmtree(cdir)
        if not os.path.exists(cdir):
            os.makedirs(cdir)
        apdir = os.path.join(cdir, 'plugins', 'action')
        modir = os.path.join(cdir, 'plugins', 'modules')
        mudir = os.path.join(cdir, 'plugins', 'module_utils')
        dfdir = os.path.join(cdir, 'plugins', 'doc_fragments')
        if not os.path.exists(apdir):
            os.makedirs(apdir)
        if not os.path.exists(modir):
            os.makedirs(modir)
        if not os.path.exists(mudir):
            os.makedirs(mudir)
        if not os.path.exists(dfdir):
            os.makedirs(dfdir)

        for mn in v['modules']:
            src = os.path.join(v['basedir'], 'lib', 'ansible', 'modules', mn)
            dst = os.path.join(modir, os.path.basename(mn))
            shutil.copy(src, dst)

        for mu in v['module_utils']:
            if not mu.strip():
                continue
            if mu in MODULE_UTIL_BLACKLIST:
                continue
            src = os.path.join(
                v['basedir'],
                'lib',
                'ansible',
                'module_utils',
                mu.replace('.', '/') + '.py'
            )
            dst = os.path.join(
                mudir, mu.split('.')[-1] + '.py'
            )
            if os.path.exists(src):
                shutil.copy(src, dst)

        if v.get('docs_fragments') is not None:
            for df in v['docs_fragments']:
                # pre-2.8 these were not plugins
                dfg1 = os.path.join(
                    v['basedir'],
                    'lib',
                    'ansible',
                    'utils',
                    'module_docs_fragments'
                )
                dfg2 = os.path.join(
                    v['basedir'],
                    'lib',
                    'ansible',
                    'plugins',
                    'doc_fragments'
                )

                if os.path.exists(dfg1):
                    src = os.path.join(dfg1, df.split('.')[0] + '.py')
                else:
                    src = os.path.join(dfg2, df.split('.')[0] + '.py')

                dst = os.path.join(dfdir, df.split('.')[0] + '.py')

                if not os.path.exists(src):
                    logger.error('%s DOES NOT EXIST!!!' % src)
                    #import epdb; epdb.st()
                    continue

                shutil.copy(src, dst)
                #import epdb; epdb.st()


def build_rpms(refresh=False, devel_only=False):

    colbasedir = os.path.join(VARDIR, 'collections')
    rpmdir = os.path.join(VARDIR, 'repos', 'rpm')
    releasedir = os.path.join(VARDIR, 'releases')

    #tarballs = glob.glob('%s/*.tar.gz' % releasedir)
    #tarballs = sorted(tarballs)

    tarballs = []
    if not devel_only:
        tarballs += glob.glob('%s/*.tar.gz' % releasedir)
    tarballs += ['devel.git']

    tarballs = sorted(tarballs)

    for tb in tarballs:
        tbbn = os.path.basename(tb)
        edir = tbbn.replace('.tar.gz', '')
        eversion = version_from_tar(tb)
        metadir = os.path.join(VARDIR, 'meta')

        jf = os.path.join(metadir, 'ansible-' + eversion + '-meta.json')
        if not os.path.exists(jf):
            continue

        with open(jf, 'r') as f:
            collections = json.loads(f.read())

        for k,v in collections.items():
            # create the package

            if k == '':
                continue
            if not [x for x in v['modules'] if not x.endswith('__init__.py')]:
                continue

            cdir = os.path.join(colbasedir, v['name'], v['version'])
            #dstrpm = os.path.join(rpmdir, '%s-%s.rpm' % (v['name'], v['version']))
            dstrpm = os.path.join(rpmdir, '%s%s-%s.rpm' % (
                COLLECTION_PACKAGE_PREFIX, v['name'], v['version'])
            )
            dstrpmdir = os.path.dirname(dstrpm)
            if not os.path.exists(dstrpmdir):
                os.makedirs(dstrpmdir)

            if os.path.exists(dstrpm) and refresh:
                os.remove(dstrpm)

            if not os.path.exists(dstrpm):
                #import epdb; epdb.st()
                logger.info('build %s' % dstrpm)
                cmd = [
                    'fpm',
                    '-t',
                    'rpm',
                    '-s',
                    'dir',
                    '-n',
                    COLLECTION_PACKAGE_PREFIX + v['name'],
                    '--version',
                    v['version'],
                    '-C',
                    cdir,
                    '--prefix',
                    os.path.join(COLLECTION_INSTALL_PATH, COLLECTION_NAMESPACE, v['name']),
                    #os.path.join(COLLECTION_INSTALL_PATH, COLLECTION_NAMESPACE),
                    '-p',
                    dstrpm,
                    'plugins'
                    #'modules',
                    #'module_utils',
                    #'module_docs_fragments'
                ]
                cmd = ' '.join(cmd)
                logger.info(cmd)
                (rc, so, se) = _run_command(cmd)
                if rc != 0:
                    logger.info('%s rc: %s' % (cmd, rc))
                    logger.info(so)
                    logger.info(se)
                    sys.exit(rc)
                #if v['name'] == 'system':
                #    import epdb; epdb.st()

    return {}


def build_repodata():
    #repodir = '/var/cache/gravity/repos/rpm'
    repodir = os.path.join(VARDIR, 'repos', 'rpm')
    repodata_dir = os.path.join(repodir, 'repodata')
    if os.path.exists(repodata_dir):
        shutil.rmtree(repodata_dir)
    logger.info('creating repo')
    createrepo('.', _cwd=repodir)


def get_issues_for_file(filename=None):
    url = 'http://ansibullbot.eng.ansible.com/ansibot/metadata/byfile.json'
    logger.info(url)
    rr = requests.get(url)
    rdata = rr.json()
    res = rdata.get(filename, [])
    return res


def build_ansible_rpm():
    releasedir = os.path.join(VARDIR, 'releases')
    repodir = os.path.join(VARDIR, 'repos', 'rpm')
    import epdb; epdb.st()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase',
        help='which phase of the process to run',
        choices=[
            'all',
            'releases',
            'index',
            'assemble',
            'package',
            'package_engine'
        ],
        default='all'
    )
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--devel_only', action='store_true')
    args = parser.parse_args()

    if args.phase in ['all', 'releases']:
        logger.info('get releases')
        get_releases(refresh=args.refresh, devel_only=args.devel_only)
    if args.phase in ['all', 'index']:
        logger.info('indexing collections')
        index_collections(refresh=args.refresh, devel_only=args.devel_only)
    if args.phase in ['all', 'assemble']:
        logger.info('assembling collections')
        assemble_collections(refresh=args.refresh, devel_only=args.devel_only)
    #if args.phase in ['all', 'package_engine']:
    #    logger.info('building ansible minimal package')
    #    build_ansible_rpm()
    if args.phase in ['all', 'package']:
        logger.info('building packages')
        build_rpms(refresh=args.refresh, devel_only=args.devel_only)
    if args.phase in ['all', 'package', 'package_engine']:
        logger.info('build repo meta')
        build_repodata()


if __name__ == "__main__":
    main()
