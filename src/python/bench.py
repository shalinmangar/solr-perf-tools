#!/bin/python

import glob
import os
import re
import shutil

import datetime
import requests
import sys
import time

import constants
import graphutils
import utils

reBytesIndexed = re.compile('^Indexer: net bytes indexed (.*)$', re.MULTILINE)
reIndexingTime = re.compile(r'^Indexer: finished \((.*) msec\)$', re.MULTILINE)

# Time in JIT compilation: 54284 ms
reTimeIn = re.compile('^\s*Time in (.*?): (\d+) ms')

# Garbage Generated in Young Generation: 39757.8 MiB
reGarbageIn = re.compile('^\s*Garbage Generated in (.*?): (.*) MiB$')

# Peak usage in Young Generation: 341.375 MiB
rePeakUsage = re.compile('^\s*Peak usage in (.*?): (.*) MiB')

SLACK = '-enable-slack-bot' in sys.argv and 'SLACK_BOT_TOKEN' in os.environ

KNOWN_CHANGES = [
    ('2016-01-22 17:43',
     'SOLR-8582: /update/json/docs is 4x slower than /update for indexing a list of json docs',
     """
     Fixed memory leak in JsonRecordReader affecting /update/json/docs. Large payloads cause OOM.
     Brings performance on par with /update for large json lists.
     """)
]


class LuceneSolrCheckout:
    def __init__(self, checkoutDir, revision='LATEST'):
        self.checkoutDir = checkoutDir
        self.revision = revision

    def checkout(self, runLogDir):
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
                            '%s clone --progress http://git-wip-us.apache.org/repos/asf/lucene-solr.git . > %s/checkout.log.txt 2>&1' % (
                                constants.GIT_EXE, runLogDir))
                else:
                    utils.runCommand(
                            '%s clone --progress http://git-wip-us.apache.org/repos/asf/lucene-solr.git .  > %s/checkout.log.txt 2>&1' % (
                                constants.GIT_EXE, runLogDir))
                    self.updateToRevision(runLogDir)
                utils.runCommand('%s ivy-bootstrap' % constants.ANT_EXE)
            else:
                self.updateToRevision(runLogDir)
        finally:
            os.chdir(x)

    def updateToRevision(self, runLogDir):
        utils.runCommand('%s reset --hard' % constants.GIT_EXE)
        if self.revision == 'LATEST':
            utils.runCommand('%s pull > %s/update.log.txt 2>&1' % (constants.GIT_EXE, runLogDir))
        else:
            utils.runCommand('%s checkout %s > %s/update.log.txt 2>&1' % (constants.GIT_EXE, self.revision, runLogDir))

    def build(self, runLogDir):
        x = os.getcwd()
        try:
            os.chdir('%s' % self.checkoutDir)
            utils.runCommand('%s clean clean-jars > %s/clean.log.txt 2>&1' % (constants.ANT_EXE, runLogDir))
            os.chdir('%s/solr' % self.checkoutDir)
            utils.runCommand('%s create-package > %s/create-package.log.txt 2>&1' % (constants.ANT_EXE, runLogDir))
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


class SolrServer:
    def __init__(self, tgz, extract_dir, host='localhost', port='8983',
                 memory=None,
                 zk_host=None, server_dir=None, solr_home=None,
                 example=None, jvm_args=None):
        self.tgz = tgz
        self.extract_dir = extract_dir
        self.host = host
        self.port = port
        self.memory = memory
        self.zk_host = zk_host
        self.server_dir = server_dir
        self.solr_home = solr_home
        self.example = example
        self.jvm_args = jvm_args

    def extract(self, runLogDir):
        if os.path.exists(self.extract_dir):
            shutil.rmtree(self.extract_dir)
        os.makedirs(self.extract_dir)
        utils.runCommand(
            'tar xvf %s -C %s --strip-components=1 > %s/extract.log.txt 2>&1' % (self.tgz, self.extract_dir, runLogDir))

    def start(self, runLogDir):
        x = os.getcwd()
        try:
            os.chdir(self.extract_dir)
            cmd = ['%s/bin/solr' % self.extract_dir, 'start', '-p', self.port]
            if self.host is not None:
                cmd.extend(['-h', self.host])
            if self.memory is not None:
                cmd.extend(['-m', self.memory])
            if self.zk_host is not None:
                cmd.extend(['-c', '-z', self.zk_host])
            if self.server_dir is not None:
                cmd.extend(['-d', self.server_dir])
            if self.solr_home is not None:
                cmd.extend(['-s', self.solr_home])
            if self.example is not None:
                cmd.extend(['-e', self.example])
            if self.jvm_args is not None:
                cmd.append(self.jvm_args)
            utils.info('Running solr with command: %s' % ' '.join(cmd))
            utils.runComand('solr server', cmd, '%s/server.log.txt' % runLogDir)
        finally:
            os.chdir(x)

    def stop(self):
        utils.runCommand('%s/bin/solr stop' % self.extract_dir)

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


