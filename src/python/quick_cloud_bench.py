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
import utils

class Input:
    def __init__(self, file, expectedDocs):
        self.file = file
        self.expectedDocs = expectedDocs

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

    # Average System Load: 4.0068359375
    reAvgSysLoad = re.compile('^\s*Average System Load: (.*)')
    reAvgSysLoadLabel = re.compile('^[\\t]*(.*) - Average System Load: (.*)')

    # Average CPU Time: 6.1978397/400
    reAvgCpuTime = re.compile('^\s*Average CPU Time: (.*)')
    reAvgCpuTimeLabel = re.compile('^[\\t]*(.*) - Average CPU Time: (.*)')

    # Average CPU Load: 1.1392051484117345
    reAvgCpuLoad = re.compile('^\s*Average CPU Load: (.*)')
    reAvgCpuLoadLabel = re.compile('^[\\t]*(.*) - Average CPU Load: (.*)')

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
                if line.startswith('Consistency'):
                    utils.info(line)
                m = self.reTimeIn.search(line)
                if m is not None:
                    self.times[m.group(1)] = float(m.group(2)) / 1000.
                else:
                    m = self.reTimeInLabel.search(line)
                    if m is not None:
                        self.init_node_data(m.group(1))
                        self.node_data[m.group(1)]['times'][m.group(2)] = float(m.group(3)) / 1000.

                m = self.reGarbageIn.search(line)
                if m is not None:
                    self.garbage[m.group(1)] = float(m.group(2))
                else:
                    m = self.reGarbageInLabel.search(line)
                    if m is not None:
                        self.init_node_data(m.group(1))
                        self.node_data[m.group(1)]['garbage'][m.group(2)] = float(m.group(3))

                m = self.rePeakUsage.search(line)
                if m is not None:
                    self.peak[m.group(1)] = float(m.group(2))
                else:
                    m = self.rePeakUsageLabel.search(line)
                    if m is not None:
                        self.init_node_data(m.group(1))
                        self.node_data[m.group(1)]['peak'][m.group(2)] = float(m.group(3))

                m = self.reAvgSysLoad.search(line)
                if m is not None:
                    self.avg_sys_load = m.group(1)
                else:
                    m = self.reAvgSysLoadLabel.search(line)
                    if m is not None:
                        self.init_node_data(m.group(1))
                        self.node_data[m.group(1)]['avg_sys_load'] = m.group(2)

                m = self.reAvgCpuTime.search(line)
                if m is not None:
                    self.avg_cpu_time = m.group(1)
                else:
                    m = self.reAvgCpuTimeLabel.search(line)
                    if m is not None:
                        self.init_node_data(m.group(1))
                        self.node_data[m.group(1)]['avg_cpu_time'] = m.group(2)

                m = self.reAvgCpuLoad.search(line)
                if m is not None:
                    self.avg_cpu_load = m.group(1)
                else:
                    m = self.reAvgCpuLoadLabel.search(line)
                    if m is not None:
                        self.init_node_data(m.group(1))
                        self.node_data[m.group(1)]['avg_cpu_load'] = m.group(2)

        utils.info('  took %.1f sec by client' % self.indexTimeSec)
        utils.info('  took %.1f sec total' % self.timeTaken)

        self.docsIndexed = server.get_num_found(constants.SOLR_COLLECTION_NAME)

    def init_node_data(self, node):
        if not self.node_data.has_key(node):
            self.node_data[node] = {'times': {}, 'garbage': {}, 'peak': {}}

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
                s += '\tAverage System Load: %s\n' %(self.node_data[k]['avg_sys_load'])
                s += '\tAverage CPU Time: %s\n' %(self.node_data[k]['avg_cpu_time'])
                s += '\tAverage CPU Load: %s\n' %(self.node_data[k]['avg_cpu_load'])
        else:
            s += self.get_stats_strings(self.times, self.garbage, self.peak)
            s += '\tAverage System Load: %s\n' % self.avg_sys_load
            s += '\tAverage CPU Time: %s\n' % self.avg_cpu_time
            s += '\tAverage CPU Load: %s\n' % self.avg_cpu_load
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

def create_collection_2x1(server, runLogFile):
    utils.info('Creating collection 2x1')
    server.create_collection(runLogFile, 'gettingstarted', num_shards='2', replication_factor='1')


