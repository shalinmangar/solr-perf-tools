#!/bin/python

import glob
import os
import re
import shutil
import traceback

import datetime
import requests
import sys
import time

import constants
import graphutils
import utils

SLACK = '-enable-slack-bot' in sys.argv and 'SLACK_BOT_TOKEN' in os.environ
NOREPORT = '-no-report' in sys.argv

KNOWN_CHANGES = [
    ('2016-01-22 17:43',
     'SOLR-8582: /update/json/docs is 4x slower than /update for indexing a list of json docs',
     """
     SOLR-8582: Fixed memory leak in JsonRecordReader affecting /update/json/docs. Large payloads cause OOM.
     Brings performance on par with /update for large json lists.
     """),
    ('2016-01-23 20:11:11',
     'ConcurrentHttpSolrClient, 8 threads, batchSize=100, queueSize=200, 4g client heap. Fixed minor bug in indexer.',
     """
     Changed indexer to use ConcurrentHttpSolrClient instead of HttpSolrClient. Dropped indexing threads
     from 16 to 8. Client heap size increased to 4g from 2g. Fixed bug in indexer which caused last batch to not be indexed.
     """),
    ('2016-01-23 21:35',
     'ConcurrentHttpSolrClient now uses binary request writer instead of default xml writer',
     """
     ConcurrentHttpSolrClient now uses binary request writer instead of default xml writer. Also we explicitly set
     request writer, response writer and poll time=0 for ConcurrentHttpSolrClient
     """
     ),
    ('2016-01-23 23:20',
     'Client threads increased to 10 from 8',
     """
     Client threads increased to 10 from 8
     """),
    ('2016-01-24 06:05',
     'Client threads decreased from 10 to 9',
     """
     Client threads decreased from 10 to 9
     """),
    ('2016-01-25 05:33',
     'Limit client feeder threads to 1 when using ConcurrentUpdateSolrClient',
     """
     When using ConcurrentUpdateSolrClient we limit the feeder threads that read wiki text from file to just
     1 thread. The SolrJ client continues to use 9 threads to send data to Solr.
     """),
    ('2016-03-16',
     'SOLR-8740: use docValues by default',
     """
     docValues are now enabled by default for most non-text (string, date, and numeric) fields in
     the schema templates
     """),
    ('2016-08-29',
     'SOLR-9449: Example schemas do not index _version_ field anymore because the field has DocValues enabled already',
     """
     SOLR-8740 had enabled doc values for long types by default. Since then, the _version_ field was both indexed
     and had doc values. SOLR-9449 stopped indexing the _version_ field since doc values are already enabled.
     """),
    ('2016-08-31',
     'SOLR-9452: JsonRecordReader should not deep copy document before handler.handle()',
     """
     JsonRecordReader used to make a deep copy of the document map which was only required for very specialized
     methods. This deep copy has been removed to optimize the common case. This change only affects JSON indexing
     and therefore only the IMDB benchmark.
     """),
    ('2018-05-22 01:11:16', 'Lucene/Solr 6.4.2 release', 'Built from tags/releases/lucene-solr/6.4.2'),
    ('2018-05-22 03:01:58', 'Lucene/Solr 6.5.1 release', 'Built from tags/releases/lucene-solr/6.5.1'),
    ('2018-05-22 04:53:12', 'Lucene/Solr 6.6.4 release', 'Built from tags/releases/lucene-solr/6.6.4'),
    ('2018-05-22 07:12:16', 'Lucene/Solr 7.0.1 release',
     """
     Lucene/Solr 7.0.1 release. Switched timesecnum from tint to pint and date field to pdate
     The _default configset is used instead of data_driven_schema_configs
     """),
    ('2018-05-22 08:57:00', 'Lucene/Solr 7.1.0 release', 'Built from tags/releases/lucene-solr/7.1.0'),
    ('2018-05-22 11:40:00', 'Lucene/Solr 7.2.1 release', 'Built from tags/releases/lucene-solr/7.2.1'),
    ('2018-05-22 21:59:30', 'Lucene/Solr 7.3.1 release', 'Built from tags/releases/lucene-solr/7.3.1')
]


class LuceneSolrCheckout:
    def __init__(self, checkoutDir, revision='LATEST'):
        self.checkoutDir = checkoutDir
        self.revision = revision

    def checkout(self, runLogFile):
        utils.info(
            'Attempting to checkout Lucene/Solr revision: %s into directory: %s' % (
                self.revision, self.checkoutDir))
        if not os.path.exists(self.checkoutDir):
            os.makedirs(self.checkoutDir)
        f = os.listdir(self.checkoutDir)
        x = os.getcwd()
        try:
            os.chdir(self.checkoutDir)
            if len(f) == 0:
                # clone
                if self.revision == 'LATEST':
                    utils.runCommand(
                        '%s clone --progress %s . >> %s 2>&1' % (
                            constants.GIT_EXE, constants.GIT_REPO, runLogFile))
                else:
                    utils.runCommand(
                        '%s clone --progress %s .  >> %s 2>&1' % (
                            constants.GIT_EXE, constants.GIT_REPO, runLogFile))
                    self.updateToRevision(runLogFile)
                try:
                    utils.runCommand('rm -r ~/.ant/lib/ivy-*.jar')
                except:
                    print('Unable to remove previous ivy-2.3.0.jar')
                utils.runCommand('%s ivy-bootstrap' % constants.ANT_EXE)
            else:
                self.updateToRevision(runLogFile)
        finally:
            os.chdir(x)

    def updateToRevision(self, runLogFile):
        # resets any staged changes (there shouldn't be any though)
        utils.runCommand('%s reset --hard' % constants.GIT_EXE)
        # clean ANY files not tracked in the repo -- this effectively restores pristine state
        utils.runCommand('%s clean -xfd .' % constants.GIT_EXE)
        if self.revision == 'LATEST':
            utils.runCommand('%s checkout origin/master >> %s 2>&1' % (constants.GIT_EXE, runLogFile))
            utils.runCommand('%s pull origin master >> %s 2>&1' % (constants.GIT_EXE, runLogFile))
        else:
            utils.runCommand('%s checkout origin/master >> %s 2>&1' % (constants.GIT_EXE, runLogFile))
            utils.runCommand('%s checkout %s >> %s 2>&1' % (constants.GIT_EXE, self.revision, runLogFile))

    def build(self, runLogFile):
        x = os.getcwd()
        try:
            os.chdir('%s' % self.checkoutDir)
            utils.runCommand('%s clean clean-jars >> %s 2>&1' % (constants.ANT_EXE, runLogFile))
            os.chdir('%s/solr' % self.checkoutDir)
            utils.runCommand('%s create-package >> %s 2>&1' % (constants.ANT_EXE, runLogFile))
            packaged = os.path.join(os.getcwd(), "package")
            files = glob.glob(os.path.join(packaged, '*.tgz'))
            if len(files) == 0:
                raise RuntimeError('No tgz file found at %s' % packaged)
            elif len(files) > 1:
                raise RuntimeError('More than 1 tgz file found at %s' % packaged)
            else:
                return files[0]
        finally:
            os.chdir(x)

    def get_git_rev(self):
        x = os.getcwd()
        try:
            os.chdir(self.checkoutDir)
            s = utils.run_get_output([constants.GIT_EXE, 'show', '-s', '--format=%H,%ci'])
            sha, date = s.split(',')
            date_parts = date.split(' ')
            return sha, datetime.datetime.strptime('%s %s' % (date_parts[0], date_parts[1]), '%Y-%m-%d %H:%M:%S')
        finally:
            os.chdir(x)