def run_simple_bench(start, tgz, runLogDir, perfFile):
    server = SolrServer(tgz, '%s/simple' % constants.BENCH_DIR, example='schemaless', memory='2g')
    server.extract(runLogDir)
    try:
        server.start(runLogDir)
        time.sleep(5)

        solrMajorVersion, solrImplVersion = server.get_version()
        cmd = ['%s/bin/post' % server.extract_dir, '-c', constants.SOLR_COLLECTION_NAME, constants.IMDB_DATA_FILE]
        logFile = '%s/simpleIndexer.log.txt' % runLogDir

        utils.info('Running simple bench. Logging at: %s' % logFile)
        utils.info('Executing: %s' % ' '.join(cmd))

        t0 = time.time()
        utils.runComand('binpost', cmd, logFile)
        t1 = time.time() - t0

        bytesIndexed = os.stat(constants.IMDB_DATA_FILE).st_size
        docsIndexed = utils.get_num_found(constants.SOLR_COLLECTION_NAME)

        if docsIndexed != constants.IMDB_NUM_DOCS:
            raise RuntimeError(
                    'Indexed num_docs do not match expected %d != found %d' % (constants.IMDB_NUM_DOCS, docsIndexed))

        print '      %.1f s' % (t1)
        with open(perfFile, 'a+') as f:
            timeStampLoggable = '%04d-%02d-%02d %02d:%02d:%02d' % (
                start.year, start.month, start.day, start.hour, start.minute, start.second)
            f.write('%s,%d,%d,%.1f,%s,%s\n' % (
                timeStampLoggable, bytesIndexed, docsIndexed, t1, solrMajorVersion, solrImplVersion))

        return bytesIndexed, docsIndexed, t1
    finally:
        server.stop()
        time.sleep(5)


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

    def compile(self, server, runLogDir):
        buildDir = self.build_dir()
        if not os.path.exists(buildDir):
            os.makedirs(buildDir)
        cmd = ['javac', '-d', buildDir, '-classpath', ':'.join(server.get_jars())]
        cmd.extend(self.src_files())
        utils.info('Running: %s' % ' '.join(cmd))
        utils.runComand('javac', cmd, os.path.join(runLogDir, 'java-bench-compile.log.txt'))

    def get_run_command(self, server, javaExeClass, cmdArgs):
        cmd = ['java']
        cmd.extend(constants.JVM_CLIENT_PARAMS)
        cmd.append('-cp')
        cmd.append('%s:%s' % (self.build_dir(), ':'.join(server.get_jars())))
        cmd.append(javaExeClass)
        cmd.extend(cmdArgs)
        return cmd

    def run(self, testName, server, javaExeClass, cmdArgs, logFile):
        cmd = self.get_run_command(server, javaExeClass, cmdArgs)
        utils.info('Running %s bench. Logging at %s' % (testName, logFile))
        utils.info('Executing: %s' % ' '.join(cmd))

        t0 = time.time()
        utils.runComand(testName, cmd, logFile)
        t1 = time.time() - t0

        s = open(logFile).read()
        bytesIndexed = int(reBytesIndexed.search(s).group(1))
        indexTimeSec = int(reIndexingTime.search(s).group(1)) / 1000.0

        # extract GC times
        times = {}
        garbage = {}
        peak = {}
        with open(logFile) as f:
            for line in f.readlines():
                m = reTimeIn.search(line)
                if m is not None:
                    times[m.group(1)] = float(m.group(2)) / 1000.
                m = reGarbageIn.search(line)
                if m is not None:
                    garbage[m.group(1)] = float(m.group(2))
                m = rePeakUsage.search(line)
                if m is not None:
                    peak[m.group(1)] = float(m.group(2))

        utils.info('  took %.1f sec by client' % indexTimeSec)
        utils.info('  took %.1f sec total' % t1)

        docsIndexed = server.get_num_found(constants.SOLR_COLLECTION_NAME)
        return bytesIndexed, indexTimeSec, docsIndexed, times, garbage, peak


