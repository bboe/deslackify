import argparse
import logging
import os
import sys
import time
from datetime import date, datetime

import slacker
from requests import HTTPError, ReadTimeout, Session


__version__ = '0.1.0'


logging.basicConfig(
    format='%(asctime)-15s %(message)s',
    level=logging.INFO)


def delete_message(slack, message, update_first=False):
    date_string = datetime.utcfromtimestamp(
        int(message['ts'].split('.', 1)[0])).strftime('%Y-%m-%d %H:%M:%S')
    logging.info('{} {}'.format(date_string, message['text']))

    if update_first:
        handle_rate_limit(
            slack.chat.update, as_user=True, channel=message['channel']['id'],
            text='-', ts=message['ts'])
    handle_rate_limit(slack.chat.delete, as_user=True,
                      channel=message['channel']['id'], ts=message['ts'])


def handle_rate_limit(method, *args, **kwargs):
    count = 5
    while count > 0:
        try:
            response = method(*args, **kwargs)
            assert response.successful
            assert response.body['ok']
            return response
        except HTTPError as exception:
            if exception.response.status_code == 429:
                retry_time = int(exception.response.headers['retry-after'])
                retry_time = min(3, retry_time)
                if retry_time > 3:
                    logging.info('Sleeping for {} seconds'
                                 .format(retry_time))
                time.sleep(retry_time)
            else:
                raise
        except ReadTimeout:
            logging.info('Read timeout. Sleeping for 16 seconds')
            time.sleep(16)
        count -= 1


def main():
    datetime = date.today()
    try:
        datetime = datetime.replace(year=datetime.year - 1)
    except ValueError:
        datetime = datetime.replace(year=datetime.year - 1,
                                    day=datetime.day - 1)
    default_before = datetime.strftime('%Y-%m-%d')

    parser = argparse.ArgumentParser(
        description='Delete slack messages by specified user',
        usage='%(prog)s [options] user')
    parser.add_argument('user', help='Delete messages from this user')
    parser.add_argument('--token', help=(
        'The token used to connect to slack. This value can also be passed via'
        'the SLACK_TOKEN environment variable.'))
    parser.add_argument(
        '--before', default=default_before,
        help='Date to delete messages prior to (default: %(default)s)')
    parser.add_argument(
        '--update', action='store_true',
        help='Update message to `-` prior to deleting (default: False)')
    parser.add_argument('--version', action='version',
                        version=f'%(prog)s {__version__}')
    args = parser.parse_args()

    token = args.token or os.getenv('SLACK_TOKEN')
    if not token:
        sys.stderr.write('Either the argument --token or the environment '
                         'variable SLACK_TOKEN must be provided\n')
        return 1

    with Session() as session:
        slack = slacker.Slacker(token, session=session)
        return run(slack, args)


def run(slack, args):
    deleted = 0
    not_found = 0

    try:
        for message in search_messages(slack, args.user, before=args.before):
            try:
                delete_message(slack, message, args.update)
            except slacker.Error as exception:
                if exception.args[0] == 'message_not_found':
                    print('---not found')
                    not_found += 1
                    continue
                raise
            deleted += 1
    except KeyboardInterrupt:
        pass

    logging.info('Messages deleted: {}'.format(deleted))
    if not_found:
        logging.info('Messages not found: {}'.format(not_found))
    return 0


def search_messages(slack, user, before=None):
    query = 'from:{}'.format(user)
    if before:
        query += ' before:{}'.format(before)

    # Determine the number of pages
    search_params = {'count': 100, 'query': query, 'sort': 'timestamp',
                     'sort_dir': 'desc'}
    response = handle_rate_limit(slack.search.messages, page=1,
                                 **search_params)
    search_result = response.body['messages']
    page = search_result['paging']['pages']
    logging.info('Found {} items'
                 .format(search_result['total']))

    while page > 0:
        response = handle_rate_limit(slack.search.messages, page=page,
                                     **search_params)
        search_result = response.body['messages']

        for message in sorted(search_result['matches'], key=lambda x: x['ts']):
            yield message
        page -= 1
