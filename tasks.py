import json
import logging
import glob
import os
import requests
import shutil
import subprocess
import time

from bs4 import BeautifulSoup
from celery import Celery

#CELERY_BROKER_URL: pyamqp://rabbit:5672
#CELERY_RESULT_BACKEND: mongodb://mongo:27017
#CELERY_MONGODB_BACKEND_DATABASE: gravity
#CELERY_MONGODB_BACKEND_COLLECTION: results

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND')
CELERY_RESULT_BACKEND += '/'
CELERY_RESULT_BACKEND += os.environ.get('CELERY_MONGODB_BACKEND_DATABASE')

VARDIR = os.environ.get('GRAVITY_VAR_DIR')
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

celery = Celery('tasks', broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

'''
@celery.task(name='tasks.add')
def add(x: int, y: int) -> int:
    time.sleep(5)
    return x + y
'''

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


@celery.task(name='tasks.run_command')
def run_command(cmd=None):
    '''
    p = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    (so, se) = p.communicate()
    return {
        'rc': p.returncode,
        'so': so.decode('utf-8'),
        'se': se.decode('utf-8')
    }
    '''
    (rc, so, se) = _run_command(cmd)
    return {
        'rc': rc,
        'so': so,
        'se': se
    }


@celery.task(name='tasks.get_releases')
def get_releases():
    baseurl = 'https://releases.ansible.com/ansible/'
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

    cachedir = os.path.join(VARDIR, 'releases')
    if not os.path.exists(cachedir):
        os.makedirs(cachedir)

    for tb in tarballs:
        # fetch the tarball
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


@celery.task(name='build_collections')
def build_collections():
    #cachedir = os.path.join(VARDIR, 'collections')
    rpmdir = os.path.join(VARDIR, 'repos', 'rpm')
    releasedir = os.path.join(VARDIR, 'releases')
    colbasedir = os.path.join(VARDIR, 'collections')
    tarballs = glob.glob('%s/*.tar.gz' % releasedir)
    tarballs = sorted(tarballs)
    for tb in tarballs:
        tbbn = os.path.basename(tb)
        edir = tbbn.replace('.tar.gz', '')
        eversion = edir.replace('ansible-', '')
        #coldir = os.path.join(cachedir, edir)
        metadir = os.path.join(VARDIR, 'meta')

        if '2.7' not in tbbn:
            continue
        #if tbbn[8] != '2' and tbbn[10] not in ['4', '5', '6', '7']:
        #    logging.info(tbbn[8])
        #    logging.info(tbbn[10])
        #    logging.info('skipping %s' % tbbn)
        #    continue

        #if not os.path.exists(coldir):
        #    os.makedirs(coldir)
        if not os.path.exists(metadir):
            os.makedirs(metadir)

        cmd = 'cd %s/lib/ansible/modules ; find . -type d' % os.path.join(releasedir, edir)
        (rc, so, se) = _run_command(cmd)
        logging.info('%s rc: %s' % (cmd, rc))
        if rc != 0:
            logging.info(se)
        dirs = [x.strip() for x in so.split('\n')if x.strip()]

        cmd = 'cd %s/lib/ansible/modules ; find . -type f' % os.path.join(releasedir, edir)
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

        for fn in files:
            fn = fn.lstrip('./')
            dirn = os.path.dirname(fn)
            collections[dirn]['modules'].append(fn)
            mfn = os.path.join(releasedir, edir, 'lib', 'ansible', 'modules', fn)

            #from random import randint
            #from ansible.module_utils.basic import AnsibleModule
            #from ansible.module_utils._text import to_text, to_native
            #from ansible.module_utils.vmware import ...
            cmd = 'fgrep "from ansible.module_utils" %s' % mfn
            #logging.info(cmd)
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
            if not os.path.exists(modir):
                os.makedirs(modir)
            if not os.path.exists(mudir):
                os.makedirs(mudir)

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

            # create the package
            dstrpm = os.path.join(rpmdir, '%s-%s.rpm' % (v['name'], v['version']))
            dstrpmdir = os.path.dirname(dstrpm)
            if not os.path.exists(dstrpmdir):
                os.makedirs(dstrpmdir)
            if not os.path.exists(dstrpm):
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
                    'module_utils'
                ]
                cmd = ' '.join(cmd)
                logging.info(cmd)
                (rc, so, se) = _run_command(cmd)
                if rc != 0:
                    logging.info('%s rc: %s' % (cmd, rc))
                    logging.info(so)
                    logging.info(se)

    return {}


@celery.task(name='tasks.get_issues_for_file')
def get_issues_for_file(filename=None):
    url = 'http://ansibullbot.eng.ansible.com/ansibot/metadata/byfile.json'
    logging.info(url)
    rr = requests.get(url)
    rdata = rr.json()
    res = rdata.get(filename, [])
    return res

