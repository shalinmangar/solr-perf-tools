#!/bin/python
import datetime
import sys
import os
import pickle

import bench
import constants
import utils


def generate_shas(start_date, end_date, delta_days):
    solr = bench.LuceneSolrCheckout(constants.CHECKOUT_DIR)
    solr.checkout('/dev/null')

    x = os.getcwd()
    try:
        os.chdir(constants.CHECKOUT_DIR)
        shas = []
        st = start_date
        while st < end_date:
            cmd = [constants.GIT_EXE, 'rev-list', '-n', '1', '--before="%s"' % st.strftime('%Y-%m-%d %H:%M:%S'), 'master']
            sha = utils.run_get_output(cmd)
            shas.append(sha.strip())
            st = st + delta_days
        print('Generated %d SHAs to backtest' % len(shas))
        return shas
    finally:
        os.chdir(x)


def save_shas(start_date, end_date, delta_days, shas):
    with open(constants.BACK_TEST_SHAS, 'wb') as f:
        pickle.dump((start_date, end_date, delta_days, shas), f)


def main():
    start_date = datetime.datetime.now()
    end_date = datetime.datetime.now()
    interval_days = 7

    if '-start-date' in sys.argv:
        index = sys.argv.index('-start-date')
        start_date_s = sys.argv[index + 1]
        start_date = datetime.datetime.strptime(start_date_s, '%Y.%m.%d.%H.%M.%S')

    if '-end-date' in sys.argv:
        index = sys.argv.index('-end-date')
        end_date_s = sys.argv[index + 1]
        end_date = datetime.datetime.strptime(end_date_s, '%Y.%m.%d.%H.%M.%S')

    if '-interval-days' in sys.argv:
        index = sys.argv.index('-interval-days')
        interval_days = int(sys.argv[index + 1])

    delta_days = datetime.timedelta(days=interval_days)

    if not os.path.exists(constants.BACK_TEST_SHAS):
        print('Generating git SHAs to back test')
        shas = generate_shas(start_date, end_date, delta_days)
        save_shas(start_date, end_date, delta_days, shas)

    with open(constants.BACK_TEST_SHAS, 'r') as f:
        (s, e, d, shas) = pickle.load(f)
        print('Found')
        print((s, e, d, shas))
        if s != start_date or e != end_date or d != delta_days:
            generate_shas(start_date, end_date, delta_days)

    with open(constants.BACK_TEST_SHAS, 'r') as f:
        (s, e, d, shas) = pickle.load(f)
        print('%d commits left to be tested' % len(shas))
        if len(shas) == 0:
            print('Back testing finished, exiting!')
            return
        sha = shas[0]
        print('Testing sha %s' % sha)
        sys.argv.append('-revision')
        sys.argv.append(sha)
        bench.main()
        shas.pop(0)
        save_shas(s, e, d, shas)


if __name__ == '__main__':
    main()