class SolrServer:
    def __init__(self, tgz, extract_dir, name='', host='localhost', port='8983',
                 memory=None,
                 zk_host=None, server_dir=None, solr_home=None,
                 example=None, jvm_args=None, cloud_mode=False):
        self.tgz = tgz
        self.extract_dir = extract_dir
        self.name = name
        self.host = host
        self.port = port
        self.memory = memory
        self.zk_host = zk_host
        self.server_dir = server_dir
        self.solr_home = solr_home
        self.example = example
        self.jvm_args = jvm_args
        # cloud mode is true if a zk host has been specified
        self.cloud_mode = cloud_mode if self.zk_host is None else True

    def extract(self, runLogFile):
        if os.path.exists(self.extract_dir):
            shutil.rmtree(self.extract_dir)
        os.makedirs(self.extract_dir)
        utils.runCommand(
            'tar xvf %s -C %s --strip-components=1 >> %s 2>&1' % (self.tgz, self.extract_dir, runLogFile))

    def start(self, runLogFile):
        x = os.getcwd()
        try:
            os.chdir(self.extract_dir)
            cmd = ['%s/bin/solr' % self.extract_dir, 'start', '-p', self.port]
            if self.jvm_args is not None:
                cmd.extend(self.jvm_args)
            if self.host is not None:
                cmd.extend(['-h', self.host])
            if self.memory is not None:
                cmd.extend(['-m', self.memory])
            if self.cloud_mode:
                cmd.extend(['-c'])
            if self.zk_host is not None:
                cmd.extend(['-z', self.zk_host])
            if self.server_dir is not None:
                cmd.extend(['-d', self.server_dir])
            if self.solr_home is not None:
                cmd.extend(['-s', self.solr_home])
            if self.example is not None:
                cmd.extend(['-e', self.example])
            utils.info('Running solr with command: %s' % ' '.join(cmd))
            utils.runComand('solr server', cmd, '%s' % runLogFile)
        finally:
            os.chdir(x)

    def create_collection(self, runLogFile, collection, num_shards='1', replication_factor='1',
                          config='_default'):
        x = os.getcwd()
        try:
            os.chdir(self.extract_dir)
            cmd = ['%s/bin/solr' % self.extract_dir, 'create_collection', '-p', self.port,
                   '-c', collection, '-shards', num_shards, '-replicationFactor', replication_factor,
                   '-d', config]
            utils.info('Creating collection with command: %s' % ' '.join(cmd))
            utils.runComand('solr create_collection', cmd, '%s' % runLogFile)
        finally:
            os.chdir(x)

    def stop(self):
        utils.runCommand('%s/bin/solr stop -p %s' % (self.extract_dir, self.port))

    def get_version(self):
        r = requests.get('http://%s:%s/solr/admin/info/system?wt=json' % (self.host, self.port))
        solr = r.json()['lucene']['solr-impl-version'].split(' ')
        return solr[0], solr[1]

    def get_num_found(self, collection):
        r = requests.get('http://%s:%s/solr/%s/select?q=*:*&rows=0&wt=json' % (self.host, self.port, collection))
        solr = r.json()['response']['numFound']
        return int(solr)

    def get_jars(self):
        dist = '%s/dist/*.jar' % self.extract_dir
        jars = glob.glob(dist)
        jars.extend(glob.glob('%s/dist/solrj-lib/*.jar' % self.extract_dir))
        return jars

    def get_metrics(self):
        r = requests.get('http://%s:%s/solr/admin/metrics?wt=json&indent=on' % (self.host, self.port))
        return r

    def get_cluster_state(self):
        r = requests.get('http://%s:%s/solr/admin/collections?action=clusterstatuswt=json&indent=on' % (self.host, self.port))
        return r.text


def run_simple_bench(start, tgz, runLogFile, perfFile):
    server = SolrServer(tgz, '%s/simple' % constants.BENCH_DIR, example='schemaless', memory='2g')
    server.extract(runLogFile)
    try:
        server.start(runLogFile)
        time.sleep(10)

        solrMajorVersion, solrImplVersion = server.get_version()
        cmd = ['%s/bin/post' % server.extract_dir, '-c', constants.SOLR_COLLECTION_NAME, constants.IMDB_DATA_FILE]
        logFile = '%s' % runLogFile

        utils.info('Running simple bench. Logging at: %s' % logFile)
        utils.info('Executing: %s' % ' '.join(cmd))

        t0 = time.time()
        utils.runComand('binpost', cmd, logFile)
        t1 = time.time() - t0

        log_metrics(logFile, server, 'simple_bench')

        bytesIndexed = os.stat(constants.IMDB_DATA_FILE).st_size
        docsIndexed = utils.get_num_found(constants.SOLR_COLLECTION_NAME)

        if docsIndexed != constants.IMDB_NUM_DOCS:
            raise RuntimeError(
                'Indexed num_docs do not match expected %d != found %d' % (constants.IMDB_NUM_DOCS, docsIndexed))

        print ('      %.1f s' % (t1))
        if not NOREPORT:
            with open(perfFile, 'a+') as f:
                timeStampLoggable = '%04d-%02d-%02d %02d:%02d:%02d' % (
                    start.year, start.month, start.day, start.hour, start.minute, start.second)
                f.write('%s,%d,%d,%.1f,%s,%s\n' % (
                    timeStampLoggable, bytesIndexed, docsIndexed, t1, solrMajorVersion, solrImplVersion))

        return bytesIndexed, docsIndexed, t1
    finally:
        server.stop()
        time.sleep(10)


