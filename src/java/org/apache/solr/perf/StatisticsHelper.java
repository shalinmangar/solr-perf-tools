/** Poached from cometd 2.1.0, Apache 2 license */

package org.apache.solr.perf;

import javax.management.*;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;
import java.io.IOException;
import java.lang.management.*;
import java.util.*;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 *
 */
public class StatisticsHelper implements Runnable {

  protected final MBeanServerConnection connection;

  protected final OperatingSystemMXBean operatingSystem;

  protected final CompilationMXBean jitCompiler;

  protected final MemoryMXBean heapMemory;

  protected final AtomicInteger starts = new AtomicInteger();

  protected volatile MemoryPoolMXBean youngMemoryPool;

  protected volatile MemoryPoolMXBean survivorMemoryPool;

  protected volatile MemoryPoolMXBean oldMemoryPool;

  protected volatile boolean hasMemoryPools;

  protected volatile ScheduledFuture< ? > memoryPoller;

  protected volatile GarbageCollectorMXBean youngCollector;

  protected volatile GarbageCollectorMXBean oldCollector;

  protected volatile boolean hasCollectors;

  protected volatile ScheduledExecutorService scheduler;

  protected volatile boolean polling;

  protected volatile long lastYoungUsed;

  protected volatile long startYoungCollections;

  protected volatile long startYoungCollectionsTime;

  protected volatile long totalYoungUsed;

  protected volatile long lastSurvivorUsed;

  protected volatile long totalSurvivorUsed;

  protected volatile long lastOldUsed;

  protected volatile long startOldCollections;

  protected volatile long startOldCollectionsTime;

  protected volatile long totalOldUsed;

  protected volatile long startTime;

  protected volatile long startProcessCPUTime;

  protected volatile long startJITCTime;

  protected volatile PeriodSampler periodSampler;

  protected String label;

  public String getLabel() {
    return label;
  }

  public void setLabel(String label) {
    this.label = label;
  }

  public static StatisticsHelper createLocalStats() throws IOException, MalformedObjectNameException {

    MBeanServerConnection connection = ManagementFactory.getPlatformMBeanServer();
    return createStats(connection);

//    OperatingSystemMXBean operatingSystem = ManagementFactory.getOperatingSystemMXBean();
//
//    CompilationMXBean jitCompiler = ManagementFactory.getCompilationMXBean();
//
//    MemoryMXBean heapMemory = ManagementFactory.getMemoryMXBean();
//
//    MemoryPoolMXBean youngMemoryPool = null, survivorMemoryPool = null, oldMemoryPool = null;
//
//    List<MemoryPoolMXBean> memoryPools = ManagementFactory.getMemoryPoolMXBeans();
//    for (MemoryPoolMXBean memoryPool : memoryPools) {
//      if ("PS Eden Space".equals(memoryPool.getName()) || "Par Eden Space".equals(memoryPool.getName())
//              || "G1 Eden".equals(memoryPool.getName())) {
//        youngMemoryPool = memoryPool;
//      } else if ("PS Survivor Space".equals(memoryPool.getName()) || "Par Survivor Space".equals(memoryPool.getName())
//              || "G1 Survivor".equals(memoryPool.getName())) {
//        survivorMemoryPool = memoryPool;
//      } else if ("PS Old Gen".equals(memoryPool.getName()) || "CMS Old Gen".equals(memoryPool.getName())
//              || "G1 Old Gen".equals(memoryPool.getName())) {
//        oldMemoryPool = memoryPool;
//      }
//    }
//
//    GarbageCollectorMXBean youngCollector = null, oldCollector = null;
//
//    List<GarbageCollectorMXBean> garbageCollectors = ManagementFactory.getGarbageCollectorMXBeans();
//    for (GarbageCollectorMXBean garbageCollector : garbageCollectors) {
//      if ("PS Scavenge".equals(garbageCollector.getName()) || "ParNew".equals(garbageCollector.getName())
//              || "G1 Young Generation".equals(garbageCollector.getName())) {
//        youngCollector = garbageCollector;
//      } else if ("PS MarkSweep".equals(garbageCollector.getName())
//              || "ConcurrentMarkSweep".equals(garbageCollector.getName())
//              || "G1 Old Generation".equals(garbageCollector.getName())) {
//        oldCollector = garbageCollector;
//      }
//    }
//
//    return new StatisticsHelper(operatingSystem, jitCompiler, heapMemory, youngMemoryPool, survivorMemoryPool, oldMemoryPool, youngCollector, oldCollector);
  }

  public static StatisticsHelper createRemoteStats(String port) throws IOException, MalformedObjectNameException {
    String url = "service:jmx:rmi:///jndi/rmi://127.0.1.1:" + port + "/jmxrmi";
    JMXServiceURL serviceURL = new JMXServiceURL(url);
    JMXConnector jmxConnector = JMXConnectorFactory.connect(serviceURL);
    MBeanServerConnection connection = jmxConnector.getMBeanServerConnection();

    return createStats(connection);
  }

