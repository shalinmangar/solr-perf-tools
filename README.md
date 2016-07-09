# solr-perf-tools
Performance benchmarking utilities for Apache Solr

Inspired by Lucene benchmarks hosted at https://people.apache.org/~mikemccand/lucenebench/

## Setup

Make sure your system has the following installed and in your path:
1. python 2.7.x+
2. java 8
3. git
4. ant
5. [python requests module](http://docs.python-requests.org/en/master/user/install/)

## Configuring

The benchmark requires a few directories to be available:
1. TEST_BASE_DIR_1 (defaults to ``/solr-bench`)
2. TEST_BASE_DIR_2 (defaults to ``/solr-bench2`)
3. DATA_BASE_DIR (defaults to ``/solr-data`)

You can change the location of the above directories by editing the `src/python/constants.py` file.

If you want the benchmark start and finish summary to be sent to Slack then you should add the following
environment variables to your system:
```bash
export SLACK_URL=https://company.slack.com/services/hooks/slackbot
export SLACK_CHANNEL=channel_name
export SLACK_BOT_TOKEN=actual_slack_token
```

## Test data

The wiki-1k test data can be downloaded from http://home.apache.org/~mikemccand/enwiki-20120502-lines.txt.lzma

The IMDB test data is a JSON file containing movie and actor data from IMDB.com. At this time this download is no
longer available from IMDB. But any JSON file containing a list of JSON documents can be used instead. These tests
use a 600MB JSON file containing approximately 2.4M documents.

The wiki-4k test data is a variant of wiki-1k where each document is a 4KB in size.

The location of all the above files are configured in src/python/constants.py along with the number of documents
that each of them contain. This information is used for verification of full indexation at the end of the run.

## Tests

* IMDB data indexed in schemaless mode with bin/post
* wiki-1k data indexed with explicit schema
* wiki-4k data indexed with explicit schema

For both wiki-1k and wiki-4k, we start Solr with schemaless configs and then use the Config API to explicitly
add the required fields and disable the _text_ copy field (to avoid duplicate indexing of text body)

## Running

Running is easy!

Without slack integration:
`python src/python/bench.py`

With slack integration enabled:
`python src/python/bench.py -enable-slack-bot`

## Output

* Reports can be found at `$TEST_BASE_DIR_1/reports` (`/solr-bench/reports`)
* Logs can be found at `$TEST_BASE_DIR_1/logs`  (`/solr-bench/logs`)
* The solr checkout is at `$TEST_BASE_DIR_1/checkout` (`/solr-bench/checkout`)
* The solr instance(s) used for benchmarks are at `TEST_BASE_DIR_1/solr` and `TEST_BASE_DIR_2/solr`
..* The instance directories will have the fully built indexes at the end of the benchmark

## How it works

* The benchmark program checks out the latest master branch of Solr or updates to the latest commit
* Builds the Solr tgz binaries by invoking `cd solr; ant create-package`
* Compiles the java client for the benchmark (found at src/java) using the solr jars in the `dist` directory
* Extracts the solr tgz to the instance directories
* Runs solr (the actual jvm parameters are specific to the test)
* Executes the benchmark client
* The client outputs all the stats necessary for creating the reports. These are extracted from the output using regexp
* The report is an html page containing graphs rendered with d3.js