class BenchResults:
    reBytesIndexed = re.compile('^Indexer: net bytes indexed (.*)$', re.MULTILINE)
    reIndexingTime = re.compile(r'^Indexer: finished \((.*) msec\)$', re.MULTILINE)

    # Time in JIT compilation: 54284 ms
    reTimeIn = re.compile('^\s*Time in (.*?): (\d+) ms')
    reTimeInLabel = re.compile('^[\\t]*(.*) - Time in (.*?): (\d+) ms')

    # Garbage Generated in Young Generation: 39757.8 MiB
    reGarbageIn = re.compile('^\s*Garbage Generated in (.*?): (.*) MiB$')
    reGarbageInLabel = re.compile('^[\\t]*(.*) - Garbage Generated in (.*?): (.*) MiB$')

    # Peak usage in Young Generation: 341.375 MiB
    rePeakUsage = re.compile('^\s*Peak usage in (.*?): (.*) MiB')
    rePeakUsageLabel = re.compile('^[\\t]*(.*) - Peak usage in (.*?): (.*) MiB')

    def __init__(self, logFile, server, time_taken):
        self.timeTaken = time_taken

        s = open(logFile).read()
        self.bytesIndexed = int(self.reBytesIndexed.search(s).group(1))
        self.indexTimeSec = int(self.reIndexingTime.search(s).group(1)) / 1000.0

        # extract GC times
        self.node_data = {}

        self.times = {}
        self.garbage = {}
        self.peak = {}
        with open(logFile) as f:
            for line in f.readlines():
                m = self.reTimeIn.search(line)
                if m is not None:
                    self.times[m.group(1)] = float(m.group(2)) / 1000.
                else:
                    m = self.reTimeInLabel.search(line)
                    if m is not None:
                        if not self.node_data.has_key(m.group(1)):
                            self.node_data[m.group(1)] = {'times': {}, 'garbage': {}, 'peak': {}}
                        self.node_data[m.group(1)]['times'][m.group(2)] = float(m.group(3)) / 1000.

                m = self.reGarbageIn.search(line)
                if m is not None:
                    self.garbage[m.group(1)] = float(m.group(2))
                else:
                    m = self.reGarbageInLabel.search(line)
                    if m is not None:
                        if not self.node_data.has_key(m.group(1)):
                            self.node_data[m.group(1)] = {'times': {}, 'garbage': {}, 'peak': {}}
                        self.node_data[m.group(1)]['garbage'][m.group(2)] = float(m.group(3))

                m = self.rePeakUsage.search(line)
                if m is not None:
                    self.peak[m.group(1)] = float(m.group(2))
                else:
                    m = self.rePeakUsageLabel.search(line)
                    if m is not None:
                        if not self.node_data.has_key(m.group(1)):
                            self.node_data[m.group(1)] = {'times': {}, 'garbage': {}, 'peak': {}}
                        self.node_data[m.group(1)]['peak'][m.group(2)] = float(m.group(3))

        utils.info('  took %.1f sec by client' % self.indexTimeSec)
        utils.info('  took %.1f sec total' % self.timeTaken)

        self.docsIndexed = server.get_num_found(constants.SOLR_COLLECTION_NAME)

    def __str__(self):
        s = """Documents indexed: %d
Bytes indexed: %.1f
Time taken by client: %.1f sec
Time taken (total): %.1f sec\n""" % (self.docsIndexed, self.bytesIndexed, self.indexTimeSec, self.timeTaken)
        if len(self.node_data) != 0:
            for k in self.node_data:
                s += 'Printing Stats for %s node\n' % k
                times = self.node_data[k]['times']
                garbage = self.node_data[k]['garbage']
                peak = self.node_data[k]['peak']
                s += self.get_stats_strings(times, garbage, peak)
        else:
            s += self.get_stats_strings(self.times, self.garbage, self.peak)
        return s

    def get_stats_strings(self, times, garbage, peak):
        s = ''
        for v in times:
            s += '\tTime in %s: %.1f ms\n' % (v, times[v])
        for v in garbage:
            s += '\tGarbage Generated in %s: %.1f MiB\n' % (v, garbage[v])
        for v in peak:
            s += '\tPeak memory usage in %s: %.1f MiB\n' % (v, peak[v])
        return s

    def get_simple_results(self):
        # bytesIndexed, indexTimeSec, docsIndexed, times, garbage, peak
        return self.bytesIndexed, self.indexTimeSec, self.docsIndexed, self.times, self.garbage, self.peak


class JavaBench:
    def __init__(self, benchDir):
        self.benchDir = benchDir

    def src_dir(self):
        return os.path.join(self.benchDir, "src/java")

    def src_files(self):
        return ['%s/org/apache/solr/perf/%s' % (self.src_dir(), x) for x in (
            'Args.java',
            'IndexThreads.java',
            'LineFileDocs.java',
            'StatisticsHelper.java',
            'WikiIndexer.java'
        )]

    def build_dir(self):
        return os.path.join(self.benchDir, 'build')

    def compile(self, server, runLogFile):
        buildDir = self.build_dir()
        if not os.path.exists(buildDir):
            os.makedirs(buildDir)
        cmd = ['javac', '-d', buildDir, '-classpath', ':'.join(server.get_jars())]
        cmd.extend(self.src_files())
        utils.info('Running: %s' % ' '.join(cmd))
        utils.runComand('javac', cmd, runLogFile)

    def get_run_command(self, server, javaExeClass, cmdArgs):
        cmd = ['java']
        cmd.extend(constants.CLIENT_JVM_PARAMS)
        cmd.append('-cp')
        cmd.append('%s:%s' % (self.build_dir(), ':'.join(server.get_jars())))
        cmd.append(javaExeClass)
        cmd.extend(cmdArgs)
        return cmd

    def run(self, testName, server, javaExeClass, cmdArgs, logFile):
        cmd = self.get_run_command(server, javaExeClass, cmdArgs)
        utils.info('Running %s bench. Logging at %s' % (testName, logFile))
        utils.info('Executing: %s' % ' '.join(cmd))

        tmpLogFile = '/tmp/%s.log' % testName
        if os.path.exists(tmpLogFile):
            os.remove(tmpLogFile)
        t0 = time.time()
        utils.runComand(testName, cmd, tmpLogFile)
        t1 = time.time() - t0

        results = BenchResults(tmpLogFile, server, t1)
        print(results)

        utils.runCommand('cat %s >> %s' % (tmpLogFile, logFile))
        return results


def run_wiki_schemaless_bench(start, tgz, runLogFile, perfFile, gcFile):
    server = SolrServer(tgz, '%s/wiki_schemaless' % constants.BENCH_DIR, example='schemaless', memory='4g')
    server.extract(runLogFile)
    try:
        bench = JavaBench(os.getcwd())
        bench.compile(server, runLogFile)

        server.start(runLogFile)
        time.sleep(10)

        solrMajorVersion, solrImplVersion = server.get_version()

        solrUrl = 'http://%s:%s/solr/gettingstarted' % (server.host, server.port)

        logFile = '%s' % runLogFile

        results = bench.run('wiki-1k-schemaless', server,
                            'org.apache.solr.perf.WikiIndexer',
                            [
                                # '-useHttpSolrClient', '-solrUrl', solrUrl,
                                '-useConcurrentUpdateSolrClient', '-solrUrl', solrUrl,
                                '-lineDocsFile', constants.WIKI_1K_DATA_FILE,
                                '-docCountLimit', '-1',
                                '-threadCount', '9',
                                '-batchSize', '100'], logFile)

        bytesIndexed, indexTimeSec, docsIndexed, times, garbage, peak = results.get_simple_results()

        log_metrics(logFile, server, 'wiki_schemaless_bench')

        if docsIndexed != constants.WIKI_1K_NUM_DOCS:
            raise RuntimeError(
                'Indexed num_docs do not match expected %d != found %d' % (constants.WIKI_1K_NUM_DOCS, docsIndexed))
        timeStampLoggable = '%04d-%02d-%02d %02d:%02d:%02d' % (
            start.year, start.month, start.day, start.hour, start.minute, start.second)
        with open(perfFile, 'a+') as f:
            f.write('%s,%d,%d,%.1f,%s,%s\n' % (
                timeStampLoggable, bytesIndexed, docsIndexed, indexTimeSec, solrMajorVersion, solrImplVersion))
        write_gc_file(gcFile, timeStampLoggable, solrMajorVersion, solrImplVersion, times, garbage, peak)
    finally:
        server.stop()
        time.sleep(10)