  private static StatisticsHelper createStats(MBeanServerConnection connection) throws IOException, MalformedObjectNameException {
    OperatingSystemMXBean operatingSystem = ManagementFactory.newPlatformMXBeanProxy(connection, ManagementFactory.OPERATING_SYSTEM_MXBEAN_NAME, com.sun.management.OperatingSystemMXBean.class);
    CompilationMXBean jitCompiler = ManagementFactory.newPlatformMXBeanProxy(connection, ManagementFactory.COMPILATION_MXBEAN_NAME, CompilationMXBean.class);
    MemoryMXBean heapMemory = ManagementFactory.newPlatformMXBeanProxy(connection, ManagementFactory.MEMORY_MXBEAN_NAME, MemoryMXBean.class);

    Set<ObjectName> memoryPoolNames = connection.queryNames(new ObjectName(ManagementFactory.MEMORY_POOL_MXBEAN_DOMAIN_TYPE + ",*"), null);
    List<MemoryPoolMXBean> memoryPools = new ArrayList<MemoryPoolMXBean>(memoryPoolNames.size());
    for (ObjectName memoryPoolName : memoryPoolNames) {
      MemoryPoolMXBean proxy = ManagementFactory.newPlatformMXBeanProxy(connection, memoryPoolName.toString(), MemoryPoolMXBean.class);
      memoryPools.add(proxy);
    }
    MemoryPoolMXBean youngMemoryPool = null, survivorMemoryPool = null, oldMemoryPool = null;
    for (MemoryPoolMXBean memoryPool : memoryPools) {
      if ("PS Eden Space".equals(memoryPool.getName()) || "Par Eden Space".equals(memoryPool.getName())
              || "G1 Eden".equals(memoryPool.getName())) {
        youngMemoryPool = memoryPool;
      } else if ("PS Survivor Space".equals(memoryPool.getName()) || "Par Survivor Space".equals(memoryPool.getName())
              || "G1 Survivor".equals(memoryPool.getName())) {
        survivorMemoryPool = memoryPool;
      } else if ("PS Old Gen".equals(memoryPool.getName()) || "CMS Old Gen".equals(memoryPool.getName())
              || "G1 Old Gen".equals(memoryPool.getName())) {
        oldMemoryPool = memoryPool;
      }
    }

    Set<ObjectName> garbageCollectorNames = connection.queryNames(new ObjectName(ManagementFactory.GARBAGE_COLLECTOR_MXBEAN_DOMAIN_TYPE + ",*"), null);
    List<GarbageCollectorMXBean> garbageCollectors = new ArrayList<GarbageCollectorMXBean>(garbageCollectorNames.size());
    for (ObjectName garbageCollectorName : garbageCollectorNames) {
      GarbageCollectorMXBean proxy = ManagementFactory.newPlatformMXBeanProxy(connection, garbageCollectorName.toString(), GarbageCollectorMXBean.class);
      garbageCollectors.add(proxy);
    }
    GarbageCollectorMXBean youngCollector = null, oldCollector = null;
    for (GarbageCollectorMXBean garbageCollector : garbageCollectors) {
      if ("PS Scavenge".equals(garbageCollector.getName()) || "ParNew".equals(garbageCollector.getName())
              || "G1 Young Generation".equals(garbageCollector.getName())) {
        youngCollector = garbageCollector;
      } else if ("PS MarkSweep".equals(garbageCollector.getName())
              || "ConcurrentMarkSweep".equals(garbageCollector.getName())
              || "G1 Old Generation".equals(garbageCollector.getName())) {
        oldCollector = garbageCollector;
      }
    }

    return new StatisticsHelper(connection, operatingSystem, jitCompiler, heapMemory, youngMemoryPool, survivorMemoryPool, oldMemoryPool, youngCollector, oldCollector);
  }

  protected StatisticsHelper(MBeanServerConnection connection, OperatingSystemMXBean operatingSystem, CompilationMXBean jitCompiler, MemoryMXBean heapMemory,
                             MemoryPoolMXBean youngMemoryPool, MemoryPoolMXBean survivorMemoryPool, MemoryPoolMXBean oldMemoryPool,
                             GarbageCollectorMXBean youngCollector, GarbageCollectorMXBean oldCollector) {
    this.connection = connection;
    this.operatingSystem = operatingSystem;
    this.jitCompiler = jitCompiler;
    this.heapMemory = heapMemory;
    this.youngMemoryPool = youngMemoryPool;
    this.survivorMemoryPool = survivorMemoryPool;
    this.oldMemoryPool = oldMemoryPool;
    this.youngCollector = youngCollector;
    this.oldCollector = oldCollector;

    this.hasMemoryPools = youngMemoryPool != null && survivorMemoryPool != null && oldMemoryPool != null;
    this.hasCollectors = youngCollector != null && oldCollector != null;
  }