def run_wiki_schemaless_bench(start, tgz, runLogDir, perfFile, gcFile):
    server = SolrServer(tgz, '%s/wiki_schemaless' % constants.BENCH_DIR, example='schemaless', memory='4g')
    server.extract(runLogDir)
    try:
        bench = JavaBench(os.getcwd())
        bench.compile(server, runLogDir)

        server.start(runLogDir)
        time.sleep(5)

        solrMajorVersion, solrImplVersion = server.get_version()

        solrUrl = 'http://%s:%s/solr/gettingstarted' % (server.host, server.port)

        logFile = '%s/wiki_schemaless.log.txt' % runLogDir

        bytesIndexed, indexTimeSec, docsIndexed, times, garbage, peak = bench.run('wiki-1k-schemaless', server,
                                                            'org.apache.solr.perf.WikiIndexer',
                                                            ['-useHttpSolrClient', '-solrUrl', solrUrl,
                                                             # '-useConcurrentUpdateSolrClient', '-solrUrl', solrUrl,
                                                             '-lineDocsFile', constants.WIKI_1K_DATA_FILE,
                                                             '-docCountLimit', '-1',
                                                             '-threadCount', '16',
                                                             '-batchSize', '100',
                                                             '-printDPS'], logFile)

        # if docsIndexed != constants.IMDB_NUM_DOCS:
        #     raise RuntimeError(
        #             'Indexed num_docs do not match expected %d != found %d' % (constants.IMDB_NUM_DOCS, docsIndexed))
        timeStampLoggable = '%04d-%02d-%02d %02d:%02d:%02d' % (
            start.year, start.month, start.day, start.hour, start.minute, start.second)
        with open(perfFile, 'a+') as f:
            f.write('%s,%d,%d,%.1f,%s,%s\n' % (
                timeStampLoggable, bytesIndexed, docsIndexed, indexTimeSec, solrMajorVersion, solrImplVersion))
        write_gc_file(gcFile, timeStampLoggable, solrMajorVersion, solrImplVersion, times, garbage, peak)
    finally:
        server.stop()
        time.sleep(5)


def run_wiki_1k_schema_bench(start, tgz, runLogDir, perfFile, gcFile):
    # we start in schemaless mode but use the schema api to add the right fields
    jmx_args = ' '.join(['-Dcom.sun.management.jmxremote',
                         '-Dcom.sun.management.jmxremote.port=9999',
                         '-Dcom.sun.management.jmxremote.authenticate=false',
                         '-Dcom.sun.management.jmxremote.ssl=false'])
    server = SolrServer(tgz, '%s/wiki-1k-schema' % constants.BENCH_DIR, example='schemaless', memory='4g', jvm_args=jmx_args)
    server.extract(runLogDir)
    try:
        bench = JavaBench(os.getcwd())
        bench.compile(server, runLogDir)

        server.start(runLogDir)
        time.sleep(5)

        solrMajorVersion, solrImplVersion = server.get_version()

        solrUrl = 'http://%s:%s/solr/gettingstarted' % (server.host, server.port)

        utils.info('Updating schema')
        schemaApiUrl = '%s/schema' % solrUrl
        r = requests.post(schemaApiUrl,
                          data='{"add-field":{"name":"title","type":"string","stored":false, "indexed":true },'
                               '"add-field":{"name":"titleTokenized","type":"text_en","stored":true, "indexed":true },'
                               '"add-field":{"name":"body","type":"text_en","stored":false, "indexed":true },'
                               '"add-field":{"name":"date","type":"date","stored":true, "indexed":true },'
                               '"add-field":{"name":"timesecnum","type":"tint","stored":false, "indexed":true },'
                               '"add-copy-field":{"source":"title","dest":[ "titleTokenized"]},'
                               '"delete-copy-field":{ "source":"*", "dest":"_text_"}}')
        print r.json()

        logFile = '%s/wiki-1k-schema.log.txt' % runLogDir

        bytesIndexed, indexTimeSec, docsIndexed, times, garbage, peak = bench.run('wiki-1k-schema', server,
                                                            'org.apache.solr.perf.WikiIndexer',
                                                            [
                                                                '-useHttpSolrClient', '-solrUrl', solrUrl,
                                                                # '-useConcurrentUpdateSolrClient', '-solrUrl', solrUrl,
                                                                '-lineDocsFile', constants.WIKI_1K_DATA_FILE,
                                                                '-docCountLimit', '-1',
                                                                '-threadCount', '16',
                                                                '-batchSize', '100',
                                                                '-printDPS'], logFile)

        # if docsIndexed != constants.IMDB_NUM_DOCS:
        #     raise RuntimeError(
        #             'Indexed num_docs do not match expected %d != found %d' % (constants.IMDB_NUM_DOCS, docsIndexed))
        timeStampLoggable = '%04d-%02d-%02d %02d:%02d:%02d' % (
            start.year, start.month, start.day, start.hour, start.minute, start.second)
        with open(perfFile, 'a+') as f:
            f.write('%s,%d,%d,%.1f,%s,%s\n' % (
                timeStampLoggable, bytesIndexed, docsIndexed, indexTimeSec, solrMajorVersion, solrImplVersion))

        write_gc_file(gcFile, timeStampLoggable, solrMajorVersion, solrImplVersion, times, garbage, peak)
        return bytesIndexed, indexTimeSec, docsIndexed, times, garbage, peak
    finally:
        server.stop()
        time.sleep(5)