def run_wiki_1k_schema_bench(start, tgz, runLogFile, perfFile, gcFile):
    # we start in schemaless mode but use the schema api to add the right fields
    jmx_args = ['-Dcom.sun.management.jmxremote',
                         '-Dcom.sun.management.jmxremote.local.only=true',
                         '-Dcom.sun.management.jmxremote.port=9999',
                         '-Dcom.sun.management.jmxremote.rmi.port=9999',
                         '-Dcom.sun.management.jmxremote.authenticate=false',
                         '-Dcom.sun.management.jmxremote.ssl=false']
    server = SolrServer(tgz, '%s/wiki-1k-schema' % constants.BENCH_DIR, example='schemaless', memory='4g', jvm_args=jmx_args)
    server.extract(runLogFile)
    try:
        bench = JavaBench(os.getcwd())
        bench.compile(server, runLogFile)

        server.start(runLogFile)
        time.sleep(10)

        solrMajorVersion, solrImplVersion = server.get_version()

        solrUrl = 'http://%s:%s/solr/gettingstarted' % (server.host, server.port)

        utils.info('Updating schema')
        schemaApiUrl = '%s/schema' % solrUrl
        r = requests.post(schemaApiUrl,
                          data='{"add-field":{"name":"title","type":"string","stored":false, "indexed":true },'
                               '"add-field":{"name":"titleTokenized","type":"text_en","stored":true, "indexed":true },'
                               '"add-field":{"name":"body","type":"text_en","stored":false, "indexed":true },'
                               '"add-field":{"name":"date","type":"pdate","stored":true, "indexed":true },'
                               '"add-field":{"name":"timesecnum","type":"pint","stored":false, "indexed":true },'
                               '"add-copy-field":{"source":"title","dest":[ "titleTokenized"]}}')
        print(r.json())

        logFile = '%s' % runLogFile

        results = bench.run('wiki-1k-schema', server,
                            'org.apache.solr.perf.WikiIndexer',
                            [
                                # '-useHttpSolrClient', '-solrUrl', solrUrl,
                                '-useConcurrentUpdateSolrClient', '-solrUrl', solrUrl,
                                '-lineDocsFile', constants.WIKI_1K_DATA_FILE,
                                '-docCountLimit', '-1',
                                '-threadCount', '9',
                                '-batchSize', '100'], logFile)

        bytesIndexed, indexTimeSec, docsIndexed, times, garbage, peak = results.get_simple_results()

        log_metrics(logFile, server, 'wiki_1k_schema_bench')

        if docsIndexed != constants.WIKI_1K_NUM_DOCS:
            raise RuntimeError(
                'Indexed num_docs do not match expected %d != found %d' % (constants.WIKI_1K_NUM_DOCS, docsIndexed))
        timeStampLoggable = '%04d-%02d-%02d %02d:%02d:%02d' % (
            start.year, start.month, start.day, start.hour, start.minute, start.second)
        if not NOREPORT:
            with open(perfFile, 'a+') as f:
                f.write('%s,%d,%d,%.1f,%s,%s\n' % (
                    timeStampLoggable, bytesIndexed, docsIndexed, indexTimeSec, solrMajorVersion, solrImplVersion))

            write_gc_file(gcFile, timeStampLoggable, solrMajorVersion, solrImplVersion, times, garbage, peak)
        return bytesIndexed, indexTimeSec, docsIndexed, times, garbage, peak
    except:
        print('Exception %s' % traceback.format_exc())
    finally:
        server.stop()
        time.sleep(10)


def log_metrics(logFile, server, bench_name):
    metrics = server.get_metrics()
    if metrics.status_code == requests.codes.ok:
        with open(logFile, 'a+') as f:
            f.write('--- BEGIN SOLR METRICS AFTER %s ---\n' % bench_name)
            f.write(metrics.text)
            f.write('--- END SOLR METRICS AFTER %s ---\n' % bench_name)


def run_wiki_4k_schema_bench(start, tgz, runLogFile, perfFile, gcFile):
    # we start in schemaless mode but use the schema api to add the right fields
    jmx_args = ['-Dcom.sun.management.jmxremote',
                         '-Dcom.sun.management.jmxremote.local.only=true',
                         '-Dcom.sun.management.jmxremote.port=9999',
                         '-Dcom.sun.management.jmxremote.rmi.port=9999',
                         '-Dcom.sun.management.jmxremote.authenticate=false',
                         '-Dcom.sun.management.jmxremote.ssl=false']
    server = SolrServer(tgz, '%s/wiki-4k-schema' % constants.BENCH_DIR, example='schemaless', memory='4g',
                        jvm_args=jmx_args)
    server.extract(runLogFile)
    try:
        bench = JavaBench(os.getcwd())
        bench.compile(server, runLogFile)

        server.start(runLogFile)
        time.sleep(10)

        solrMajorVersion, solrImplVersion = server.get_version()

        solrUrl = 'http://%s:%s/solr/gettingstarted' % (server.host, server.port)

        utils.info('Updating schema')
        schemaApiUrl = '%s/schema' % solrUrl
        r = requests.post(schemaApiUrl,
                          data='{"add-field":{"name":"title","type":"string","stored":false, "indexed":true },'
                               '"add-field":{"name":"titleTokenized","type":"text_en","stored":true, "indexed":true },'
                               '"add-field":{"name":"body","type":"text_en","stored":false, "indexed":true },'
                               '"add-field":{"name":"date","type":"pdate","stored":true, "indexed":true },'
                               '"add-field":{"name":"timesecnum","type":"pint","stored":false, "indexed":true },'
                               '"add-copy-field":{"source":"title","dest":[ "titleTokenized"]}}')
        print(r.json())

        logFile = '%s' % runLogFile

        results = bench.run('wiki-4k-schema', server,
                            'org.apache.solr.perf.WikiIndexer',
                            [
                                # '-useHttpSolrClient', '-solrUrl', solrUrl,
                                '-useConcurrentUpdateSolrClient', '-solrUrl', solrUrl,
                                '-lineDocsFile', constants.WIKI_4K_DATA_FILE,
                                '-docCountLimit', '-1',
                                '-threadCount', '9',
                                '-batchSize', '100'], logFile)

        bytesIndexed, indexTimeSec, docsIndexed, times, garbage, peak = results.get_simple_results()

        log_metrics(logFile, server, 'wiki_4k_schema_bench')

        if docsIndexed != constants.WIKI_4k_NUM_DOCS:
            raise RuntimeError(
                'Indexed num_docs do not match expected %d != found %d' % (constants.WIKI_4k_NUM_DOCS, docsIndexed))

        timeStampLoggable = '%04d-%02d-%02d %02d:%02d:%02d' % (
            start.year, start.month, start.day, start.hour, start.minute, start.second)
        if not NOREPORT:
            with open(perfFile, 'a+') as f:
                f.write('%s,%d,%d,%.1f,%s,%s\n' % (
                    timeStampLoggable, bytesIndexed, docsIndexed, indexTimeSec, solrMajorVersion, solrImplVersion))
            write_gc_file(gcFile, timeStampLoggable, solrMajorVersion, solrImplVersion, times, garbage, peak)

        return bytesIndexed, indexTimeSec, docsIndexed, times, garbage, peak
    except:
        print('Exception %s' % traceback.format_exc())
    finally:
        server.stop()
        time.sleep(10)


