#!/bin/python

import os
import sys
import bench
import requests
import datetime
import constants
import graphutils

KNOWN_CHANGES = []

NOREPORT = '-no-report' in sys.argv
ONLYREPORT = '-only-report' in sys.argv

def run_simple(start, tgz, runLogFile, perfFile):
    simpleBytesIndexed, simpleDocsIndexed, simpleTimeTaken = bench.run_fusion_bench(start, tgz, runLogFile, perfFile)
    return simpleBytesIndexed, simpleDocsIndexed, simpleTimeTaken

def generate_report(simplePerfFile):
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
    if not NOREPORT:
        graphutils.writeFusionIndexingHTML(annotations,
                                           [simpleIndexChartData])

def main():
    start = datetime.datetime.now()
    timeStamp = '%04d.%02d.%02d.%02d.%02d.%02d' % (
        start.year, start.month, start.day, start.hour, start.minute, start.second)

    tgz = '/home/shalin/programs/fusion-4.1.0-beta4.tar.gz'
    simplePerfFile = '%s/fusionSimpleIndexer.perfdata.txt' % constants.LOG_BASE_DIR

    runLogDir = '%s/%s' % (constants.LOG_BASE_DIR, timeStamp)
    runLogFile = '%s/output.txt' % runLogDir

    if ONLYREPORT:
        generate_report(simplePerfFile)
        return

    simpleBytesIndexed, simpleDocsIndexed, simpleTimeTaken = run_simple(start, tgz, runLogFile, simplePerfFile)

    if not NOREPORT:
        generate_report(simplePerfFile)


if __name__ == '__main__':
    main()