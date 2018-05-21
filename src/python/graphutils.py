#!/bin/python

import datetime
import constants

onClickJS = '''
  function zp(num,count) {
    var ret = num + '';
    while(ret.length < count) {
      ret = "0" + ret;
    }
    return ret;
  }

  function doClick(ev, msec, pts) {
    d = new Date(msec);
    top.location = "../logs/" + d.getFullYear() + "." + zp(1+d.getMonth(), 2) + "." + zp(d.getDate(), 2) + "." + zp(d.getHours(), 2) + "." + zp(d.getMinutes(), 2) + "." + zp(d.getSeconds(), 2) + "/output.txt";
  }
'''

def getLabel(label):
    if label < 26:
        s = chr(65 + label)
    else:
        s = '%s%s' % (chr(65 + (label / 26 - 1)), chr(65 + (label % 26)))
    return s


def getOneGraphHTML(annotations, id, data, yLabel, title, errorBars=True):
    l = []
    w = l.append
    series = data[0].split(',')[1]
    w('<div id="%s" style="width:800px;height:400px"></div>' % id)
    w('<script type="text/javascript">')
    w(onClickJS)
    w('  g_%s = new Dygraph(' % id)
    w('    document.getElementById("%s"),' % id)
    for s in data[:-1]:
        w('    "%s\\n" +' % s)
    w('    "%s\\n",' % data[-1])
    options = []
    options.append('title: "%s"' % title)
    options.append('xlabel: "Date"')
    options.append('ylabel: "%s"' % yLabel)
    options.append('labelsKMB: true')
    options.append('labelsSeparateLines: true')
    options.append('labelsDivWidth: 700')
    options.append('clickCallback: doClick')
    options.append("labelsDivStyles: {'background-color': 'transparent'}")
    if False:
        if errorBars:
            maxY = max([float(x.split(',')[1]) + float(x.split(',')[2]) for x in data[1:]])
        else:
            maxY = max([float(x.split(',')[1]) for x in data[1:]])
        options.append('valueRange:[0,%.3f]' % (maxY * 1.25))
    # options.append('includeZero: true')

    if errorBars:
        options.append('errorBars: true')
        options.append('sigma: 1')

    options.append('showRoller: true')

    w('    {%s}' % ', '.join(options))

    if 0:
        if errorBars:
            w('    {errorBars: true, valueRange:[0,%.3f], sigma:1, title:"%s", ylabel:"%s", xlabel:"Date"}' % (
                maxY * 1.25, title, yLabel))
        else:
            w('    {valueRange:[0,%.3f], title:"%s", ylabel:"%s", xlabel:"Date"}' % (maxY * 1.25, title, yLabel))
    w('  );')
    w('  g_%s.setAnnotations([' % id)
    label = 0
    for date, timestamp, desc, fullDesc in annotations:
        if 'JIT/GC' not in title or 'Garbage created' not in title or 'Peak memory' not in title or label >= 33:
            w('    {')
            w('      series: "%s",' % series)
            w('      x: "%s",' % timestamp)
            w('      shortText: "%s",' % getLabel(label))
            w('      width: 20,')
            w('      text: "%s",' % desc)
            w('    },')
        label += 1
    w('  ]);')
    w('</script>')

    if 0:
        f = open('%s/%s.txt' % (constants.NIGHTLY_REPORTS_DIR, id), 'wb')
        for s in data:
            f.write('%s\n' % s)
        f.close()
    return '\n'.join(l)