def create_collection_2x1(server, runLogFile):
    utils.info('Creating collection 2x1')
    server.create_collection(runLogFile, 'gettingstarted', num_shards='2', replication_factor='1')


def create_collection_1x2(server, runLogFile):
    utils.info('Creating collection 1x2')
    server.create_collection(runLogFile, 'gettingstarted', num_shards='1', replication_factor='2')


def run_wiki_1k_schema_cloud_bench(start, tgz, runLogFile, perfFile, gcFile, collection_function):
    # we start in schemaless mode but use the schema api to add the right fields
    jmx_args = ['-Dcom.sun.management.jmxremote',
                         '-Dcom.sun.management.jmxremote.local.only=true',
                         '-Dcom.sun.management.jmxremote.port=9999',
                         '-Dcom.sun.management.jmxremote.rmi.port=9999',
                         '-Dcom.sun.management.jmxremote.authenticate=false',
                         '-Dcom.sun.management.jmxremote.ssl=false']
    server = SolrServer(tgz, '%s/wiki-1k-schema_cloud_node1' % constants.BENCH_DIR, name = '1', memory='4g', jvm_args=jmx_args, cloud_mode=True)
    server.extract(runLogFile)
    jmx_args2 = ['-Dcom.sun.management.jmxremote',
                          '-Dcom.sun.management.jmxremote.local.only=true',
                         '-Dcom.sun.management.jmxremote.port=10000',
                         '-Dcom.sun.management.jmxremote.rmi.port=10000',
                         '-Dcom.sun.management.jmxremote.authenticate=false',
                         '-Dcom.sun.management.jmxremote.ssl=false']
    server2 = SolrServer(tgz, '%s/wiki-1k-schema_cloud_node2' % constants.BENCH_DIR_2, name='2', zk_host='localhost:9983', memory='4g', port='8984', jvm_args = jmx_args2, cloud_mode=True)
    server2.extract(runLogFile)
    try:
        bench = JavaBench(os.getcwd())
        bench.compile(server, runLogFile)

        utils.info('Starting server 1 at port 8983')
        server.start(runLogFile)
        time.sleep(10)
        utils.info('Starting server 2 at port 8984')
        server2.start(runLogFile)
        time.sleep(10)

        collection_function(server, runLogFile)

        solrMajorVersion, solrImplVersion = server.get_version()

        solrUrl = 'http://%s:%s/solr/gettingstarted' % (server.host, server.port)

        utils.info('Updating schema')
        schemaApiUrl = '%s/schema' % solrUrl
        r = requests.post(schemaApiUrl,
                          data='{"add-field":{"name":"title","type":"string","stored":false, "indexed":true },'
                               '"add-field":{"name":"titleTokenized","type":"text_en","stored":true, "indexed":true },'
                               '"add-field":{"name":"body","type":"text_en","stored":false, "indexed":true },'
                               '"add-field":{"name":"date","type":"pdate","stored":true, "indexed":true },'
                               '"add-field":{"name":"timesecnum","type":"pint","stored":false, "indexed":true },'
                               '"add-copy-field":{"source":"title","dest":[ "titleTokenized"]}}')
        print(r.json())

        logFile = '%s' % runLogFile

        results = bench.run('wiki-1k-schema_cloud', server,
                            'org.apache.solr.perf.WikiIndexer',
                            [
                                '-useCloudSolrClient',
                                '-zkHost', 'localhost:9983',
                                '-collection', 'gettingstarted',
                                '-lineDocsFile', constants.WIKI_1K_DATA_FILE,
                                '-docCountLimit', '-1',
                                '-threadCount', '9',
                                '-batchSize', '100'], logFile)

        # bytesIndexed, indexTimeSec, docsIndexed, times, garbage, peak = results.get_simple_results()
        bytesIndexed, indexTimeSec, docsIndexed = [results.bytesIndexed, results.indexTimeSec, results.docsIndexed]

        log_metrics(logFile, server, 'wiki_1k_schema_cloud_bench_8983')
        log_metrics(logFile, server2, 'wiki_1k_schema_cloud_bench_8984')

        if docsIndexed != constants.WIKI_1K_NUM_DOCS:
            raise RuntimeError(
                'Indexed num_docs do not match expected %d != found %d' % (constants.WIKI_1K_NUM_DOCS, docsIndexed))

        timeStampLoggable = '%04d-%02d-%02d %02d:%02d:%02d' % (
            start.year, start.month, start.day, start.hour, start.minute, start.second)
        if not NOREPORT:
            with open(perfFile, 'a+') as f:
                f.write('%s,%d,%d,%.1f,%s,%s\n' % (
                    timeStampLoggable, bytesIndexed, docsIndexed, indexTimeSec, solrMajorVersion, solrImplVersion))
            write_gc_file_cloud(gcFile, timeStampLoggable, solrMajorVersion, solrImplVersion, results.node_data)

        return results
    except:
        print('Exception %s' % traceback.format_exc())
    finally:
        try:
            server2.stop()
            time.sleep(10)
        except:
            pass
        server.stop()
        time.sleep(10)


def write_gc_file_cloud(gcFile, timeStampLoggable, solrMajorVersion, solrImplVersion, node_data):
    with open(gcFile, 'a+') as f:
        f.write('%s,%s,%s' % (timeStampLoggable, solrMajorVersion, solrImplVersion))
        for n in sorted(node_data):
            times = node_data[n]['times']
            garbage = node_data[n]['garbage']
            peak = node_data[n]['peak']

            for k in sorted(times):
                f.write(',%f' % times[k])
            for k in sorted(garbage):
                f.write(',%f' % garbage[k])
            for k in sorted(peak):
                f.write(',%f' % peak[k])
        f.write('\n')



def write_gc_file(gcFile, timeStampLoggable, solrMajorVersion, solrImplVersion, times, garbage, peak):
    with open(gcFile, 'a+') as f:
        f.write('%s,%s,%s,' % (timeStampLoggable, solrMajorVersion, solrImplVersion))
        for k in sorted(times):
            f.write('%f,' % times[k])
        for k in sorted(garbage):
            f.write('%f,' % garbage[k])
        c = 0
        for k in sorted(peak):
            f.write('%f' % peak[k])
            c += 1
            if c < len(peak):
                f.write(',')
        f.write('\n')


