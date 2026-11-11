"""Exercise HTTP validation, ACK-after-commit and retry idempotency."""
import json
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest


@pytest.fixture
def server(tmp_path, request):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    command = [sys.executable, '-m', 'experiment.harness', 'serve',
        '--sqlite', str(tmp_path / 'nested' / 'study.sqlite'), '--port', str(port)]
    mode = getattr(request, 'param', None)
    if mode:
        setup = ("h.Store.insert = lambda *a: (_ for _ in ()).throw(RuntimeError('injected commit failure'))"
                 if mode == 'commit_failure' else
                 "h.queue.Queue.put = lambda *a, **k: (_ for _ in ()).throw(h.queue.Full())")
        code = 'import sys; from experiment import harness as h; ' + setup + '; sys.argv = ' + repr(['harness'] + command[3:]) + '; h.main()'
        command = [sys.executable, '-c', code]
    process = subprocess.Popen(command,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                with urlopen(url + '/health', timeout=.2) as response:
                    assert json.load(response)['ok']
                break
            except (URLError, TimeoutError):
                if process.poll() is not None:
                    pytest.fail(process.stderr.read().decode())
                time.sleep(.05)
        else:
            pytest.fail('Server did not become ready')
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)
        process.stderr.close()


def post(url, events):
    request = Request(url + '/batch', data=json.dumps({'run_id': 'test', 'events': events}).encode(),
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def event(eid='a', route='route', sequence=0):
    return dict(event_id=eid, route_key=route, tenant='study', schema='v1', sequence=sequence)


def test_ack_is_persisted_and_retry_is_idempotent(server):
    events = [event(), event('b', sequence=1)]
    result = post(server, events)
    assert result['committed'] == 2
    assert result['database_commit_ms'] >= 0
    assert result['queue_wait_ms'] >= 0
    with urlopen(server + '/events?run_id=test') as response:
        stored = json.load(response)['events']
    assert [row['event_id'] for row in stored] == ['a', 'b']
    assert [row['sequence'] for row in stored] == [0, 1]
    assert post(server, events)['duplicate_attempts'] == 2
    with urlopen(server + '/events?run_id=test') as response:
        assert len(json.load(response)['events']) == 2


@pytest.mark.parametrize('events', [[], [event(), event('b', route='other')],
    [event(), event()], [event(sequence=True)], [event(sequence=-1)], 'invalid'])
def test_rejected_batch_does_not_commit(server, events):
    with pytest.raises(HTTPError) as exc:
        post(server, events)
    assert exc.value.code == 400
    with urlopen(server + '/events?run_id=test') as response:
        assert json.load(response)['events'] == []


def test_persistent_connection_commits_and_retries(server):
    from experiment.harness import BatchConnection
    client = BatchConnection(server, 'persistent')
    body = json.dumps({'run_id': 'test', 'events': [event()]}).encode()
    try:
        assert json.loads(client.post(body))['committed'] == 1
        assert json.loads(client.post(body))['duplicate_attempts'] == 1
    finally:
        client.close()


@pytest.mark.parametrize('server,code', [('commit_failure', 500), ('queue_full', 503)], indirect=['server'])
def test_server_failure_never_acknowledges_commit(server, code):
    with pytest.raises(HTTPError) as exc:
        post(server, [event()])
    assert exc.value.code == code
    with urlopen(server + '/events?run_id=test') as response:
        assert json.load(response)['events'] == []