  public void run() {

    if (!hasMemoryPools)
      return;

    long young = youngMemoryPool.getUsage().getUsed();
    long survivor = survivorMemoryPool.getUsage().getUsed();
    long old = oldMemoryPool.getUsage().getUsed();

    if (!polling) {
      polling = true;
    } else {
      if (lastYoungUsed <= young) {
        totalYoungUsed += young - lastYoungUsed;
      }

      if (lastSurvivorUsed <= survivor) {
        totalSurvivorUsed += survivor - lastSurvivorUsed;
      }

      if (lastOldUsed <= old) {
        totalOldUsed += old - lastOldUsed;
      } else {
        // May need something more here, like "how much was collected"
      }
    }
    lastYoungUsed = young;
    lastSurvivorUsed = survivor;
    lastOldUsed = old;
  }

  public boolean startStatistics() {
    // Support for multiple nodes requires to ignore start requests after the
    // first
    // but also requires that requests after the first wait until the
    // initialization
    // is completed (otherwise node #2 may start the run while the server is
    // GC'ing)
    synchronized (this) {
      if (starts.incrementAndGet() > 1)
        return false;

      heapMemory.gc();
      System.err.println("\n========================================");
      System.err.println("Statistics Started at " + new Date());
      System.err.println("Operative System: " + operatingSystem.getName() + " " + operatingSystem.getVersion() + " "
              + operatingSystem.getArch());
      System.err.println("JVM : " + System.getProperty("java.vm.vendor") + " " + System.getProperty("java.vm.name")
              + " runtime " + System.getProperty("java.vm.version") + " " + System.getProperty("java.runtime.version"));
      System.err.println("Processors: " + operatingSystem.getAvailableProcessors());
      if (operatingSystem instanceof com.sun.management.OperatingSystemMXBean) {
        com.sun.management.OperatingSystemMXBean os = (com.sun.management.OperatingSystemMXBean) operatingSystem;
        long totalMemory = os.getTotalPhysicalMemorySize();
        long freeMemory = os.getFreePhysicalMemorySize();
        System.err.println("System Memory: " + percent(totalMemory - freeMemory, totalMemory) + "% used of "
                + gibiBytes(totalMemory) + " GiB");
      } else {
        System.err.println("System Memory: N/A");
      }

      MemoryUsage heapMemoryUsage = heapMemory.getHeapMemoryUsage();
      System.err.println("Used Heap Size: " + mebiBytes(heapMemoryUsage.getUsed()) + " MiB");
      System.err.println("Max Heap Size: " + mebiBytes(heapMemoryUsage.getMax()) + " MiB");
      if (hasMemoryPools) {
        long youngGenerationHeap = heapMemoryUsage.getMax() - oldMemoryPool.getUsage().getMax();
        System.err.println("Young Generation Heap Size: " + mebiBytes(youngGenerationHeap) + " MiB");
      } else {
        System.err.println("Young Generation Heap Size: N/A");
      }

      System.err.println("- - - - - - - - - - - - - - - - - - - - ");

      scheduler = Executors.newSingleThreadScheduledExecutor();
      polling = false;
      memoryPoller = scheduler.scheduleWithFixedDelay(this, 0, 250, TimeUnit.MILLISECONDS);

      lastYoungUsed = 0;
      if (hasCollectors) {
        startYoungCollections = youngCollector.getCollectionCount();
        startYoungCollectionsTime = youngCollector.getCollectionTime();
      }
      totalYoungUsed = 0;
      lastSurvivorUsed = 0;
      totalSurvivorUsed = 0;
      lastOldUsed = 0;
      if (hasCollectors) {
        startOldCollections = oldCollector.getCollectionCount();
        startOldCollectionsTime = oldCollector.getCollectionTime();
      }
      totalOldUsed = 0;

      startTime = System.nanoTime();
      if (operatingSystem instanceof com.sun.management.OperatingSystemMXBean) {
        com.sun.management.OperatingSystemMXBean os = (com.sun.management.OperatingSystemMXBean) operatingSystem;
        startProcessCPUTime = os.getProcessCpuTime();
      }
      startJITCTime = jitCompiler.getTotalCompilationTime();

      periodSampler = new PeriodSampler(operatingSystem);
      periodSampler.start();
      return true;
    }
  }