def main():
    utils.info('Running solr benchmarks with parameter: %s' % sys.argv)
    t0 = time.time()
    if os.path.exists(constants.BENCH_DIR):
        shutil.rmtree(constants.BENCH_DIR)
        os.makedirs(constants.BENCH_DIR)
    if os.path.exists(constants.BENCH_DIR_2):
        shutil.rmtree(constants.BENCH_DIR_2)
        os.makedirs(constants.BENCH_DIR_2)
    if not os.path.exists(constants.NIGHTLY_REPORTS_DIR):
        os.makedirs(constants.NIGHTLY_REPORTS_DIR)

    if '-clean-build' in sys.argv:
        if os.path.exists(constants.CHECKOUT_DIR):
            print('Deleting directory: %s' % constants.CHECKOUT_DIR)
            shutil.rmtree(constants.CHECKOUT_DIR)
        if os.path.exists(constants.ANT_LIB_DIR):
            print('Deleting directory: %s' % constants.ANT_LIB_DIR)
            shutil.rmtree(constants.ANT_LIB_DIR)
        if os.path.exists(constants.IVY_LIB_CACHE):
            print('Deleting directory: %s' % constants.IVY_LIB_CACHE)
            shutil.rmtree(constants.IVY_LIB_CACHE)

    solr = None
    if '-revision' in sys.argv:
        index = sys.argv.index('-revision')
        revision = sys.argv[index + 1]
        solr = LuceneSolrCheckout(constants.CHECKOUT_DIR, revision)
    else:
        solr = LuceneSolrCheckout(constants.CHECKOUT_DIR)
    start = datetime.datetime.now()
    timeStamp = '%04d.%02d.%02d.%02d.%02d.%02d' % (
        start.year, start.month, start.day, start.hour, start.minute, start.second)

    if SLACK:
        try:
            slackUrl = os.environ.get('SLACK_URL')
            slackChannel = os.environ.get('SLACK_CHANNEL')
            slackToken = os.environ.get('SLACK_BOT_TOKEN')
            r = requests.post('%s?token=%s&channel=%s' % (slackUrl, slackToken, slackChannel),
                              'Solr performance test started at %s' % timeStamp)
            print(r)
        except Exception:
            print('Unable to send message to slackbot')

    runLogDir = '%s/%s' % (constants.LOG_BASE_DIR, timeStamp)
    runLogFile = '%s/output.txt' % runLogDir

    if '-logFile' in sys.argv:
        index = sys.argv.index('-logFile')
        runLogFile = sys.argv[index + 1]
    else:
        os.makedirs(runLogDir)

    print('Logging to %s' % runLogFile)
    solr.checkout(runLogFile)
    sha, git_date = solr.get_git_rev()

    if '-log-by-commit-date' in sys.argv:
        start = git_date
        timeStamp = '%04d.%02d.%02d.%02d.%02d.%02d' % (
            git_date.year, git_date.month, git_date.day, git_date.hour, git_date.minute, git_date.second)

    tgz = solr.build(runLogFile)
    utils.info('Solr tgz file created at: %s' % tgz)

    implVersion = ''

    simplePerfFile = '%s/simpleIndexer.perfdata.txt' % constants.LOG_BASE_DIR
    simpleBytesIndexed, simpleDocsIndexed, simpleTimeTaken = run_simple_bench(start, tgz, runLogFile, simplePerfFile)
    simpleIndexChartData = []
    annotations = []
    if os.path.isfile(simplePerfFile):
        with open(simplePerfFile, 'r') as f:
            lines = [line.rstrip('\n') for line in f]
            for l in lines:
                timeStamp, bytesIndexed, docsIndexed, timeTaken, solrMajorVersion, solrImplVersion = l.split(',')
                implVersion = solrImplVersion
                simpleIndexChartData.append(
                    '%s,%.1f' % (timeStamp, (int(bytesIndexed) / (1024 * 1024.)) / float(timeTaken)))
                for date, desc, fullDesc in KNOWN_CHANGES:
                    if timeStamp.startswith(date):
                        print('add annot for simple %s' % desc)
                        annotations.append((date, timeStamp, desc, fullDesc))
                        KNOWN_CHANGES.remove((date, desc, fullDesc))

    simpleIndexChartData.sort()
    simpleIndexChartData.insert(0, 'Date,MB/sec')

    # wiki cannot be indexed into schemaless because of SOLR-8495
    # wikiSchemalessPerfFile = '%s/wiki_schemaless.perfdata.txt' % constants.LOG_BASE_DIR
    # wikiSchemalessGcFile = '%s/wiki_schemaless.gc.txt' % constants.LOG_BASE_DIR
    # run_wiki_schemaless_bench(start, tgz, runLogFile, wikiSchemalessPerfFile, wikiSchemalessGcFile)
    # wikiSchemalessIndexChartData = []
    # with open(wikiSchemalessPerfFile, 'r') as f:
    #     lines = [line.rstrip('\n') for line in f]
    #     for l in lines:
    #         timeStamp, bytesIndexed, docsIndexed, timeTaken, solrMajorVersion, solrImplVersion = l.split(',')
    #         wikiSchemalessIndexChartData.append(
    #                 '%s,%.1f' % (timeStamp, (int(bytesIndexed) / (1024 * 1024 * 1024.)) / (float(timeTaken) / 3600.)))
    #
    # wikiSchemalessIndexChartData.sort()
    # wikiSchemalessIndexChartData.insert(0, 'Date,GB/hour')

    wiki1kSchemaPerfFile = '%s/wiki_1k_schema.perfdata.txt' % constants.LOG_BASE_DIR
    wiki1kSchemaGcFile = '%s/wiki_1k_schema.gc.txt' % constants.LOG_BASE_DIR
    wiki1kBytesIndexed, wiki1kIndexTimeSec, wiki1kDocsIndexed, \
    wiki1kTimes, wiki1kGarbage, wiki1kPeak = run_wiki_1k_schema_bench(start, tgz, runLogFile, wiki1kSchemaPerfFile,
                                                                      wiki1kSchemaGcFile)
    wiki1kSchemaIndexChartData = []
    wiki1kSchemaIndexDocsSecChartData = []
    wiki1kSchemaGcTimesChartData = []
    wiki1kSchemaGcGarbageChartData = []
    wiki1kSchemaGcPeakChartData = []
    populate_gc_data(wiki1kSchemaGcFile, wiki1kSchemaGcGarbageChartData, wiki1kSchemaGcPeakChartData,
                     wiki1kSchemaGcTimesChartData)
    if os.path.isfile(wiki1kSchemaPerfFile):
        with open(wiki1kSchemaPerfFile, 'r') as f:
            lines = [line.rstrip('\n') for line in f]
            for l in lines:
                timeStamp, bytesIndexed, docsIndexed, timeTaken, solrMajorVersion, solrImplVersion = l.split(',')
                implVersion = solrImplVersion
                wiki1kSchemaIndexChartData.append(
                    '%s,%.1f' % (timeStamp, (int(bytesIndexed) / (1024 * 1024 * 1024.)) / (float(timeTaken) / 3600.)))
                wiki1kSchemaIndexDocsSecChartData.append(
                    '%s,%.1f' % (timeStamp, (int(docsIndexed) / 1000) / float(timeTaken)))

    wiki1kSchemaIndexChartData.sort()
    wiki1kSchemaIndexChartData.insert(0, 'Date,GB/hour')

    wiki1kSchemaIndexDocsSecChartData.sort()
    wiki1kSchemaIndexDocsSecChartData.insert(0, 'Date,K docs/sec')

    wiki4kSchemaPerfFile = '%s/wiki_4k_schema.perfdata.txt' % constants.LOG_BASE_DIR
    wiki4kGcFile = '%s/wiki_4k_schema.gc.txt' % constants.LOG_BASE_DIR
    wiki4kBytesIndexed, wiki4kIndexTimeSec, wiki4kDocsIndexed, \
    wiki4kTimes, wiki4kGarbage, wiki4kPeak = run_wiki_4k_schema_bench(start, tgz, runLogFile, wiki4kSchemaPerfFile, wiki4kGcFile)
    wiki4kSchemaIndexChartData = []
    wiki4kSchemaIndexDocsSecChartData = []

    wiki4kSchemaGcTimesChartData = []
    wiki4kSchemaGcGarbageChartData = []
    wiki4kSchemaGcPeakChartData = []
    populate_gc_data(wiki4kGcFile, wiki4kSchemaGcGarbageChartData, wiki4kSchemaGcPeakChartData,
                     wiki4kSchemaGcTimesChartData)

    if os.path.isfile(wiki4kSchemaPerfFile):
        with open(wiki4kSchemaPerfFile, 'r') as f:
            lines = [line.rstrip('\n') for line in f]
            for l in lines:
                timeStamp, bytesIndexed, docsIndexed, timeTaken, solrMajorVersion, solrImplVersion = l.split(',')
                implVersion = solrImplVersion
                wiki4kSchemaIndexChartData.append(
                        '%s,%.1f' % (timeStamp, (int(bytesIndexed) / (1024 * 1024 * 1024.)) / (float(timeTaken) / 3600.)))
                wiki4kSchemaIndexDocsSecChartData.append('%s,%.1f' % (timeStamp, (int(docsIndexed) / 1000) / float(timeTaken)))

    wiki4kSchemaIndexChartData.sort()
    wiki4kSchemaIndexChartData.insert(0, 'Date,GB/hour')

    wiki4kSchemaIndexDocsSecChartData.sort()
    wiki4kSchemaIndexDocsSecChartData.insert(0, 'Date,K docs/sec')

    wiki1kSchemaCloudPerfFile = '%s/wiki_1k_schema_cloud.perfdata.txt' % constants.LOG_BASE_DIR
    wiki1kCloudGcFile = '%s/wiki_1k_schema_cloud.gc.txt' % constants.LOG_BASE_DIR
    results = run_wiki_1k_schema_cloud_bench(start, tgz, runLogFile,
                                                                                           wiki1kSchemaCloudPerfFile,
                                                                                           wiki1kCloudGcFile,
                                                                                           create_collection_2x1)

    wiki1kCloudBytesIndexed, wiki1kCloudIndexTimeSec, wiki1kCloudDocsIndexed = [results.bytesIndexed, results.indexTimeSec, results.docsIndexed]

    wiki1kCloudGcTimesChartData = []
    wiki1kCloudGcGarbageChartData = []
    wiki1kCloudGcPeakChartData = []
    populate_cloud_gc_data(wiki1kCloudGcFile, results.node_data, wiki1kCloudGcTimesChartData, wiki1kCloudGcGarbageChartData, wiki1kCloudGcPeakChartData)

    wiki1kCloudIndexChartData = []
    wiki1kCloudIndexDocsSecChartData = []

    if os.path.isfile(wiki1kSchemaCloudPerfFile):
        with open(wiki1kSchemaCloudPerfFile, 'r') as f:
            lines = [line.rstrip('\n') for line in f]
            for l in lines:
                timeStamp, bytesIndexed, docsIndexed, timeTaken, solrMajorVersion, solrImplVersion = l.split(',')
                implVersion = solrImplVersion
                wiki1kCloudIndexChartData.append(
                    '%s,%.1f' % (timeStamp, (int(bytesIndexed) / (1024 * 1024 * 1024.)) / (float(timeTaken) / 3600.)))
                wiki1kCloudIndexDocsSecChartData.append(
                    '%s,%.1f' % (timeStamp, (int(docsIndexed) / 1000) / float(timeTaken)))

    wiki1kCloudIndexChartData.sort()
    wiki1kCloudIndexChartData.insert(0, 'Date,GB/hour')

    wiki1kCloudIndexDocsSecChartData.sort()
    wiki1kCloudIndexDocsSecChartData.insert(0, 'Date,K docs/sec')

    wiki1kSchemaCloud1x2PerfFile = '%s/wiki_1k_schema_cloud1x2.perfdata.txt' % constants.LOG_BASE_DIR
    wiki1kCloud1x2GcFile = '%s/wiki_1k_schema_cloud1x2.gc.txt' % constants.LOG_BASE_DIR

    results = run_wiki_1k_schema_cloud_bench(start, tgz,
                                                                                                    runLogFile,
                                                                                                    wiki1kSchemaCloud1x2PerfFile,
                                                                                                    wiki1kCloud1x2GcFile,
                                                                                                    create_collection_1x2)

    wiki1kCloud1x2BytesIndexed, wiki1kCloudIndexTimeSec, wiki1kCloudDocsIndexed = [results.bytesIndexed, results.indexTimeSec, results.docsIndexed]

    wiki1kCloud1x2IndexChartData = []
    wiki1kCloud1x2IndexDocsSecChartData = []

    wiki1kCloud1x2GcTimesChartData = []
    wiki1kCloud1x2GcGarbageChartData = []
    wiki1kCloud1x2GcPeakChartData = []
    populate_cloud_gc_data(wiki1kCloud1x2GcFile, results.node_data, wiki1kCloud1x2GcTimesChartData, wiki1kCloud1x2GcGarbageChartData, wiki1kCloud1x2GcPeakChartData)

    if os.path.isfile(wiki1kSchemaCloud1x2PerfFile):
        with open(wiki1kSchemaCloud1x2PerfFile, 'r') as f:
            lines = [line.rstrip('\n') for line in f]
            for l in lines:
                timeStamp, bytesIndexed, docsIndexed, timeTaken, solrMajorVersion, solrImplVersion = l.split(',')
                implVersion = solrImplVersion
                wiki1kCloud1x2IndexChartData.append(
                    '%s,%.1f' % (timeStamp, (int(bytesIndexed) / (1024 * 1024 * 1024.)) / (float(timeTaken) / 3600.)))
                wiki1kCloud1x2IndexDocsSecChartData.append(
                    '%s,%.1f' % (timeStamp, (int(docsIndexed) / 1000) / float(timeTaken)))

    wiki1kCloud1x2IndexChartData.sort()
    wiki1kCloud1x2IndexChartData.insert(0, 'Date,GB/hour')

    wiki1kCloud1x2IndexDocsSecChartData.sort()
    wiki1kCloud1x2IndexDocsSecChartData.insert(0, 'Date,K docs/sec')

    if not NOREPORT:
        graphutils.writeIndexingHTML(annotations,
                                     [simpleIndexChartData,
                                      wiki1kSchemaIndexChartData, wiki1kSchemaIndexDocsSecChartData,
                                      wiki1kSchemaGcTimesChartData, wiki1kSchemaGcGarbageChartData,
                                      wiki1kSchemaGcPeakChartData,

                                      wiki4kSchemaIndexChartData, wiki4kSchemaIndexDocsSecChartData,
                                      wiki4kSchemaGcTimesChartData, wiki4kSchemaGcGarbageChartData,
                                      wiki4kSchemaGcPeakChartData,

                                      wiki1kCloudIndexChartData, wiki1kCloudIndexDocsSecChartData,
                                      wiki1kCloudGcTimesChartData, wiki1kCloudGcGarbageChartData,
                                      wiki1kCloudGcPeakChartData,

                                      wiki1kCloud1x2IndexChartData, wiki1kCloud1x2IndexDocsSecChartData,
                                      wiki1kCloud1x2GcTimesChartData, wiki1kCloud1x2GcGarbageChartData,
                                      wiki1kCloud1x2GcPeakChartData])

    totalBenchTime = time.time() - t0
    utils.info('Total bench time: %d seconds' % totalBenchTime)

    if '-logFile' not in sys.argv and '-log-by-commit-date' in sys.argv:
        # find updated runLogDir
        timeStamp = '%04d.%02d.%02d.%02d.%02d.%02d' % (
            git_date.year, git_date.month, git_date.day, git_date.hour, git_date.minute, git_date.second)
        newRunLogDir = '%s/%s' % (constants.LOG_BASE_DIR, timeStamp)
        print('Moving logs from %s to %s' % (runLogDir, newRunLogDir))
        shutil.move(runLogDir, newRunLogDir)

    if SLACK:
        try:
            slackUrl = os.environ.get('SLACK_URL')
            slackChannel = os.environ.get('SLACK_CHANNEL')
            slackToken = os.environ.get('SLACK_BOT_TOKEN')
            message = 'Solr performance test on git sha %s completed in %d seconds:\n' \
                      '\t Start: %s\n' \
                      '\t simple: %.1f json MB/sec\n' \
                      '\t wiki_1k_schema: %.1f GB/hour %.1f k docs/sec\n' \
                      '\t wiki_1k_schema_cloud: %.1f GB/hour %.1f k docs/sec\n' \
                      '\t See complete report at: %s' \
                      % (implVersion, totalBenchTime, timeStamp,
                         (int(simpleBytesIndexed) / (1024 * 1024.)) / float(simpleTimeTaken),
                         (int(wiki1kBytesIndexed) / (1024 * 1024 * 1024.)) / (float(wiki1kIndexTimeSec) / 3600.),
                         (int(wiki1kDocsIndexed) / 1000) / float(wiki1kIndexTimeSec),
                         (int(wiki1kCloudBytesIndexed) / (1024 * 1024 * 1024.)) / (
                                     float(wiki1kCloudIndexTimeSec) / 3600.),
                         (int(wiki1kCloudDocsIndexed) / 1000) / float(wiki1kCloudIndexTimeSec),
                         os.environ.get('SLACK_REPORT_URL'))

            print('Sending message to slackbot: \n\t\t%s' % message)
            r = requests.post('%s?token=%s&channel=%s' % (slackUrl, slackToken, slackChannel), message)
            print('slackbot request posted:')
            print(r)
        except Exception:
            print('Unable to send request to slackbot')


