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
from sh import find as shfind


#DEVEL_URL = 'https://github.com/nitzmahone/ansible.git'
DEVEL_URL = 'https://github.com/ansible/ansible.git'
#DEVEL_BRANCH = 'collection_content_load'
DEVEL_BRANCH = 'devel'

#VARDIR = os.environ.get('GRAVITY_VAR_DIR', '/var/cache/gravity')
VARDIR = os.environ.get('GRAVITY_VAR_DIR', '.cache')
#COLLECTION_NAMESPACE = 'builtins'
#COLLECTION_NAMESPACE = 'evicted'
COLLECTION_NAMESPACE = 'jctanner'
#COLLECTION_NAMESPACE = 'ansible'
COLLECTION_PACKAGE_PREFIX = 'ansible-collection-'
COLLECTION_PREFIX = ''
COLLECTION_INSTALL_PATH = '/usr/share/ansible/collections/ansible_collections'
MODULE_UTIL_BLACKLIST = [
    '_text',
    'basic',
    'common.collections',
    'common.dict_transformations',
    'common.network',
    'common.removed',
    'common.text.formatters',
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


def clean_extra_lines(rawtext):
    lines = rawtext.split('\n')

    imports_start = None
    imports_stop = None
    for idx,x in enumerate(lines):
        if imports_start is None:
            if x.startswith('from ') and not 'absolute_import' in x:
                imports_start = idx
                continue

        if not x:
            continue

        if x.startswith('from '):
            continue

        if imports_start and imports_stop is None:
            if x[0].isalnum():
                imports_stop = idx
                break

    empty_lines = [x for x in range(imports_start, imports_stop)]
    empty_lines = [x for x in empty_lines if not lines[x].strip()]

    if not empty_lines:
        return rawtext

    if len(empty_lines) == 1:
        return rawtext

    # keep 2 empty lines between imports and definitions
    if len(empty_lines) == 2 and (empty_lines[-1] - empty_lines[-2] == 1):
        return rawtext

    print(lines[imports_start:imports_stop])

    while empty_lines:
        try:
            print('DELETING: %s' % lines[empty_lines[0]])
        except IndexError as e:
            print(e)
            import epdb; epdb.st()
        del lines[empty_lines[0]]
        del empty_lines[0]
        empty_lines = [x-1 for x in empty_lines]
        if [x for x in empty_lines if x <= 0]:
            break

        if len(empty_lines) <= 2:
            break

        #import epdb; epdb.st()

    rawtext = '\n'.join(lines)
    return rawtext


def _run_command(cmd):
    logger.debug(cmd)
    if not isinstance(cmd, bytes):
        cmd = cmd.encode('utf-8')
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


def get_releases(refresh=False, devel_only=False):

    cachedir = os.path.join(VARDIR, 'releases')
    if not os.path.exists(cachedir):
        os.makedirs(cachedir)

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

    if not devel_only:
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

    return {}


def index_collections(devel_only=False, refresh=False, filters=None, force=False):
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
        _index_collections(tb, releasedir, colbasedir, refresh=refresh, filters=filters)


def _index_collections(tb, releasedir, colbasedir, refresh=False, filters=None):

    metadir = os.path.join(VARDIR, 'meta')
    if not os.path.exists(metadir):
        os.makedirs(metadir)

    istar = True
    if not tb.endswith('tar.gz') or tb.endswith('.git'):
        istar = False

    logger.info('index %s' % tb)
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

    if filters:
        for filen in files[:]:
            include = True
            for filtern in filters:
                if filtern not in filen:
                    include = False
                    break
            if not include:
                files.remove(filen)

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

    # find test(s)
    rdir = os.path.join(releasedir, edir)
    target_dir = os.path.join(rdir, 'test', 'integration', 'targets')
    units_dir = os.path.join(rdir, 'test', 'units')

    for k,v in collections.items():
        units = []
        targets = []
        for module_filepath in v['modules']:
            mname = os.path.basename(module_filepath)
            mname = mname.replace('.py', '')
            mname = mname.replace('.ps1', '')
            mname = mname.replace('.ps2', '')

            mtdir = os.path.join(target_dir, mname)
            if os.path.exists(mtdir):
                targets.append(mname)

            mufile = 'test_' + mname + '.py'
            cmd = 'find %s -type f -name "%s"' % (units_dir, mufile)
            res = run_command(cmd)
            if res['rc'] == 0:
                units.append(res['so'].strip())

        mudir = os.path.join(units_dir, 'modules', k)
        if os.path.exists(mudir):
            thisdir = os.path.join('modules', k)
            units.append(thisdir)

            cmd = 'find %s -type f -name "*.py"' % (mudir)
            res = run_command(cmd)
            unit_files = [x.strip() for x in res['so'].split('\n') if x.strip()]
            for _uf in unit_files:
                with open(_uf, 'r') as f:
                    uflines = f.readlines()
                ufdata = '\n'.join(uflines)

                # need the conftest file for these tests
                # .cache/releases/devel.git/test/units/modules/conftest.py
                if 'patch_ansible_module' in ufdata:
                    units.append('modules/conftest.py')
                    #import epdb; epdb.st()

        if '/' in k:
            fudir = os.path.join(units_dir, 'module_utils', k.split('/')[1])
            funame = os.path.join(units_dir, 'module_utils', 'test_' + k.split('/')[1] + '.py')
        else:
            fudir = os.path.join(units_dir, 'module_utils', k)
            funame = os.path.join(units_dir, 'module_utils', 'test_' + k + '.py')
        if os.path.exists(fudir):
            units.append(fudir.replace(units_dir + '/', ''))
        if os.path.exists(funame):
            units.append(funame.replace(units_dir + '/', ''))

        collections[k]['units'] = sorted(set([x for x in units[:] if x]))
        collections[k]['targets'] = sorted(set([x for x in targets[:] if x]))

        # look for integration target imports
        for target in targets:
            thistarget = os.path.join(target_dir, target)
            cmd = 'find %s -type f -name "*.yml"' % (thistarget)
            res = run_command(cmd)
            yfiles = res['so'].split('\n')
            yfiles = [x.strip() for x in yfiles if x.strip()]

            for yf in yfiles:
                with open(yf, 'r') as f:
                    _ydata = f.read()

                try:
                    ydata = yaml.load(_ydata.replace('!unsafe', ''))
                except Exception as e:
                    logger.error(e)
                    #import epdb; epdb.st()
                    continue

                if not ydata:
                    continue
                for task in ydata:
                    if task is None:
                        continue
                    dependency = None
                    if 'include_role' in task or 'import_role' in task:
                        key = None
                        if 'include_role' in task:
                            key = 'include_role'
                        elif 'import_role' in task:
                            key = 'import_role'

                        if 'name' in task[key]:
                            dependency = task[key]['name']
                        else:
                            logger.error('NO NAME!!!')
                            import epdb; epdb.st()

                    if dependency:
                        if dependency not in collections[k]['targets']:
                            collections[k]['targets'].append(dependency)

    # store the meta ...
    jf = os.path.join(metadir, 'ansible-' + eversion + '-meta.json')
    with open(jf, 'w') as f:
        f.write(json.dumps(collections, indent=2, sort_keys=True))


def assemble_collections(refresh=False, devel_only=False, filters=None):
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

        _assemble_collections(collections, refresh=refresh, filters=filters)


def _assemble_collections(collections, refresh=False, filters=None):
    rpmdir = os.path.join(VARDIR, 'repos', 'rpm')
    releasedir = os.path.join(VARDIR, 'releases')
    colbasedir = os.path.join(VARDIR, 'collections')
    metadir = os.path.join(VARDIR, 'meta')
    
    if refresh and os.path.exists(colbasedir):
        shutil.rmtree(colbasedir)

    # create the collections ...
    assembled = []
    for k,v in collections.items():
        if k == '':
            continue

        #if 'vmware' in k:
        #    import epdb; epdb.st()

        logger.debug('%s %s' % (k, filters))

        if filters:
            include = True
            for x in filters:
                if x not in k:
                    include = False
                    break
            if not include:
                continue

        #if 'vmware' in k:
        #    import epdb; epdb.st()

        if not [x for x in v['modules'] if not x.endswith('__init__.py')]:
            continue

        #cdir = os.path.join(colbasedir, v['name'], v['version'])
        cdir = os.path.join(colbasedir, 'ansible_collections', COLLECTION_NAMESPACE, v['name'])

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
        with open(os.path.join(apdir, '__init__.py'), 'w') as f:
            f.write('')
        if not os.path.exists(modir):
            os.makedirs(modir)
        with open(os.path.join(modir, '__init__.py'), 'w') as f:
            f.write('')
        if not os.path.exists(mudir):
            os.makedirs(mudir)
        with open(os.path.join(mudir, '__init__.py'), 'w') as f:
            f.write('')
        if not os.path.exists(dfdir):
            os.makedirs(dfdir)

        # create the galaxy.yml
        gdata = {
            'namespace': COLLECTION_NAMESPACE,
            'name': v['name'],
            'version': v['version'],
            'authors': None,
            'description': None,
            'license': None,
            'tags': None,
            'dependencies': None,
            'repository': None,
            'documentation': None,
            'homepage': None,
            'issues': None
        }
        with open(os.path.join(cdir, 'galaxy.yml'), 'w') as f:
            f.write(yaml.dump(gdata, default_flow_style=False))

        for mn in v['modules']:
            src = os.path.join(v['basedir'], 'lib', 'ansible', 'modules', mn)
            dst = os.path.join(modir, os.path.basename(mn))
            shutil.copy(src, dst)

            with open(dst, 'r') as f:
                mdata = f.read()
            _mdata = mdata[:]

            # were any lines nullified?
            extralines = False

            # fix the module util paths
            for mu in v['module_utils']:
                if not mu:
                    continue
                if mu in MODULE_UTIL_BLACKLIST:
                    continue

                # ansible.module_utils.vmware
                # ansible_collections.jctanner.cloud_vmware.module_utils.vmware
                si = 'ansible.module_utils.%s' % mu
                #di = 'ansible_collections.%s.%s.module_utils.%s' % (COLLECTION_NAMESPACE, v['name'], mu)
                di = 'ansible_collections.%s.%s.plugins.module_utils.%s' % (COLLECTION_NAMESPACE, v['name'], mu)

                #mdata = mdata.replace(si, di)
                mdlines = mdata.split('\n')
                for idx,x in enumerate(mdlines):
                    #if not x.startswith('from ') or x.endswith('('):
                    if not x.startswith('from '):
                        continue
                    if si in x:
                        newx = x.replace(si, di)
                        if len(newx) < 160 and ('(' not in x) and '\\' not in x:
                            mdlines[idx] = newx
                            continue

                        if '(' in x and ')' not in x:
                            x = ''
                            tonull = []
                            for thisx in range(idx, len(mdlines)):
                                x += mdlines[thisx]
                                tonull.append(thisx)
                                if ')' in mdlines[thisx]:
                                    break

                            if len(tonull) > 1:
                                extralines = True
                            for tn in tonull:
                                mdlines[tn] = ''

                        if '\\' in x:
                            x = ''
                            tonull = []
                            for thisx in range(idx, len(mdlines)):

                                if thisx != idx and mdlines[thisx].startswith('from '):
                                    break

                                print('add %s' % mdlines[thisx])
                                x += mdlines[thisx]
                                tonull.append(thisx)


                                if thisx != idx and (not mdlines[thisx].strip() or mdlines[thisx][0].isalnum()):
                                    break
                                print('add %s' % mdlines[thisx])
                                #x += mdlines[thisx]
                                #tonull.append(thisx)

                            #print(tonull)
                            #import epdb; epdb.st()
                            if len(tonull) > 1:
                                extralines = True
                            for tn in tonull:
                                mdlines[tn] = ''

                            #print(tonull)
                            #import epdb; epdb.st()

                        #if len(newx) < 160:
                        #    mdlines[idx] = newx
                        #    continue

                        # we have to use newlined imports for those that are >160 chars
                        ximports = x[:]

                        #if '(' in x and ')' not in x:
                        #    import epdb; epdb.st()

                        if si in ximports:
                            ximports = ximports.replace(si, '')
                        elif di in ximports:
                            ximports = ximports.replace(di, '')
                        ximports = ximports.replace('from', '')
                        ximports = ximports.replace('import', '')
                        ximports = ximports.replace('\\', '')
                        ximports = ximports.replace('(', '')
                        ximports = ximports.replace(')', '')
                        ximports = ximports.split(',')
                        ximports = [x.strip() for x in ximports if x.strip()]
                        ximports = sorted(set(ximports))

                        newx = 'from %s import (\n' % di
                        for xi in ximports:
                            newx += '    ' + xi + ',\n'
                        newx += ')'
                        #import epdb; epdb.st()
                        mdlines[idx] = newx

                mdata = '\n'.join(mdlines)

            # FIXME: clean too many empty lines
            if extralines:
                mdata = clean_extra_lines(mdata)
                #import epdb; epdb.st()

            #if dst.endswith('vca_fw.py'):
            #    import epdb; epdb.st()

            # fix the docs fragments
            # extends_documentation_fragment: vmware.documentation\n'
            for df in v['docs_fragments']:
                if not df:
                    continue
                if df not in mdata:
                    continue
                ddf = '%s.%s.%s' % (COLLECTION_NAMESPACE, v['name'], df)
                #import epdb; epdb.st()
                mdata = mdata.replace(
                    'extends_documentation_fragment: ' + df,
                    'extends_documentation_fragment: ' + ddf,
                )

            #if dst.endswith('vca_fw.py'):
            #    import epdb; epdb.st()

            if mdata != _mdata:
                logger.info('fixing imports in %s' % dst)
                with open(dst, 'w') as f:
                    f.write(mdata.rstrip() + '\n')

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

        if v.get('units'):

            # need to fix these imports in the unit tests
            module_names = [os.path.basename(x).replace('.py', '') for x in v['modules']]

            dst = os.path.join(cdir, 'test', 'unit')
            if not os.path.exists(dst):
                os.makedirs(dst)
            for uf in v['units']:
                fuf = os.path.join(v['basedir'], 'test', 'units', uf)
                if os.path.isdir(fuf):
                    #import epdb; epdb.st()

                    fns = glob.glob('%s/*' % fuf)
                    for fn in fns:
                        if os.path.isdir(fn):
                            try:
                                shutil.copytree(fn, os.path.join(dst, os.path.basename(fn)))
                            except Exception as e:
                                pass
                        else:
                           shutil.copy(fn, os.path.join(dst, os.path.basename(fn)))

                elif os.path.isfile(fuf):
                    fuf_dst = os.path.join(dst, os.path.basename(fuf))
                    shutil.copy(fuf, fuf_dst)

                cmd = 'find %s -type f -name "*.py"' % (dst)
                res = run_command(cmd)
                unit_files = sorted([x.strip() for x in res['so'].split('\n') if x.strip()])

                for unit_file in unit_files:
                    # fix the module import paths to be relative
                    #   from ansible.modules.cloud.vmware import vmware_guest
                    #   from ...plugins.modules import vmware_guest

                    depth = unit_file.replace(cdir, '')
                    depth = depth.lstrip('/')
                    depth = os.path.dirname(depth)
                    depth = depth.split('/')
                    rel_path = '.'.join(['' for x in range(-1, len(depth))])
                    
                    with open(unit_file, 'r') as f:
                        unit_lines = f.readlines()
                    unit_lines = [x.rstrip() for x in unit_lines]

                    changed = False

                    for module in module_names:
                        for li,line in enumerate(unit_lines):
                            if line.startswith('from ') and line.endswith(module):
                                unit_lines[li] = 'from %s.plugins.modules import %s' % (rel_path, module)
                                changed = True

                    if changed:
                        with open(unit_file, 'w') as f:
                            f.write('\n'.join(unit_lines) + '\n')
                    #import epdb; epdb.st()


        if v.get('targets'):
            dst = os.path.join(cdir, 'test', 'integration', 'targets')
            if not os.path.exists(dst):
                os.makedirs(dst)
            for uf in v['targets']:
                fuf = os.path.join(v['basedir'], 'test', 'integration', 'targets', uf)
                duf = os.path.join(dst, os.path.basename(fuf))
                if not os.path.exists(os.path.join(dst, os.path.basename(fuf))):
                    try:
                        shutil.copytree(fuf, duf)
                    except Exception as e:
                        import epdb; epdb.st()

                # set namespace for all module refs
                cmd = 'find %s -type f -name "*.yml"' % (duf)
                res = run_command(cmd)
                yfiles = res['so'].split('\n')
                yfiles = [x.strip() for x in yfiles if x.strip()]

                for yf in yfiles:

                    with open(yf, 'r') as f:
                        ydata = f.read()
                    _ydata = ydata[:]

                    if os.path.basename(os.path.dirname(yf)) == 'tasks':

                        for module in v['modules']:
                            msrc = os.path.basename(module)
                            msrc = msrc.replace('.py', '')
                            msrc = msrc.replace('.ps1', '')
                            msrc = msrc.replace('.ps2', '')

                            mdst = '%s.%s.%s' % (COLLECTION_NAMESPACE, v['name'], msrc)

                            if msrc not in ydata or mdst in ydata:
                                continue

                            #import epdb; epdb.st()
                            ydata = ydata.replace(msrc+':', mdst+':')

                    # fix import_role calls?
                    #tasks = yaml.load(ydata)
                    #import epdb; epdb.st()

                    if ydata != _ydata:
                        logger.info('fixing module calls in %s' % yf)
                        with open(yf, 'w') as f:
                            f.write(ydata)

        assembled.append(k)

    if not assembled:
        logger.error('no collections assembled')


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
    parser.add_argument('--devel', dest='devel_only', action='store_true')
    parser.add_argument('--filter', nargs='+')
    #parser.add_argument('--force', nargs='+')

    args = parser.parse_args()

    if args.phase in ['all', 'releases', 'index', 'assemble']:
        logger.info('get releases')
        get_releases(refresh=args.refresh, devel_only=args.devel_only)
    if args.phase in ['all', 'index', 'releases', 'assemble']:
        logger.info('indexing collections', 'index', 'releases', 'assemble')
        index_collections(refresh=args.refresh, devel_only=args.devel_only, filters=args.filter)
    if args.phase in ['all', 'assemble']:
        logger.info('assembling collections')
        assemble_collections(refresh=args.refresh, devel_only=args.devel_only, filters=args.filter)
    #if args.phase in ['all', 'package_engine']:
    #    logger.info('building ansible minimal package')
    #    build_ansible_rpm()
    if args.phase in ['all', 'package']:
        logger.info('building packages')
        build_rpms(refresh=args.refresh, devel_only=args.devel_only, filters=args.filter)
    if args.phase in ['all', 'package', 'package_engine']:
        logger.info('build repo meta')
        build_repodata()


if __name__ == "__main__":
    main()
