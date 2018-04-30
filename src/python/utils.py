#!/bin/python

import os
import subprocess

import datetime
import time
import requests


def info(message):
    print('[%s] %s' % (datetime.datetime.now(), message))


def get_solr_version():
    r = requests.get('http://localhost:8983/solr/admin/info/system?wt=json')
    solr = r.json()['lucene']['solr-impl-version'].split(' ')
    return solr[0], solr[1]


def get_num_found(collection):
    r = requests.get('http://localhost:8983/solr/%s/select?q=*:*&rows=0&wt=json' % collection)
    solr = r.json()['response']['numFound']
    return int(solr)


def runCommand(command):
    info('RUN: %s' % command)
    t0 = time.time()
    if os.system(command):
        info('  FAILED')
        raise RuntimeError('command failed: %s' % command)
    info('  took %.1f sec' % (time.time() - t0))


def runComand(name, command, log):
    p = subprocess.Popen(command, shell=False, stdout=subprocess.PIPE, stdin=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    f = open(log, 'wbu')
    while True:
        s = p.stdout.readline()
        if s == '':
            break
        f.write(s)
        f.flush()
    f.close()
    if p.wait() != 0:
        print()
        print('Command %s FAILED:' % name)
        s = open(log, 'r')
        for line in s.readlines():
            print(line.rstrip())
        raise RuntimeError('%s failed; see log %s' % (name, log))
