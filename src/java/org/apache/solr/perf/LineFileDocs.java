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

// FIELDS_HEADER_INDICATOR###	title	timestamp	text	username	characterCount	categories	imageCount	sectionCount	subSectionCount	subSubSectionCount	refCount

import org.apache.solr.common.SolrInputDocument;

import java.io.*;
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicLong;

/*
  Copied over from luceneutil and modified for our purposes
  https://github.com/mikemccand/luceneutil
 */
public class LineFileDocs implements Closeable {

  private final static int BUFFER_SIZE = 1 << 16;     // 64K
  private final static char SEP = '\t';
  private final boolean doRepeat;
  private final String path;
  private final AtomicLong bytesIndexed = new AtomicLong();
  private BufferedReader reader;
  private String[] extraFacetFields;
  private int readCount;

  public LineFileDocs(String path, boolean doRepeat) throws IOException {
    this.path = path;
    this.doRepeat = doRepeat;
    open();
  }

  public static String intToID(int id) {
    // Base 36, prefixed with 0s to be length 6 (= 2.2 B)
    final String s = String.format("%6s", Integer.toString(id, Character.MAX_RADIX)).replace(' ', '0');
    //System.out.println("fromint: " + id + " -> " + s);
    return s;
  }

  public static int idToInt(String id) {
    // Decode base 36
    int accum = 0;
    int downTo = id.length() - 1;
    int multiplier = 1;
    while (downTo >= 0) {
      final char ch = id.charAt(downTo--);
      final int digit;
      if (ch >= '0' && ch <= '9') {
        digit = ch - '0';
      } else if (ch >= 'a' && ch <= 'z') {
        digit = 10 + (ch - 'a');
      } else {
        assert false;
        digit = -1;
      }
      accum += multiplier * digit;
      multiplier *= 36;
    }

    return accum;
  }

  public long getBytesIndexed() {
    return bytesIndexed.get();
  }

  private void open() throws IOException {
    InputStream is = new FileInputStream(path);
    reader = new BufferedReader(new InputStreamReader(is, "UTF-8"), BUFFER_SIZE);
    String firstLine = reader.readLine();
    if (firstLine.startsWith("FIELDS_HEADER_INDICATOR")) {
      if (!firstLine.startsWith("FIELDS_HEADER_INDICATOR###	doctitle	docdate	body") &&
              !firstLine.startsWith("FIELDS_HEADER_INDICATOR###	title	timestamp	text")) {
        throw new IllegalArgumentException("unrecognized header in line docs file: " + firstLine.trim());
      }
      // Skip header
    } else {
      // Old format: no header
      reader.close();
      is = new FileInputStream(path);
      reader = new BufferedReader(new InputStreamReader(is, "UTF-8"), BUFFER_SIZE);
    }
  }

  public synchronized void close() throws IOException {
    if (reader != null) {
      reader.close();
      reader = null;
    }
  }

  public DocState newDocState() {
    return new DocState();
  }

  @SuppressWarnings({"rawtypes", "unchecked"})
  public SolrInputDocument nextDoc(DocState doc) throws IOException {
    String line;
    final int myID;
    synchronized (this) {
      myID = readCount++;
      line = reader.readLine();
      if (line == null) {
        if (doRepeat) {
          close();
          open();
          line = reader.readLine();
        } else {
          return null;
        }
      }
    }

    int spot = line.indexOf(SEP);
    if (spot == -1) {
      throw new RuntimeException("line: [" + line + "] is in an invalid format !");
    }
    int spot2 = line.indexOf(SEP, 1 + spot);
    if (spot2 == -1) {
      throw new RuntimeException("line: [" + line + "] is in an invalid format !");
    }
    int spot3 = line.indexOf(SEP, 1 + spot2);
    if (spot3 == -1) {
      spot3 = line.length();
    }
    bytesIndexed.addAndGet(spot3);

    SolrInputDocument document = new SolrInputDocument();

    document.addField("body", line.substring(1 + spot2, spot3));
    final String title = line.substring(0, spot);
    document.addField("title", title);

//    if (addDVFields) {
//      //doc.titleBDV.setBytesValue(new BytesRef(title));
//      doc.titleDV.setBytesValue(new BytesRef(title));
//      doc.titleTokenized.setStringValue(title);
//    }

    final String dateString = line.substring(1 + spot, spot2);

    document.addField("id", intToID(myID));
    doc.datePos.setIndex(0);
    final Date date = doc.dateParser.parse(dateString, doc.datePos);
    if (date == null) {
      System.out.println("FAILED: " + dateString);
    } else  {
      document.addField("date", date);
    }
    doc.dateCal.setTime(date);

//    if (addDVFields) {
//      doc.lastModNDV.setLongValue(doc.dateCal.getTimeInMillis());
//    }

    final int sec = doc.dateCal.get(Calendar.HOUR_OF_DAY) * 3600 + doc.dateCal.get(Calendar.MINUTE) * 60 + doc.dateCal.get(Calendar.SECOND);

    document.addField("timesecnum", sec);

    return document;
  }

  //private final Random rand = new Random(17);

  public static final class DocState {
    // Necessary for "old style" wiki line files:
    final SimpleDateFormat dateParser = new SimpleDateFormat("dd-MMM-yyyy HH:mm:ss", Locale.US);

    // For just y/m/day:
    //final SimpleDateFormat dateParser = new SimpleDateFormat("y/M/d", Locale.US);

    //final SimpleDateFormat dateParser = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US);
    final Calendar dateCal = Calendar.getInstance();
    final ParsePosition datePos = new ParsePosition(0);
  }
}