def populate_gc_data(gcFile, gcGarbageChartData, gcPeakChartData, gcTimesChartData):
    if os.path.isfile(gcFile):
        with open(gcFile, 'r') as f:
            lines = [line.rstrip('\n') for line in f]
            for l in lines:
                timeStamp, solrMajorVersion, solrImplVersion, jitCompilation, oldGenGC, \
                youngGenGc, oldGenGarbage, survivorGenGarbage, youngGenGarbage, \
                oldGenPeak, survivorGenPeak, youngGenPeak = l.split(',')
                s = '%s,%.4f,%.4f,%.4f' % (timeStamp, float(jitCompilation), float(youngGenGc), float(oldGenGC))
                gcTimesChartData.append(s)
                s = '%s,%.4f,%.4f,%.4f' % (
                    timeStamp, float(youngGenGarbage) / 1024., float(survivorGenGarbage) / 1024.,
                    float(oldGenGarbage) / 1024.)
                gcGarbageChartData.append(s)
                s = '%s,%.4f,%.4f,%.4f' % (timeStamp, float(youngGenPeak), float(survivorGenPeak), float(oldGenPeak))
                gcPeakChartData.append(s)
    gcTimesChartData.sort()
    gcTimesChartData.insert(0, 'Date,JIT (sec), Young GC (sec), Old GC (sec)')
    gcGarbageChartData.sort()
    gcGarbageChartData.insert(0, 'Date,Young Garbage (GB),Survivor Garbage (GB),Old Garbage (GB)')
    gcPeakChartData.sort()
    gcPeakChartData.insert(0, 'Date,Young Peak (MB),Survivor Peak (MB),Old Peak (MB)')


