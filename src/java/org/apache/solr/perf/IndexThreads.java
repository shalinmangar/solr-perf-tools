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
import org.apache.solr.common.SolrInputDocument;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

class IndexThreads {

  final IngestRatePrinter printer;
  final CountDownLatch startLatch = new CountDownLatch(1);
  final AtomicBoolean stop;
  final AtomicBoolean failed;
  final LineFileDocs docs;
  final Thread[] threads;

  public IndexThreads(SolrClient client, AtomicBoolean indexingFailed, LineFileDocs lineFileDocs, int numThreads, int docCountLimit,
                      boolean printDPS, float docsPerSecPerThread, UpdatesListener updatesListener, int batchSize)
          throws IOException, InterruptedException {

    this.docs = lineFileDocs;

    threads = new Thread[numThreads];

    final CountDownLatch stopLatch = new CountDownLatch(numThreads);
    final AtomicInteger count = new AtomicInteger();
    stop = new AtomicBoolean(false);
    failed = indexingFailed;

    for (int thread = 0; thread < numThreads; thread++) {
      threads[thread] = new IndexThread(startLatch, stopLatch, client, docs, docCountLimit, count, stop, docsPerSecPerThread, failed, updatesListener, batchSize);
      threads[thread].start();
    }

    Thread.sleep(10);

    if (printDPS) {
      printer = new IngestRatePrinter(count, stop);
      printer.start();
    } else {
      printer = null;
    }
  }

  public void start() {
    startLatch.countDown();
  }

  public long getBytesIndexed() {
    return docs.getBytesIndexed();
  }

  public void stop() throws InterruptedException, IOException {
    stop.getAndSet(true);
    for (Thread t : threads) {
      t.join();
    }
    if (printer != null) {
      printer.join();
    }
    docs.close();
  }

  public boolean done() {
    for (Thread t : threads) {
      if (t.isAlive()) {
        return false;
      }
    }

    return true;
  }



  public static interface UpdatesListener {
    public void beforeUpdate();

    public void afterUpdate();
  }

  private static class IndexThread extends Thread {
    private final LineFileDocs docs;
    private final int numTotalDocs;
    private final SolrClient client;
    private final AtomicBoolean stop;
    private final AtomicInteger count;
    private final CountDownLatch startLatch;
    private final CountDownLatch stopLatch;
    private final float docsPerSec;
    private final AtomicBoolean failed;
    private final UpdatesListener updatesListener;
    private final int batchSize;

    public IndexThread(CountDownLatch startLatch, CountDownLatch stopLatch, SolrClient client,
                       LineFileDocs docs, int numTotalDocs, AtomicInteger count,
                       AtomicBoolean stop, float docsPerSec,
                       AtomicBoolean failed, UpdatesListener updatesListener, int batchSize) {
      this.startLatch = startLatch;
      this.stopLatch = stopLatch;
      this.client = client;
      this.docs = docs;
      this.numTotalDocs = numTotalDocs;
      this.count = count;
      this.stop = stop;
      this.docsPerSec = docsPerSec;
      this.failed = failed;
      this.updatesListener = updatesListener;
      this.batchSize = batchSize;
    }

    @Override
    public void run() {
      try {
        final LineFileDocs.DocState docState = docs.newDocState();
        final long tStart = System.currentTimeMillis();

        try {
          startLatch.await();
        } catch (InterruptedException ie) {
          Thread.currentThread().interrupt();
          return;
        }

        if (docsPerSec > 0) {
          final long startNS = System.nanoTime();
          int threadCount = 0;
          while (!stop.get()) {
            final SolrInputDocument doc = docs.nextDoc(docState);
            if (doc == null) {
              break;
            }
            final int id = LineFileDocs.idToInt(doc.getFieldValue("id").toString());
            if (numTotalDocs != -1 && id >= numTotalDocs) {
              break;
            }

            if (((1 + id) % 100000) == 0) {
              System.out.println("Indexer: " + (1 + id) + " docs... (" + (System.currentTimeMillis() - tStart) + " msec)");
            }
            if (updatesListener != null) {
              updatesListener.beforeUpdate();
            }
            client.add(doc);

            if (updatesListener != null) {
              updatesListener.afterUpdate();
            }
            int docCount = count.incrementAndGet();
            threadCount++;

            if ((docCount % 100000) == 0) {
              System.out.println("Indexer: " + docCount + " docs... (" + (System.currentTimeMillis() - tStart) + " msec)");
            }

            final long sleepNS = startNS + (long) (1000000000 * (threadCount / docsPerSec)) - System.nanoTime();
            if (sleepNS > 0) {
              final long sleepMS = sleepNS / 1000000;
              final int sleepNS2 = (int) (sleepNS - sleepMS * 1000000);
              Thread.sleep(sleepMS, sleepNS2);
            }
          }
        } else {
          outer:
          while (!stop.get()) {
            if (batchSize > 1)  {
              List<SolrInputDocument> list = new ArrayList<SolrInputDocument>(batchSize);
              for (int i=0; i<batchSize; i++) {
                final SolrInputDocument doc = docs.nextDoc(docState);
                if (doc == null) {
                  break outer;
                }
//              Object id = doc.getFieldValue("id");
//              if (doc.getFieldValue("body").toString().length() > 10922)  {
//                System.out.println("Long body: id = " + id);
//                i--;
//                continue;
//              }
//              if (id.equals("00547r") || id.equals("03fetn") || id.equals("04n7lu") || id.equals("04z8uc")) {
//                i--;
//                continue;
//              }
                int docCount = count.incrementAndGet();
                if (numTotalDocs != -1 && docCount > numTotalDocs) {
                  break;
                }
                if ((docCount % 100000) == 0) {
                  System.out.println("Indexer: " + docCount + " docs... (" + (System.currentTimeMillis() - tStart) + " msec)");
                }
                list.add(doc);
              }

              if (!list.isEmpty()) {
                client.add(list);
              }
            } else  {
              final SolrInputDocument doc = docs.nextDoc(docState);
              if (doc == null) {
                break;
              }
              client.add(doc);
            }
          }
        }
      } catch (Exception e) {
        failed.set(true);
        throw new RuntimeException(e);
      } finally {
        stopLatch.countDown();
      }
    }
  }

  private static class IngestRatePrinter extends Thread {

    private final AtomicInteger count;
    private final AtomicBoolean stop;

    public IngestRatePrinter(AtomicInteger count, AtomicBoolean stop) {
      this.count = count;
      this.stop = stop;
    }

    @Override
    public void run() {
      long time = System.currentTimeMillis();
      System.out.println("startIngest: " + time);
      final long start = time;
      int lastCount = count.get();
      while (!stop.get()) {
        try {
          Thread.sleep(200);
        } catch (Exception ex) {
        }
        int numDocs = count.get();

        double current = numDocs - lastCount;
        long now = System.currentTimeMillis();
        double seconds = (now - time) / 1000.0d;
        System.out.println("ingest: " + (current / seconds) + " " + (now - start));
        time = now;
        lastCount = numDocs;
      }
    }
  }
}
