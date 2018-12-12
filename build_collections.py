#!/usr/bin/env python

import argparse
import json
import logging
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


VARDIR = os.environ.get('GRAVITY_VAR_DIR', '/var/cache/gravity')
COLLECTION_PREFIX = 'ansible_'
COLLECTION_INSTALL_PATH = '/usr/share/ansible/content'
MODULE_UTIL_BLACKLIST = [
    '_text',
    'basic',
    'common.collections',
    'common.dict_transformations',
    'common.removed',
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
            logging.info('fetching %s' % url)
            rr = requests.get(url, allow_redirects=True)
            open(dst, 'wb').write(rr.content)

        # extract the tarball
        edir = tb.replace('.tar.gz', '')
        epath = os.path.join(cachedir, edir)
        if not os.path.exists(epath):
            logging.info('extracing %s' % tb)
            cmd = 'cd %s; tar xzvf %s' % (cachedir, tb)
            p = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            (so, se) = p.communicate()

    return {}


def build_collections():
    #cachedir = os.path.join(VARDIR, 'collections')
    rpmdir = os.path.join(VARDIR, 'repos', 'rpm')
    releasedir = os.path.join(VARDIR, 'releases')
    colbasedir = os.path.join(VARDIR, 'collections')
    tarballs = glob.glob('%s/*.tar.gz' % releasedir)
    tarballs = sorted(tarballs)
    for tb in tarballs:
        logger.info('assemble %s' % tb)
        tbbn = os.path.basename(tb)
        edir = tbbn.replace('.tar.gz', '')
        eversion = edir.replace('ansible-', '')
        #coldir = os.path.join(cachedir, edir)
        metadir = os.path.join(VARDIR, 'meta')

        if '2.7' not in tbbn:
            continue
        if not os.path.exists(metadir):
            os.makedirs(metadir)

        cmd = 'cd %s/lib/ansible/modules ; find . -type d' % os.path.join(releasedir, edir)
        logger.info(cmd)
        (rc, so, se) = _run_command(cmd)
        logging.info('%s rc: %s' % (cmd, rc))
        if rc != 0:
            logging.info(se)
        dirs = [x.strip() for x in so.split('\n')if x.strip()]

        cmd = 'cd %s/lib/ansible/modules ; find . -type f' % os.path.join(releasedir, edir)
        logger.info(cmd)
        (rc, so, se) = _run_command(cmd)
        logging.info('%s rc: %s' % (cmd, rc))
        if rc != 0:
            logging.info(se)
        files = [x.strip() for x in so.split('\n') if x.strip()]

        collections = {}
        for dirn in dirs:
            dirn = dirn.lstrip('./')
            collections[dirn] = {}
            collections[dirn]['basedir'] = os.path.join(releasedir, edir)
            collections[dirn]['name'] = COLLECTION_PREFIX + dirn.replace('/', '_')
            collections[dirn]['version'] = eversion
            collections[dirn]['modules'] = []
            collections[dirn]['module_utils'] = []
            collections[dirn]['docs_fragments'] = []

        for fn in files:
            logger.info(fn)
            fn = fn.lstrip('./')
            dirn = os.path.dirname(fn)
            collections[dirn]['modules'].append(fn)
            mfn = os.path.join(releasedir, edir, 'lib', 'ansible', 'modules', fn)

            #from random import randint
            #from ansible.module_utils.basic import AnsibleModule
            #from ansible.module_utils._text import to_text, to_native
            #from ansible.module_utils.vmware import ...
            cmd = 'fgrep "from ansible.module_utils" %s' % mfn
            (rc, so, se) = _run_command(cmd)
            if rc != 0:
                logging.info('%s rc:%s' % (cmd, rc))
                logging.info(se)
            logging.info(so)
            mutils = so.split('\n')
            mutils = [x.strip() for x in mutils if x.strip()]
            mutils = [x.split()[1] for x in mutils]

            for idx,x in enumerate(mutils):
                try:
                    parts = x.split('.')
                    mutils[idx] = '.'.join(parts[2:])
                except:
                    logging.info('can not split %s' % x)

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
                        if line.startswith("'''") or line.startswith('"""'):
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
                        fdoc = yaml.load(''.join(docs[fragment_index:]))
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

        # store the meta ...
        jf = os.path.join(metadir, 'ansible-' + eversion + '-meta.json')
        with open(jf, 'w') as f:
            f.write(json.dumps(collections, indent=2, sort_keys=True))

        # create the -versioned- collections ...
        for k,v in collections.items():
            if k == '':
                continue
            if not [x for x in v['modules'] if not x.endswith('__init__.py')]:
                continue
            cdir = os.path.join(colbasedir, v['name'], v['version'])
            if not os.path.exists(cdir):
                os.makedirs(cdir)
            modir = os.path.join(cdir, 'modules')
            mudir = os.path.join(cdir, 'module_utils')
            dfdir = os.path.join(cdir, 'module_docs_fragments')
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
                    src = os.path.join(
                        v['basedir'],
                        'lib',
                        'ansible',
                        'utils',
                        'module_docs_fragments',
                        df.split('.')[0] + '.py'
                    )
                    dst = os.path.join(dfdir, df.split('.')[0] + '.py')

                    #if not os.path.exists(src):
                    #    import epdb; epdb.st()

                    shutil.copy(src, dst)
                    #import epdb; epdb.st()

def build_rpms():

    colbasedir = os.path.join(VARDIR, 'collections')
    rpmdir = os.path.join(VARDIR, 'repos', 'rpm')
    releasedir = os.path.join(VARDIR, 'releases')
    tarballs = glob.glob('%s/*.tar.gz' % releasedir)
    tarballs = sorted(tarballs)

    for tb in tarballs:
        tbbn = os.path.basename(tb)
        edir = tbbn.replace('.tar.gz', '')
        eversion = edir.replace('ansible-', '')
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
            dstrpm = os.path.join(rpmdir, '%s-%s.rpm' % (v['name'], v['version']))
            dstrpmdir = os.path.dirname(dstrpm)
            if not os.path.exists(dstrpmdir):
                os.makedirs(dstrpmdir)

            if not os.path.exists(dstrpm):
                logger.info('build %s' % dstrpm)
                cmd = [
                    'fpm',
                    '-t',
                    'rpm',
                    '-s',
                    'dir',
                    '-n',
                    v['name'],
                    '--version',
                    v['version'],
                    '-C',
                    cdir,
                    '--prefix',
                    os.path.join(COLLECTION_INSTALL_PATH, 'ansible', v['name']),
                    '-p',
                    dstrpm,
                    'modules',
                    'module_utils',
                    'module_docs_fragments'
                ]
                cmd = ' '.join(cmd)
                logging.info(cmd)
                (rc, so, se) = _run_command(cmd)
                if rc != 0:
                    logger.info('%s rc: %s' % (cmd, rc))
                    logger.info(so)
                    logger.info(se)
                    sys.exit(rc)

    return {}


def build_repodata():
    repodir = '/var/cache/gravity/repos/rpm'
    repodata_dir = os.path.join(repodir, 'repodata')
    if os.path.exists(repodata_dir):
        shutil.rmtree(repodata_dir)
    logger.info('creating repo')
    createrepo('.', _cwd=repodir)


def get_issues_for_file(filename=None):
    url = 'http://ansibullbot.eng.ansible.com/ansibot/metadata/byfile.json'
    logging.info(url)
    rr = requests.get(url)
    rdata = rr.json()
    res = rdata.get(filename, [])
    return res


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase',
        help='which phase of the process to run',
        choices=[
            'all',
            'releases',
            'assemble',
            'package'
        ],
        default='all'
    )
    args = parser.parse_args()

    if args.phase in ['all', 'releases']:
        logger.info('get releases')
        get_releases()
    if args.phase in ['all', 'assemble']:
        logger.info('assembling collections')
        build_collections()
    if args.phase in ['all', 'package']:
        logger.info('building packages')
        build_rpms()
        logger.info('build repo meta')
        build_repodata()


if __name__ == "__main__":
    main()
