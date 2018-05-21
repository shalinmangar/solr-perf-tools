package org.apache.solr.perf;

/**
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The ASF licenses this file to You under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance with
 * the License.  You may obtain a copy of the License at
 * <p/>
 * http://www.apache.org/licenses/LICENSE-2.0
 * <p/>
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */


import org.apache.solr.client.solrj.SolrClient;
import org.apache.solr.client.solrj.impl.*;
import org.apache.solr.common.cloud.DocCollection;
import org.apache.solr.common.cloud.Replica;
import org.apache.solr.common.cloud.Slice;

import java.util.Random;
import java.util.concurrent.atomic.AtomicBoolean;

public final class WikiIndexer {

  static StatisticsHelper[] stats;

  public static void main(String[] clArgs) throws Exception {
    Args args = new Args(clArgs);
    if (args.getFlag("-useCloudSolrClient")) {
      stats = new StatisticsHelper[2];
      stats[0] = StatisticsHelper.createRemoteStats("9999");
      stats[0].setLabel("8983");
      stats[1] = StatisticsHelper.createRemoteStats("10000");
      stats[1].setLabel("8984");
    } else  {
      stats = new StatisticsHelper[1];
      stats[0] = StatisticsHelper.createRemoteStats("9999");
    }
    try {
      for (StatisticsHelper stat : stats) {
        stat.startStatistics();
      }
      try {
        _main(clArgs);
      } finally {
        for (StatisticsHelper stat : stats) {
          stat.stopStatistics();
        }
      }
    } catch (Exception e) {
      e.printStackTrace();
    }
  }

  private static void _main(String[] clArgs) throws Exception {

    Args args = new Args(clArgs);

    final boolean useHttpSolrClient = args.getFlag("-useHttpSolrClient");
    final boolean useConcurrentUpdateSolrClient = args.getFlag("-useConcurrentUpdateSolrClient");
    final boolean useCloudSolrClient = args.getFlag("-useCloudSolrClient");

    final String zkHost, collectionName, solrUrl;
    if (useCloudSolrClient) {
      zkHost = args.getString("-zkHost");
      collectionName = args.getString("-collection");
      solrUrl = null;
    } else {
      zkHost = collectionName = null;
      solrUrl = args.getString("-solrUrl");
    }

    final String lineFile = args.getString("-lineDocsFile");

    // -1 means all docs in the line file:
    final int docCountLimit = args.getInt("-docCountLimit");
    int numThreads = args.getInt("-threadCount");
    final int batchSize = args.getInt("-batchSize");

    final boolean verbose = args.getFlag("-verbose");

    final boolean doDeletions = args.getFlag("-deletions");
    final boolean printDPS = args.getFlag("-printDPS");

    // True to start back at the beginning if we run out of
    // docs from the line file source:
    final boolean repeatDocs = args.getFlag("-repeatDocs");

    args.check();

    System.out.println("Line file: " + lineFile);
    System.out.println("Doc count limit: " + (docCountLimit == -1 ? "all docs" : "" + docCountLimit));
    System.out.println("Threads: " + numThreads);
    System.out.println("Batch size: " + batchSize);
    System.out.println("Verbose: " + (verbose ? "yes" : "no"));
    System.out.println("Do deletions: " + (doDeletions ? "yes" : "no"));
    System.out.println("Repeat docs: " + repeatDocs);

    final AtomicBoolean indexingFailed = new AtomicBoolean();

    final SolrClient client;
    if (useHttpSolrClient) {
      HttpSolrClient c = new HttpSolrClient(solrUrl);
      c.setParser(new BinaryResponseParser());
      c.setRequestWriter(new BinaryRequestWriter());
      client = c;
    } else if (useConcurrentUpdateSolrClient) {
      ConcurrentUpdateSolrClient c = new ConcurrentUpdateSolrClient(solrUrl, batchSize * 2, numThreads);
      c.setParser(new BinaryResponseParser());
      c.setRequestWriter(new BinaryRequestWriter());
      c.setPollQueueTime(0);
      client = c;
      numThreads = 1; // no need to spawn multiple feeder threads when using ConcurrentUpdateSolrClient
    } else if (useCloudSolrClient) {
      CloudSolrClient c = new CloudSolrClient(zkHost);
      c.setDefaultCollection(collectionName);
      client = c;
      c.connect();
      DocCollection collection = c.getZkStateReader().getClusterState().getCollection("gettingstarted");
      for (Slice slice : collection.getActiveSlices()) {
        if (slice.getReplicas().size() > 1)  {
          for (Replica replica : slice.getReplicas()) {
            for (StatisticsHelper stat : stats) {
              if (replica.getNodeName().contains(stat.getLabel()))  {
                if (slice.getLeader() == replica) {
                  stat.setLabel("leader");
                } else  {
                  stat.setLabel("replica");
                }
              }
            }
          }
        } else  {
          for (Replica replica : slice.getReplicas()) {
            for (StatisticsHelper stat : stats) {
              if (replica.getNodeName().contains(stat.getLabel()))  {
                stat.setLabel(replica.getNodeName());
              }
            }
          }
        }
      }
    } else {
      throw new RuntimeException("Either -useHttpSolrClient or -useConcurrentUpdateSolrClient or -useCloudSolrClient must be specified");
    }

    try {
      LineFileDocs lineFileDocs = new LineFileDocs(lineFile, repeatDocs);

      float docsPerSecPerThread = -1f;

      IndexThreads threads = new IndexThreads(client, indexingFailed, lineFileDocs, numThreads, docCountLimit, printDPS, docsPerSecPerThread, null, batchSize);

      System.out.println("\nIndexer: start");
      final long t0 = System.currentTimeMillis();

      threads.start();

      while (!threads.done() && !indexingFailed.get()) {
        Thread.sleep(100);
      }

      threads.stop();

      if (client instanceof ConcurrentUpdateSolrClient) {
        ConcurrentUpdateSolrClient concurrentUpdateSolrClient = (ConcurrentUpdateSolrClient) client;
        concurrentUpdateSolrClient.blockUntilFinished();
      }
      client.commit();

      final long tFinal = System.currentTimeMillis();
      System.out.println("\nIndexer: finished (" + (tFinal - t0) + " msec)");
      System.out.println("\nIndexer: net bytes indexed " + threads.getBytesIndexed());
      System.out.println("\nIndexer: " + (threads.getBytesIndexed() / 1024. / 1024. / 1024. / ((tFinal - t0) / 3600000.)) + " GB/hour plain text");
    } finally {
      client.close();
    }
  }
}