def populate_cloud_gc_data(gcFile, node_data, gcTimesChartData, gcGarbageChartData, gcPeakChartData):
    if os.path.isfile(gcFile):
        with open(gcFile, 'r') as f:
            lines = [line.rstrip('\n') for line in f]
            for l in lines:
                x = l.split(',')
                timeStamp, solrMajorVersion, solrImplVersion = x[:3]

                jitCompilation, oldGenGC, \
                youngGenGc, oldGenGarbage, survivorGenGarbage, youngGenGarbage, \
                oldGenPeak, survivorGenPeak, youngGenPeak = x[3:12]

                jitCompilation2, oldGenGC2, \
                youngGenGc2, oldGenGarbage2, survivorGenGarbage2, youngGenGarbage2, \
                oldGenPeak2, survivorGenPeak2, youngGenPeak2 = x[12:]

                s = '%s,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f' % (timeStamp, float(jitCompilation), float(youngGenGc), float(oldGenGC), float(jitCompilation2), float(youngGenGc2), float(oldGenGC2))
                gcTimesChartData.append(s)
                s = '%s,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f' % (
                    timeStamp, float(youngGenGarbage) / 1024., float(survivorGenGarbage) / 1024.,
                    float(oldGenGarbage) / 1024.,
                    float(youngGenGarbage2) / 1024., float(survivorGenGarbage2) / 1024.,
                    float(oldGenGarbage2) / 1024.)
                gcGarbageChartData.append(s)
                s = '%s,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f' % \
                    (timeStamp,
                     float(youngGenPeak), float(survivorGenPeak), float(oldGenPeak),
                     float(youngGenPeak2), float(survivorGenPeak2), float(oldGenPeak2))
                gcPeakChartData.append(s)

    node1 = sorted(node_data)[0]
    node2 = sorted(node_data)[1]

    gcTimesChartData.sort()
    gcTimesChartData.insert(0, 'Date, %s JIT (sec), %s Young GC (sec), %s Old GC (sec), %s JIT (sec), %s Young GC (sec), %s Old GC (sec)' % (node1, node1, node1, node2, node2, node2))
    gcGarbageChartData.sort()
    gcGarbageChartData.insert(0, 'Date, %s Young Garbage (GB), %s Survivor Garbage (GB), %s Old Garbage (GB), %s Young Garbage (GB), %s Survivor Garbage (GB), %s Old Garbage (GB)' % (node1, node1, node1, node2, node2, node2))
    gcPeakChartData.sort()
    gcPeakChartData.insert(0, 'Date, %s Young Peak (MB), %s Survivor Peak (MB), %s Old Peak (MB), %s Young Peak (MB), %s Survivor Peak (MB), %s Old Peak (MB)' % (node1, node1, node1, node2, node2, node2))

if __name__ == '__main__':
    main()
