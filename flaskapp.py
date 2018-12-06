#!/usr/bin/env python

__version__ = '1.0.0'

import glob
import json
import os
import tempfile

from pprint import pprint

from flask import Flask
from flask import request
from flask import jsonify
from flask import url_for
from flask import render_template

from celery import Celery
from celery.result import AsyncResult

from tasks import _run_command
from tasks import run_command
from tasks import get_releases
from tasks import build_collections
from tasks import get_issues_for_file

app = Flask(__name__)

VARDIR = os.environ.get('GRAVITY_VAR_DIR')
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND')
CELERY_RESULT_BACKEND += '/'
CELERY_RESULT_BACKEND += os.environ.get('CELERY_MONGODB_BACKEND_DATABASE')
celery = Celery('tasks', broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)


@app.route('/')
def root():
    #return app.send_static_file('index.html')
    return render_template('index.html')


@app.route('/status/<task_id>')
def taskstatus(task_id):
    task = celery.AsyncResult(task_id)
    response = {
    'state': task.state,
        'result': task.result
    }
    return jsonify(response)


@app.route('/testcmd')
def testcmd():
    task = run_command.apply_async((), {'cmd': 'whoami'})
    return jsonify({}), 202, {'Location': url_for('taskstatus', task_id=task.id)}


@app.route('/get_releases')
def get_release_tarballs():
    task = get_releases.apply_async()
    return jsonify({}), 202, {'Location': url_for('taskstatus', task_id=task.id)}


@app.route('/build_collections')
def build_all_collections():
    task = build_collections.apply_async()
    return jsonify({}), 202, {'Location': url_for('taskstatus', task_id=task.id)}


#<a href='/collections'>collections</a>
@app.route('/collections')
def collections():

    collection_meta = {}

    collections_base_dir = os.path.join(VARDIR, 'collections')
    cdirs = glob.glob('%s/*' % collections_base_dir)
    for cdir in cdirs:
        vdirs = glob.glob('%s/*' % cdir)
        versions = [os.path.basename(x) for x in vdirs]
        versions = sorted(versions, reverse=True)
        cname = os.path.basename(cdir)
        cnamespace = 'ansible'
        collection_meta[cnamespace + '/' + cname] = {
            'namespace': cnamespace,
            'name': cname,
            'versions': versions,
            'url': '/collections/%s/%s' % (cnamespace, cname)
        }

    return render_template('collections.html', collections=collection_meta)


@app.route('/collections/<namespace>/<name>/<version>')
def collection_version(namespace, name, version):
    colmeta = {}
    collections_base_dir = os.path.join(VARDIR, 'collections')
    coldir = os.path.join(collections_base_dir, name, version)
    cmd = 'cd %s; find . -type f' % coldir
    (rc, so, se) = _run_command(cmd)
    if rc != 0:
        print(cmd)
        print(rc)
        print(se)
        print(so)
    files = so.split('\n')
    files = [x.strip() for x in files]
    files = [x.lstrip('./') for x in files]
    files = sorted(files)

    colmeta['filepath'] = coldir
    colmeta['namespace'] = namespace
    colmeta['name'] = name
    colmeta['files'] = files[:]
    colmeta['version'] = version

    issues = {}
    '''
    for fn in colmeta['files']:
        repofn = os.path.join('/lib/ansible', fn)
        res = get_issues_for_file(repofn)
        issues[fn] = res[:]
    '''
    pprint(colmeta)

    return render_template('collection_version.html', collection=colmeta, issues=issues)


#<a href='/repoview'>repoview</a>
@app.route('/repoview')
def repoview():
    yum_base_dir = os.path.join(VARDIR, 'repos', 'rpm')
    rpms = glob.glob('%s/*.rpm' % yum_base_dir)
    rpms = [os.path.basename(x) for x in rpms]
    rpms = sorted(rpms)
    return render_template('repoview.html', rpms=rpms)


@app.route('/artifacts')
@app.route('/artifacts/<path:thispath>')
def artifacts(thispath=None):
    base_dir = os.path.join(VARDIR, 'repos')
    if thispath is None:
        thispath = base_dir
        checkdir = base_dir
    else:
        checkdir = thispath.replace('/artifacts/', '')
        checkdir = os.path.join(base_dir, checkdir)
        print(checkdir)

    filenames = {}

    paths = glob.glob('%s/*' % checkdir)
    for gpath in paths:
        bn = os.path.basename(gpath)
        if os.path.isdir(gpath):
            ftype = 'dir'
        else:
            ftype = 'file'
        filenames[bn] = {
            'ftype': ftype,
            'name': bn,
            'fullpath': '/artifacts/' + gpath.replace(base_dir + '/', '')
        }

    return render_template('fileview.html', thispath=thispath, filenames=filenames)



if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=False)