def run_wiki_4k_schema_bench(start, tgz, runLogDir, perfFile, gcFile):
    # we start in schemaless mode but use the schema api to add the right fields
    jmx_args = ' '.join(['-Dcom.sun.management.jmxremote',
                '-Dcom.sun.management.jmxremote.port=9999',
                '-Dcom.sun.management.jmxremote.authenticate=false',
                '-Dcom.sun.management.jmxremote.ssl=false'])
    server = SolrServer(tgz, '%s/wiki-4k-schema' % constants.BENCH_DIR, example='schemaless', memory='4g', jvm_args=jmx_args)
    server.extract(runLogDir)
    try:
        bench = JavaBench(os.getcwd())
        bench.compile(server, runLogDir)

        server.start(runLogDir)
        time.sleep(5)

        solrMajorVersion, solrImplVersion = server.get_version()

        solrUrl = 'http://%s:%s/solr/gettingstarted' % (server.host, server.port)

        utils.info('Updating schema')
        schemaApiUrl = '%s/schema' % solrUrl
        r = requests.post(schemaApiUrl,
                          data='{"add-field":{"name":"title","type":"string","stored":false, "indexed":true },'
                               '"add-field":{"name":"titleTokenized","type":"text_en","stored":true, "indexed":true },'
                               '"add-field":{"name":"body","type":"text_en","stored":false, "indexed":true },'
                               '"add-field":{"name":"date","type":"date","stored":true, "indexed":true },'
                               '"add-field":{"name":"timesecnum","type":"tint","stored":false, "indexed":true },'
                               '"add-copy-field":{"source":"title","dest":[ "titleTokenized"]},'
                               '"delete-copy-field":{ "source":"*", "dest":"_text_"}}')
        print r.json()

        logFile = '%s/wiki-4k-schema.log.txt' % runLogDir

        bytesIndexed, indexTimeSec, docsIndexed, times, garbage, peak = bench.run('wiki-4k-schema', server,
                                                            'org.apache.solr.perf.WikiIndexer',
                                                            [
                                                                '-useHttpSolrClient', '-solrUrl', solrUrl,
                                                                # '-useConcurrentUpdateSolrClient', '-solrUrl', solrUrl,
                                                                '-lineDocsFile', constants.WIKI_4K_DATA_FILE,
                                                                '-docCountLimit', '-1',
                                                                '-threadCount', '16',
                                                                '-batchSize', '100',
                                                                '-printDPS'], logFile)

        # if docsIndexed != constants.IMDB_NUM_DOCS:
        #     raise RuntimeError(
        #             'Indexed num_docs do not match expected %d != found %d' % (constants.IMDB_NUM_DOCS, docsIndexed))

        timeStampLoggable = '%04d-%02d-%02d %02d:%02d:%02d' % (
            start.year, start.month, start.day, start.hour, start.minute, start.second)
        with open(perfFile, 'a+') as f:
            f.write('%s,%d,%d,%.1f,%s,%s\n' % (
                timeStampLoggable, bytesIndexed, docsIndexed, indexTimeSec, solrMajorVersion, solrImplVersion))

        write_gc_file(gcFile, timeStampLoggable, solrMajorVersion, solrImplVersion, times, garbage, peak)

        return bytesIndexed, indexTimeSec, docsIndexed, times, garbage, peak
    finally:
        server.stop()
        time.sleep(5)


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
    t0 = time.time()
    if os.path.exists(constants.BENCH_DIR):
        shutil.rmtree(constants.BENCH_DIR)
        os.makedirs(constants.BENCH_DIR)
    if not os.path.exists(constants.NIGHTLY_REPORTS_DIR):
        os.makedirs(constants.NIGHTLY_REPORTS_DIR)
    solr = LuceneSolrCheckout(constants.CHECKOUT_DIR)
    start = datetime.datetime.now()
    timeStamp = '%04d.%02d.%02d.%02d.%02d.%02d' % (
        start.year, start.month, start.day, start.hour, start.minute, start.second)

    if SLACK:
        slackUrl = os.environ.get('SLACK_URL')
        slackChannel = os.environ.get('SLACK_CHANNEL')
        slackToken = os.environ.get('SLACK_BOT_TOKEN')
        r = requests.post('%s?token=%s&channel=%s' % (slackUrl, slackToken, slackChannel), 'Solr performance test started at %s' % timeStamp)
        print r

    runLogDir = '%s/%s' % (constants.LOG_BASE_DIR, timeStamp)
    os.makedirs(runLogDir)
    solr.checkout(runLogDir)
    tgz = solr.build(runLogDir)
    utils.info('Solr tgz file created at: %s' % tgz)

    implVersion = ''

    simplePerfFile = '%s/simpleIndexer.perfdata.txt' % constants.LOG_BASE_DIR
    simpleBytesIndexed, simpleDocsIndexed, simpleTimeTaken = run_simple_bench(start, tgz, runLogDir, simplePerfFile)
    simpleIndexChartData = []
    annotations = []
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
    # run_wiki_schemaless_bench(start, tgz, runLogDir, wikiSchemalessPerfFile, wikiSchemalessGcFile)
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
    wiki1kTimes, wiki1kGarbage, wiki1kPeak = run_wiki_1k_schema_bench(start, tgz, runLogDir, wiki1kSchemaPerfFile, wiki1kSchemaGcFile)
    wiki1kSchemaIndexChartData = []
    wiki1kSchemaIndexDocsSecChartData = []
    wiki1kSchemaGcTimesChartData = []
    wiki1kSchemaGcGarbageChartData = []
    wiki1kSchemaGcPeakChartData = []
    populate_gc_data(wiki1kSchemaGcFile, wiki1kSchemaGcGarbageChartData, wiki1kSchemaGcPeakChartData,
                     wiki1kSchemaGcTimesChartData)
    with open(wiki1kSchemaPerfFile, 'r') as f:
        lines = [line.rstrip('\n') for line in f]
        for l in lines:
            timeStamp, bytesIndexed, docsIndexed, timeTaken, solrMajorVersion, solrImplVersion = l.split(',')
            implVersion = solrImplVersion
            wiki1kSchemaIndexChartData.append(
                    '%s,%.1f' % (timeStamp, (int(bytesIndexed) / (1024 * 1024 * 1024.)) / (float(timeTaken) / 3600.)))
            wiki1kSchemaIndexDocsSecChartData.append('%s,%.1f' % (timeStamp, (int(docsIndexed) / 1000) / float(timeTaken)))

    wiki1kSchemaIndexChartData.sort()
    wiki1kSchemaIndexChartData.insert(0, 'Date,GB/hour')

    wiki1kSchemaIndexDocsSecChartData.sort()
    wiki1kSchemaIndexDocsSecChartData.insert(0, 'Date,K docs/sec')

    wiki4kSchemaPerfFile = '%s/wiki_4k_schema.perfdata.txt' % constants.LOG_BASE_DIR
    wiki4kGcFile = '%s/wiki_4k_schema.gc.txt' % constants.LOG_BASE_DIR
    wiki4kBytesIndexed, wiki4kIndexTimeSec, wiki4kDocsIndexed, \
    wiki4kTimes, wiki4kGarbage, wiki4kPeak = run_wiki_4k_schema_bench(start, tgz, runLogDir, wiki4kSchemaPerfFile, wiki4kGcFile)
    wiki4kSchemaIndexChartData = []
    wiki4kSchemaIndexDocsSecChartData = []

    wiki4kSchemaGcTimesChartData = []
    wiki4kSchemaGcGarbageChartData = []
    wiki4kSchemaGcPeakChartData = []
    populate_gc_data(wiki4kGcFile, wiki4kSchemaGcGarbageChartData, wiki4kSchemaGcPeakChartData,
                     wiki4kSchemaGcTimesChartData)

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

    graphutils.writeIndexingHTML(annotations,
                                 simpleIndexChartData,
                                 wiki1kSchemaIndexChartData, wiki1kSchemaIndexDocsSecChartData,
                                 wiki1kSchemaGcTimesChartData, wiki1kSchemaGcGarbageChartData,
                                 wiki1kSchemaGcPeakChartData,
                                 wiki4kSchemaIndexChartData, wiki4kSchemaIndexDocsSecChartData,
                                 wiki4kSchemaGcTimesChartData, wiki4kSchemaGcGarbageChartData,
                                 wiki4kSchemaGcPeakChartData)

    totalBenchTime = time.time() - t0
    print 'Total bench time: %d seconds' % totalBenchTime
    if SLACK:
        slackUrl = os.environ.get('SLACK_URL')
        slackChannel = os.environ.get('SLACK_CHANNEL')
        slackToken = os.environ.get('SLACK_BOT_TOKEN')
        message = 'Solr performance test on r%s completed in %d seconds:\n' \
                  '\t Start: %s\n' \
                  '\t simple: %.1f json MB/sec\n' \
                  '\t wiki_1k_schema: %.1f GB/hour %.1f k docs/sec\n' \
                  '\t wiki_4k_schema: %.1f GB/hour %.1f k docs/sec' \
                  % (implVersion, totalBenchTime, timeStamp,
                                    (int(simpleBytesIndexed) / (1024 * 1024.)) / float(simpleTimeTaken),
                     (int(wiki1kBytesIndexed) / (1024 * 1024 * 1024.)) / (float(wiki1kIndexTimeSec) / 3600.),
                     (int(wiki1kDocsIndexed) / 1000) / float(wiki1kIndexTimeSec),
                     (int(wiki4kBytesIndexed) / (1024 * 1024 * 1024.)) / (float(wiki4kIndexTimeSec) / 3600.),
                     (int(wiki4kDocsIndexed) / 1000) / float(wiki4kIndexTimeSec))
        r = requests.post('%s?token=%s&channel=%s' % (slackUrl, slackToken, slackChannel), message)
        print 'slackbot request posted:'
        print r