  public boolean stopStatistics() {
    synchronized (this) {
      if (starts.decrementAndGet() > 0)
        return false;

      memoryPoller.cancel(false);
      scheduler.shutdown();
      periodSampler.stop();

      System.err.println("- - - - - - - - - - - - - - - - - - - - ");
      errPrint("Statistics Ended at " + new Date());
      long elapsedTime = System.nanoTime() - startTime;
      errPrint("Elapsed time: " + TimeUnit.NANOSECONDS.toMillis(elapsedTime) + " ms");
      long elapsedJITCTime = jitCompiler.getTotalCompilationTime() - startJITCTime;
      errPrint("Time in JIT compilation: " + elapsedJITCTime + " ms", 1);
      if (hasCollectors) {
        long elapsedYoungCollectionsTime = youngCollector.getCollectionTime() - startYoungCollectionsTime;
        long youngCollections = youngCollector.getCollectionCount() - startYoungCollections;
        errPrint("Time in Young Generation GC: " + elapsedYoungCollectionsTime + " ms (" + youngCollections
                + " collections)", 1);
        long elapsedOldCollectionsTime = oldCollector.getCollectionTime() - startOldCollectionsTime;
        long oldCollections = oldCollector.getCollectionCount() - startOldCollections;
        errPrint("Time in Old Generation GC: " + elapsedOldCollectionsTime + " ms (" + oldCollections
                + " collections)", 1);
      } else {
        errPrint("Time in GC: N/A", 1);
      }

      if (hasMemoryPools) {
        errPrint("Garbage Generated in Young Generation: " + mebiBytes(totalYoungUsed) + " MiB");
        errPrint("Garbage Generated in Survivor Generation: " + mebiBytes(totalSurvivorUsed) + " MiB");
        errPrint("Garbage Generated in Old Generation: " + mebiBytes(totalOldUsed) + " MiB");

        errPrint("Peak usage in Young Generation: " + mebiBytes(youngMemoryPool.getPeakUsage().getUsed()) + " MiB");
        errPrint("Peak usage in Survivor Generation: " + mebiBytes(survivorMemoryPool.getPeakUsage().getUsed()) + " MiB");
        errPrint("Peak usage in Old Generation: " + mebiBytes(oldMemoryPool.getPeakUsage().getUsed()) + " MiB");
      } else {
        errPrint("Garbage Generated: N/A");
      }

      errPrint(String.format("Average System Load: %.3f", periodSampler.systemLoad.average()));

      if (operatingSystem instanceof com.sun.management.OperatingSystemMXBean) {
        com.sun.management.OperatingSystemMXBean os = (com.sun.management.OperatingSystemMXBean) operatingSystem;
        long elapsedProcessCPUTime = os.getProcessCpuTime() - startProcessCPUTime;
        errPrint(String.format("Average CPU Time: %.3f/%d", ((float) elapsedProcessCPUTime * 100 / elapsedTime),
                (100 * operatingSystem.getAvailableProcessors())));
        errPrint(String.format("Average CPU Load: %.3f", (periodSampler.cpuLoad.average() * 100.0)));
      } else {
        errPrint("Average CPU Time: N/A");
        errPrint("Average CPU Load: N/A");
      }

      System.err.println("----------------------------------------\n");
      return true;
    }
  }

  private void errPrint(String message) {
    errPrint(message, 0);
  }

  private void errPrint(String message, int indentBy) {
    if (label == null)  {
      for (int i = 0; i < indentBy; i++) {
        System.err.print('\t');
      }
      System.err.println(message);
    } else  {
      for (int i = 0; i < indentBy; i++) {
        System.err.print('\t');
      }
      System.err.println(label + " - " + message);
    }
  }

  public float percent(long dividend, long divisor) {
    return (float) dividend * 100 / divisor;
  }

  public float mebiBytes(long bytes) {
    return (float) bytes / 1024 / 1024;
  }

  public float gibiBytes(long bytes) {
    return (float) bytes / 1024 / 1024 / 1024;
  }

  public static class Histogram {
    double sum = 0;
    double num = 0;

    public synchronized void add(double val) {
      sum += val;
      num++;
    }

    public synchronized double average() {
      return sum / num;
    }
  }

  public static class PeriodSampler {
    Timer timer = new Timer();
    Histogram cpuLoad = new Histogram();
    Histogram systemLoad = new Histogram();
    OperatingSystemMXBean os;
    long lastUpdate;

    public PeriodSampler(OperatingSystemMXBean os) {
      this.os = os;
    }

    public void start() {
      // every minute
      timer.schedule(new TimerTask() {
        @Override
        public void run() {
          update();
        }
      }, 100, 1000 * 60);
    }

    public synchronized void update () {
      if (os instanceof com.sun.management.OperatingSystemMXBean) {
        cpuLoad.add(((com.sun.management.OperatingSystemMXBean) os).getProcessCpuLoad());
      }
      systemLoad.add(os.getSystemLoadAverage());
      lastUpdate = System.nanoTime();
    }

    public void stop() {
      timer.cancel();
      // kinda bias to the last minutes metrics,
      // but on the long running task, this will be ok
      update();
    }
  }
}
