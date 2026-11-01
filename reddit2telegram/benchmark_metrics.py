"""Opt-in, payload-free measurements for the live language experiment.

All implementations use the event contract in implementations/benchmarks.
Without an active measurement window these functions do no I/O on requests.
"""

from collections import Counter
from contextvars import ContextVar
import json
import hashlib
import logging
import os
from pathlib import Path
import time


CONTROL = Path(__file__).resolve().parent.parent / 'implementations/benchmarks/state/active.json'
_JOB = ContextVar('benchmark_job', default=None)


def active_run():
    try:
        run = json.loads(CONTROL.read_text())
        now = time.time()
        if run['started_at'] <= now < run['deadline']:
            return run
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def emit(run, event, **fields):
    if run is None or not run['started_at'] <= time.time() < run['deadline']:
        return
    record = dict(schema=1, run_id=run['run_id'], event=event, ts=time.time(), **fields)
    # One O_APPEND write per line; workers never log credentials, URLs or content.
    data = (json.dumps(record, separators=(',', ':')) + '\n').encode()
    try:
        fd = os.open(run['events_path'], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            if os.write(fd, data) != len(data):
                logging.error('Incomplete benchmark event write')
        finally:
            os.close(fd)
    except OSError:
        logging.exception('Could not write benchmark event')


def begin_job(task_id, module, created_at=None):
    run = active_run()
    if run is None:
        return None
    state = dict(run=run, task_id=str(task_id), module=module,
                 started=time.monotonic(), counters=Counter())
    token = _JOB.set(state)
    wait = max(0, time.time() - created_at) if created_at is not None else None
    state['queue_wait_seconds'] = wait
    emit(run, 'job_start', task_id=state['task_id'], module=module,
         queue_wait_seconds=wait)
    return token


def finish_job(token, status, error_type=None):
    state = _JOB.get()
    if token is None or state is None:
        return
    try:
        emit(state['run'], 'job_end', task_id=state['task_id'], module=state['module'],
             status=status, error_type=error_type,
             duration_seconds=time.monotonic() - state['started'],
             queue_wait_seconds=state['queue_wait_seconds'], counters=dict(state['counters']))
    finally:
        _JOB.reset(token)


def count(key, amount=1):
    state = _JOB.get()
    if state is not None:
        state['counters'][key] += amount


def measuring():
    return _JOB.get() is not None


def request_status(prefix, status):
    count(prefix + '_requests')
    if status == 429:
        count(prefix + '_rate_limits')
    if status >= 400:
        count(prefix + '_http_errors')


async def telegram_request(request):
    if not measuring():
        return
    # httpx consumes this stream itself; preserve streaming and backpressure.
    import httpx

    class MeasuredStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            async for chunk in original:
                count('telegram_request_body_bytes', len(chunk))
                yield chunk

        async def aclose(self):
            await original.aclose()

    original = request.stream
    request.stream = MeasuredStream()
    count('telegram_request_attempts')


async def telegram_response(response):
    request_status('telegram', response.status_code)


def delivery(result):
    if not measuring():
        return
    from telegram import Message

    for message in result if isinstance(result, (tuple, list)) else [result]:
        if not isinstance(message, Message):
            continue
        count('telegram_messages')
        if message.video:
            kind = 'video'
        elif message.animation:
            kind = 'animation'
        elif message.photo:
            kind = 'photo'
        elif message.document:
            kind = 'document'
        elif message.audio:
            kind = 'audio'
        else:
            kind = 'text_or_other'
        count('telegram_messages_' + kind)


def post_record(channel, url, sent):
    state = _JOB.get()
    if state is None:
        return
    count('posts_recorded_sent' if sent else 'candidates_rejected')
    if sent:
        # Compare observed repeated deliveries without persisting source URLs.
        key = hashlib.sha256((channel.lower() + '\0' + url.lower()).encode()).hexdigest()
        emit(state['run'], 'post_record', task_id=state['task_id'], post_key=key)
