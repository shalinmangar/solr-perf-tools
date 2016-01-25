#!/bin/python

ANT_EXE = 'ant'
GIT_EXE = 'git'

TEST_BASE_DIR_1 = '/solr-bench'
TEST_BASE_DIR_2 = '/solr-bench2'
DATA_BASE_DIR = '/solr-data'
LOG_BASE_DIR = '%s/logs' % TEST_BASE_DIR_1

NIGHTLY_REPORTS_DIR = '%s/reports' % TEST_BASE_DIR_1

SOLR_COLLECTION_NAME = 'gettingstarted'

IMDB_DATA_FILE = '%s/imdb.json' % DATA_BASE_DIR
IMDB_NUM_DOCS = 2436442

WIKI_1K_DATA_FILE = '%s/enwiki-20120502-lines-1k.txt' % DATA_BASE_DIR
WIKI_1K_NUM_DOCS = 33332620
# WIKI_1K_DATA_FILE = '%s/small-enwiki-20120502-lines-1k.txt' % DATA_BASE_DIR
# WIKI_1K_DATA_FILE = '%s/enwiki.random.lines.txt' % DATA_BASE_DIR

WIKI_4K_DATA_FILE = '%s/enwiki-20120502-lines.txt' % DATA_BASE_DIR
WIKI_4k_NUM_DOCS = 6726515
# WIKI_4K_DATA_FILE = '%s/enwiki.random.lines.txt' % DATA_BASE_DIR
# WIKI_4K_DATA_FILE = '%s/small-4k-wiki-lines.txt' % DATA_BASE_DIR

ZOOKEEPER_TAR_GZ = '%s/zookeeer-3.4.6.tar.gz' % DATA_BASE_DIR

CHECKOUT_DIR = '%s/checkout' % TEST_BASE_DIR_1

BENCH_DIR = '%s/solr' % TEST_BASE_DIR_1
BENCH_DIR_2 = '%s/solr' % TEST_BASE_DIR_2

# These are passed to the client JVM
CLIENT_JVM_PARAMS = ['-server', '-Xms4g', '-Xmx4g', '-XX:-TieredCompilation', '-XX:+HeapDumpOnOutOfMemoryError', '-Xbatch']