def populate_gc_data(gcFile, gcGarbageChartData, gcPeakChartData, gcTimesChartData):
    with open(gcFile, 'r') as f:
        lines = [line.rstrip('\n') for line in f]
        for l in lines:
            timeStamp, solrMajorVersion, solrImplVersion, jitCompilation, oldGenGC, \
            youngGenGc, oldGenGarbage, survivorGenGarbage, youngGenGarbage, \
            oldGenPeak, survivorGenPeak, youngGenPeak = l.split(',')
            s = '%s,%.4f,%.4f,%.4f' % (timeStamp, float(jitCompilation), float(youngGenGc), float(oldGenGC))
            gcTimesChartData.append(s)
            s = '%s,%.4f,%.4f,%.4f' % (
            timeStamp, float(youngGenGarbage), float(survivorGenGarbage), float(oldGenGarbage))
            gcGarbageChartData.append(s)
            s = '%s,%.4f,%.4f,%.4f' % (timeStamp, float(youngGenPeak), float(survivorGenPeak), float(oldGenPeak))
            gcPeakChartData.append(s)
    gcTimesChartData.sort()
    gcTimesChartData.insert(0, 'Date,JIT (sec), Young GC (sec), Old GC (sec)')
    gcGarbageChartData.sort()
    gcGarbageChartData.insert(0, 'Date,Young Garbage (MiB),Survivor Garbage (MiB),Old Garbage (MiB)')
    gcPeakChartData.sort()
    gcPeakChartData.insert(0, 'Date,Young Peak (MiB),Survivor Peak (MiB),Old Peak (MiB)')


if __name__ == '__main__':
    main()
