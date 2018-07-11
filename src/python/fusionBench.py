#!/bin/python

import os
import sys
import bench
import requests
import datetime
start = datetime.datetime.now()

timeStamp = '%04d.%02d.%02d.%02d.%02d.%02d' % (
    start.year, start.month, start.day, start.hour, start.minute, start.second)

bench.run_fusion_bench(start, '/home/shalin/programs/fusion-4.1.0-beta4.tar.gz', '/home/shalin/fusion-test.log', '/home/shalin/fusion-bench.txt')