def htmlEscape(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def header(w, title):
    w('<html>')
    w('<head>')
    w('<title>%s</title>' % htmlEscape(title))
    w('<style type="text/css">')
    w('BODY { font-family:verdana; }')
    w('</style>')
    w('<script src="https://cdnjs.cloudflare.com/ajax/libs/dygraph/2.1.0/dygraph.min.js"></script>\n')
    w('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/dygraph/2.1.0/dygraph.min.css" />\n')
    w('</head>')
    w('<body>')


def footer(w):
    w('<br>')
    # w('Solr options:')
    # w('<ul>')
    # w('<li>IMDB dataset: <code>bin/solr -e schemaless -m 4g</code></li>')
    # w('<li>Wiki 1KB dataset: <code>bin/solr -e schemaless -m 4g</code></li>')
    # w('<li>Wiki 4KB dataset: <code>bin/solr -e schemaless -m 4g</code></li>')
    # w('</ul>')
    w(
        '<br><em>[last updated: %s; send questions to <a href="mailto:shalin@apache.org">Shalin Shekhar Mangar</a>]</em>' % datetime.datetime.now())
    w('</body>')
    w('</html>')


def writeKnownChanges(annotations, w):
    w('<br>')
    w('<b>Known changes:</b>')
    w('<ul>')
    label = 0
    for date, timestamp, desc, fullDesc in annotations:
        w('<li><p><b>%s</b> (%s): %s</p>' % (getLabel(label), date, fullDesc))
        label += 1
    w('</ul>')


def writeIndexingHTML(annotations, chart_data):
    simpleIndexChartData, \
    wiki1kSchemaIndexChartData, wiki1kSchemaIndexDocsSecChartData, \
    wiki1kSchemaGcTimesChartData, wiki1kSchemaGcGarbageChartData, wiki1kSchemaGcPeakChartData, \
    wiki4kSchemaIndexChartData, wiki4kSchemaIndexDocsSecChartData, \
    wiki4kSchemaGcTimesChartData, wiki4kSchemaGcGarbageChartData, wiki4kSchemaGcPeakChartData, \
    wiki1kCloudIndexChartData, wiki1kCloudIndexDocsSecChartData, \
    wiki1kCloudGcTimesChartData, wiki1kCloudGcGarbageChartData, \
    wiki1kCloudGcPeakChartData, \
    wiki1kCloud1x2IndexChartData, wiki1kCloud1x2IndexDocsSecChartData, \
    wiki1kCloud1x2GcTimesChartData, wiki1kCloud1x2GcGarbageChartData, \
    wiki1kCloud1x2GcPeakChartData= chart_data

    f = open('%s/indexing.html' % constants.NIGHTLY_REPORTS_DIR, 'wb')
    w = f.write
    header(w, 'Solr nightly indexing benchmark')
    w('<h1>Indexing Throughput</h1>\n')
    w('<br>')
    w('<ul>')
    w('<li><a href="#SimpleSchemalessIndex">IMDB JSON dataset (649MB, 2436442 docs) indexed via bin/post in schemaless mode</a></li>')

    w('<li>~1KB docs from wikipedia (31GB, 33,332,620 docs)</li>')
    w('<ul>')
    w('<li><a href="#Wiki_1k_Index">GB/hour plain text indexing throughput</a></li>')
    w('<li><a href="#Wiki_1k_Index_Docs_sec">K docs/sec plain text indexing throughput</a></li>')
    w('<li><a href="#Wiki_1k_GCTimes">JIT/GC times indexing</a></li>')
    w('<li><a href="#Wiki_1k_Garbage">Garbage created</a></li>')
    w('<li><a href="#Wiki_1k_Peak_memory">Peak memory usage</a></li>')
    w('</ul>')

    w('<li>~4KB docs from wikipedia (29GB, 6,726,515 docs)</li>')
    w('<ul>')
    w('<li><a href="#Wiki_4k_Index">GB/hour plain text indexing throughput</a></li>')
    w('<li><a href="#Wiki_4k_Index_Docs_sec">K docs/sec plain text indexing throughput</a></li>')
    w('<li><a href="#Wiki_4k_GCTimes">JIT/GC times indexing</a></li>')
    w('<li><a href="#Wiki_4k_Garbage">Garbage created</a></li>')
    w('<li><a href="#Wiki_4k_Peak_memory">Peak memory usage</a></li>')
    w('</ul>')

    w('<li>~1KB docs from wikipedia (31 GB, 33,332,620 docs) on SolrCloud 2 nodes, 2 shards, 1 replica</li>')
    w('<ul>')
    w('<li><a href="#Wiki_1k_Cloud_Index">GB/hour plain text indexing throughput</a></li>')
    w('<li><a href="#Wiki_1k_Cloud_Index_Docs_sec">K docs/sec plain text indexing throughput</a></li>')
    w('<li><a href="#Wiki_1k_Cloud_GCTimes">JIT/GC times indexing</a></li>')
    w('<li><a href="#Wiki_1k_Cloud_Garbage">Garbage created</a></li>')
    w('<li><a href="#Wiki_1k_Cloud_Peak_memory">Peak memory usage</a></li>')
    w('</ul>')

    w('<li>~1KB docs from wikipedia (31 GB, 33,332,620 docs) on SolrCloud 2 nodes, 1 shards, 2 replicas</li>')
    w('<ul>')
    w('<li><a href="#Wiki_1k_Cloud1x2_Index">GB/hour plain text indexing throughput</a></li>')
    w('<li><a href="#Wiki_1k_Cloud1x2_Index_Docs_sec">K docs/sec plain text indexing throughput</a></li>')
    w('<li><a href="#Wiki_1k_Cloud1x2_GCTimes">JIT/GC times indexing</a></li>')
    w('<li><a href="#Wiki_1k_Cloud1x2_Garbage">Garbage created</a></li>')
    w('<li><a href="#Wiki_1k_Cloud1x2_Peak_memory">Peak memory usage</a></li>')
    w('</ul>')

    w('</ul>')
    w(getOneGraphHTML(annotations, 'SimpleSchemalessIndex', simpleIndexChartData, "JSON MB/sec", "IMDB",
                      errorBars=False))
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Index', wiki1kSchemaIndexChartData, "GB/hour", "~1 KB Wikipedia English docs",
                      errorBars=False))
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Index_Docs_sec', wiki1kSchemaIndexDocsSecChartData, "k docs/sec", "~1 KB Wikipedia English docs",
                      errorBars=False))
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_GCTimes', wiki1kSchemaGcTimesChartData, "Seconds", "JIT/GC times indexing ~1 KB docs", errorBars=False))
    w('\n')
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Garbage', wiki1kSchemaGcGarbageChartData, "GB", "Garbage created indexing ~1 KB docs", errorBars=False))
    w('\n')
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Peak_memory', wiki1kSchemaGcPeakChartData, "MB", "Peak memory usage indexing ~1 KB docs", errorBars=False))

    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_4k_Index', wiki4kSchemaIndexChartData, "GB/hour", "~4 KB Wikipedia English docs",
                      errorBars=False))
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_4k_Index_Docs_sec', wiki4kSchemaIndexDocsSecChartData, "k docs/sec", "~4 KB Wikipedia English docs",
                      errorBars=False))
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_4k_GCTimes', wiki4kSchemaGcTimesChartData, "Seconds", "JIT/GC times indexing ~4 KB docs", errorBars=False))
    w('\n')
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_4k_Garbage', wiki4kSchemaGcGarbageChartData, "GB", "Garbage created indexing ~4 KB docs", errorBars=False))
    w('\n')
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_4k_Peak_memory', wiki4kSchemaGcPeakChartData, "MB", "Peak memory usage indexing ~4 KB docs", errorBars=False))

    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Cloud_Index', wiki1kCloudIndexChartData, "GB/hour", "SolrCloud: ~1 KB Wikipedia English docs - 2 shard, 1 replica", errorBars=False))
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Cloud_Index_Docs_sec', wiki1kCloudIndexDocsSecChartData, "k docs/sec", "SolrCloud: ~1 KB Wikipedia English docs - 2 shard, 1 replica", errorBars=False))
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Cloud_GCTimes', wiki1kCloudGcTimesChartData, "Seconds", "SolrCloud: ~1 KB Wikipedia English docs - 2 shard, 1 replica - JIT/GC times", errorBars=False))
    w('\n')
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Cloud_Garbage', wiki1kCloudGcGarbageChartData, "GB", "SolrCloud: ~1 KB Wikipedia English docs - 2 shard, 1 replica - Garbage created", errorBars=False))
    w('\n')
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Cloud_Peak_memory', wiki1kCloudGcPeakChartData, "MB", "SolrCloud: ~1 KB Wikipedia English docs - 2 shard, 1 replica - Peak memory usage", errorBars=False))

    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Cloud1x2_Index', wiki1kCloud1x2IndexChartData, "GB/hour", "SolrCloud: ~1 KB Wikipedia English docs - 1 shard, 2 replicas", errorBars=False))
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Cloud1x2_Index_Docs_sec', wiki1kCloud1x2IndexDocsSecChartData, "k docs/sec", "SolrCloud: ~1 KB Wikipedia English docs - 1 shard, 2 replicas", errorBars=False))
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Cloud1x2_GCTimes', wiki1kCloud1x2GcTimesChartData, "Seconds", "SolrCloud: ~1 KB Wikipedia English docs - 1 shard, 2 replica - JIT/GC times", errorBars=False))
    w('\n')
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Cloud1x2_Garbage', wiki1kCloud1x2GcGarbageChartData, "GB", "SolrCloud: ~1 KB Wikipedia English docs - 1 shard, 2 replica - Garbage created", errorBars=False))
    w('\n')
    w('<br>')
    w('<br>')
    w(getOneGraphHTML(annotations, 'Wiki_1k_Cloud1x2_Peak_memory', wiki1kCloud1x2GcPeakChartData, "MB", "SolrCloud: ~1 KB Wikipedia English docs - 1 shard, 2 replica - Peak memory usage", errorBars=False))

    writeKnownChanges(annotations, w)
    footer(w)
    f.close()