def create_collection_1x2(server, runLogFile):
    utils.info('Creating collection 1x2')
    server.create_collection(runLogFile, 'gettingstarted', num_shards='1', replication_factor='2')


def run_wiki_1k_schema_cloud_bench(start, tgz, runLogFile, collection_function, node1_dir, node2_dir, input_file):
    # we start in schemaless mode but use the schema api to add the right fields
    jmx_args = ['-Dcom.sun.management.jmxremote',
                '-Dcom.sun.management.jmxremote.local.only=true',
                '-Dcom.sun.management.jmxremote.port=9999',
                '-Dcom.sun.management.jmxremote.rmi.port=9999',
                '-Dcom.sun.management.jmxremote.authenticate=false',
                '-Dcom.sun.management.jmxremote.ssl=false']
    server = SolrServer(tgz, node1_dir, name = '1', memory='4g', jvm_args=jmx_args, cloud_mode=True)
    server.extract(runLogFile)
    jmx_args2 = ['-Dcom.sun.management.jmxremote',
                 '-Dcom.sun.management.jmxremote.local.only=true',
                 '-Dcom.sun.management.jmxremote.port=10000',
                 '-Dcom.sun.management.jmxremote.rmi.port=10000',
                 '-Dcom.sun.management.jmxremote.authenticate=false',
                 '-Dcom.sun.management.jmxremote.ssl=false']
    server2 = SolrServer(tgz, node2_dir, name='2', zk_host='localhost:9983', memory='4g', port='8984', jvm_args = jmx_args2, cloud_mode=True)
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
                                '-lineDocsFile', input_file,
                                '-docCountLimit', '-1',
                                '-threadCount', '9',
                                '-batchSize', '100'], logFile)

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

def get_parameter(param, explain):
    if param in sys.argv:
        index = sys.argv.index(param)
        return sys.argv[index+1]
    raise RuntimeError(explain)

def main():
    utils.info('Running solr benchmarks with parameter: %s' % sys.argv)
    t0 = time.time()
    node1_dir = get_parameter("-node1", "Expected a directory for running solr node1")
    node2_dir = get_parameter("-node2", "Expected a directory for running solr node2")
    input_file = get_parameter("-input", "Expected a wiki lines file as input")

    # if '-clean-build' in sys.argv:
    #     if os.path.exists(constants.CHECKOUT_DIR):
    #         print('Deleting directory: %s' % constants.CHECKOUT_DIR)
    #         shutil.rmtree(constants.CHECKOUT_DIR)
    #     if os.path.exists(constants.ANT_LIB_DIR):
    #         print('Deleting directory: %s' % constants.ANT_LIB_DIR)
    #         shutil.rmtree(constants.ANT_LIB_DIR)
    #     if os.path.exists(constants.IVY_LIB_CACHE):
    #         print('Deleting directory: %s' % constants.IVY_LIB_CACHE)
    #         shutil.rmtree(constants.IVY_LIB_CACHE)
    #
    # if '-revision' in sys.argv:
    #     index = sys.argv.index('-revision')
    #     revision = sys.argv[index + 1]
    #     solr = LuceneSolrCheckout(constants.CHECKOUT_DIR, revision)
    # else:
    #     solr = LuceneSolrCheckout(constants.CHECKOUT_DIR)

    start = datetime.datetime.now()
    runLogFile = get_parameter("-logFile", "Expected a file for write out log\ni.e:/home/datcm/log.out")
    print('Logging to %s' % runLogFile)
    tgz = get_parameter("-tgz", "Expected a solr tgz build file\ni.e:/home/datcm/solr-http2.tgz")

    # if '-tgz' in sys.argv:
    #     index = sys.argv.index('-logFile')
    #     tgz = sys.argv[index+1]
    # else:
    #     solr.checkout(runLogFile)
    #     tgz = solr.build(runLogFile)
    #     utils.info('Solr tgz file created at: %s' % tgz)

    run_wiki_1k_schema_cloud_bench(start,
                                   tgz,
                                   runLogFile,
                                   create_collection_1x2,
                                   node1_dir,
                                   node2_dir,
                                   input_file)

    totalBenchTime = time.time() - t0
    utils.info('Total bench time: %d seconds' % totalBenchTime)

if __name__ == '__main__':
    main()
