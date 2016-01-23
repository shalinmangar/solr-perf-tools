#!/bin/python

ANT_EXE = 'ant'
GIT_EXE = 'git'

TEST_BASE_DIR = '/solr-bench'
LOG_BASE_DIR = '%s/logs' % TEST_BASE_DIR

NIGHTLY_REPORTS_DIR = '%s/reports' % TEST_BASE_DIR

SOLR_COLLECTION_NAME = 'gettingstarted'

IMDB_DATA_FILE = '/solr-data/imdb.json'
IMDB_NUM_DOCS = 2436442

WIKI_1K_DATA_FILE = '/solr-data/enwiki-20120502-lines-1k.txt'
WIKI_1K_NUM_DOCS = 33332620
#WIKI_1K_DATA_FILE = '/solr-data/small-enwiki-20120502-lines-1k.txt'
# WIKI_1K_DATA_FILE = '/solr-data/enwiki.random.lines.txt'

WIKI_4K_DATA_FILE = '/solr-data/enwiki-20120502-lines.txt'
WIKI_4k_NUM_DOCS = 6726515
# WIKI_4K_DATA_FILE = '/solr-data/enwiki.random.lines.txt'
# WIKI_4K_DATA_FILE = '/solr-data/small-4k-wiki-lines.txt'

CHECKOUT_DIR = '%s/checkout' % TEST_BASE_DIR
BENCH_DIR = '%s/solr' % TEST_BASE_DIR

JVM_CLIENT_PARAMS = ['-server', '-Xms2g', '-Xmx2g', '-XX:-TieredCompilation', '-XX:+HeapDumpOnOutOfMemoryError', '-Xbatch']
