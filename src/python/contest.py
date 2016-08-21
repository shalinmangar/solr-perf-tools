#!/bin/python

import os
import shutil

import datetime
import sys
import time

import constants
import utils
import bench


def run_test(start, revision, tgz, runLogDir):
    simplePerfFile = '%s/simpleIndexer-%s.perfdata.txt' % (constants.LOG_BASE_DIR, revision)
    simpleBytesIndexed, simpleDocsIndexed, simpleTimeTaken = bench.run_simple_bench(start, tgz, runLogDir,
                                                                                    simplePerfFile)
    return simpleBytesIndexed, simpleDocsIndexed, simpleTimeTaken


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

    revision1 = sys.argv[1 + sys.argv.index('-revision1')]
    revision2 = sys.argv[1 + sys.argv.index('-revision2')]

    utils.info('Contest between %s and %s' % (revision1, revision2))
    solr1 = bench.LuceneSolrCheckout('%s/contest-1' % constants.CHECKOUT_DIR, revision1)
    solr2 = bench.LuceneSolrCheckout('%s/contest-2' % constants.CHECKOUT_DIR, revision2)

    start = datetime.datetime.now()
    timeStamp = '%04d.%02d.%02d.%02d.%02d.%02d' % (
        start.year, start.month, start.day, start.hour, start.minute, start.second)

    runLogDir1 = '%s/%s/contest-%s' % (constants.LOG_BASE_DIR, timeStamp, revision1)
    runLogDir2 = '%s/%s/contest-%s' % (constants.LOG_BASE_DIR, timeStamp, revision2)
    os.makedirs(runLogDir1)
    os.makedirs(runLogDir2)
    solr1.checkout(runLogDir1)
    solr2.checkout(runLogDir2)
    tgz1 = solr1.build(runLogDir1)
    tgz2 = solr2.build(runLogDir2)
    utils.info('Solr tgz file for revision %s created at: %s' % (revision1, tgz1))
    utils.info('Solr tgz file for revision %s created at: %s' % (revision2, tgz2))

    iters = int(sys.argv[1 + sys.argv.index('-iters')])
    results1 = []
    results2 = []
    utils.info('### Running tests on revision %s' % revision1)
    for i in range(0, iters):
        simpleBytesIndexed, simpleDocsIndexed, simpleTimeTaken = run_test(start, revision1, tgz1, runLogDir1)
        results1.append((simpleBytesIndexed, simpleDocsIndexed, simpleTimeTaken))
        utils.info('Attempt #%s - %d %d %.1f' % (str(i), simpleBytesIndexed, simpleDocsIndexed, simpleTimeTaken))
        if os.path.exists(constants.BENCH_DIR):
            shutil.rmtree(constants.BENCH_DIR)
        os.makedirs(constants.BENCH_DIR)
    utils.info('### Running tests on revision %s' % revision2)
    for i in range(0, iters):
        simpleBytesIndexed, simpleDocsIndexed, simpleTimeTaken = run_test(start, revision2, tgz2, runLogDir2)
        results2.append((simpleBytesIndexed, simpleDocsIndexed, simpleTimeTaken))
        utils.info('Attempt #%s - %d %d %.1f' % (str(i), simpleBytesIndexed, simpleDocsIndexed, simpleTimeTaken))
        if os.path.exists(constants.BENCH_DIR):
            shutil.rmtree(constants.BENCH_DIR)
        os.makedirs(constants.BENCH_DIR)

    utils.info('#######################################')
    for x in range(0, iters):
        r1 = results1[x]
        r2 = results2[x]
        utils.info('Attempt %d - %.1f \t %.1f \t %.1f' % (x, r1[2], r2[2], r2[2] - r1[2]))

    totalBenchTime = time.time() - t0
    utils.info('Total bench time: %d seconds' % totalBenchTime)


if __name__ == '__main__':
    main()
