"""Portable HTTP -> in-process queue -> database study harness.

SQLite supports local functional checks. PostgreSQL is the Linux study target.
Application body bytes are recorded; TCP packet counts and joules require
separate instruments. The HTTP acknowledgment follows the database commit.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import http.client
import platform
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import socket
import sqlite3
import struct
import threading
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

import numpy as np


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def net_counters(interface: str = 'eth0') -> dict | None:
    """Linux container interface totals; None on native macOS/Windows."""
    root = Path('/sys/class/net') / interface / 'statistics'
    try:
        return {name: int((root / name).read_text())
                for name in ('rx_bytes', 'tx_bytes', 'rx_packets', 'tx_packets')}
    except (FileNotFoundError, PermissionError):
        return None


class WireCounter:
    """Passive TCP packet/frame counters on the isolated app container eth0."""

    def __init__(self):
        self.counts = {'producer_packets': 0, 'producer_frame_bytes': 0,
                       'database_packets': 0, 'database_frame_bytes': 0}
        self.lock = threading.Lock()
        self.available = False
        try:
            self.sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
            self.sock.bind(('eth0', 0))
            self.sock.settimeout(1)
            self.available = True
            threading.Thread(target=self.run, daemon=True).start()
        except (AttributeError, OSError):
            self.available = False

    def run(self):
        while True:
            try:
                frame = self.sock.recv(65535)
            except socket.timeout:
                continue
            except OSError:
                return
            if len(frame) < 54 or frame[12:14] != b'\x08\x00':
                continue
            ip_start = 14
            if frame[ip_start + 9] != 6:
                continue
            tcp_start = ip_start + (frame[ip_start] & 15) * 4
            if len(frame) < tcp_start + 4:
                continue
            source_port, dest_port = struct.unpack('!HH', frame[tcp_start:tcp_start + 4])
            if 8765 in (source_port, dest_port):
                prefix = 'producer'
            elif 5432 in (source_port, dest_port):
                prefix = 'database'
            else:
                continue
            with self.lock:
                self.counts[f'{prefix}_packets'] += 1
                self.counts[f'{prefix}_frame_bytes'] += len(frame)

    def snapshot(self):
        if not self.available:
            return None
        with self.lock:
            return dict(self.counts)


class Store:
    def __init__(self, sqlite_path: str | None, pg_dsn: str | None):
        self.postgres = bool(pg_dsn)
        if self.postgres:
            import psycopg
            self.conn = psycopg.connect(pg_dsn)
            self.placeholder = '%s'
        else:
            if sqlite_path and sqlite_path != ':memory:':
                Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(sqlite_path or ':memory:', check_same_thread=False)
            self.conn.execute('PRAGMA journal_mode=WAL')
            self.conn.execute('PRAGMA synchronous=FULL')
            self.placeholder = '?'
        with self.transaction():
            self.conn.execute('''CREATE TABLE IF NOT EXISTS study_events (
                run_id TEXT NOT NULL, event_id TEXT NOT NULL, route_key TEXT NOT NULL,
                sequence INTEGER NOT NULL, PRIMARY KEY (run_id, event_id))''')

    def transaction(self):
        # psycopg's connection context closes the connection on exit, while
        # sqlite's context commits without closing it.
        return self.conn.transaction() if self.postgres else self.conn

    def insert(self, run_id: str, events: list[dict]) -> int:
        sql = ('INSERT INTO study_events (run_id,event_id,route_key,sequence) '
               f'VALUES ({",".join([self.placeholder] * 4)}) ON CONFLICT DO NOTHING')
        duplicates = 0
        with self.transaction():
            for event in events:
                result = self.conn.execute(sql, (run_id, event['event_id'],
                                                 event['route_key'], event['sequence']))
                duplicates += int(result.rowcount == 0)
        return duplicates

    def events(self, run_id: str) -> list[dict]:
        sql = (f'SELECT event_id,route_key,sequence FROM study_events WHERE run_id={self.placeholder} '
               'ORDER BY route_key,sequence')
        return [{'event_id': eid, 'route_key': route, 'sequence': seq}
                for eid, route, seq in self.conn.execute(sql, (run_id,)).fetchall()]


class Task:
    def __init__(self, run_id: str, events: list[dict]):
        self.run_id = run_id
        self.events = events
        self.done = threading.Event()
        self.duplicates = 0
        self.error = None
        self.enqueued_at = time.perf_counter()
        self.queue_wait_ms = None
        self.database_commit_ms = None


def serve(args) -> None:
    store = Store(args.sqlite, args.pg_dsn or os.environ.get('FM_PG_DSN'))
    wire = WireCounter()
    tasks = queue.Queue(maxsize=1024)
    stats = {'batches': 0, 'request_body_bytes': 0, 'response_body_bytes': 0,
             'duplicate_attempts': 0}
    lock = threading.Lock()

    def worker():
        while True:
            task = tasks.get()
            try:
                task.queue_wait_ms = (time.perf_counter() - task.enqueued_at) * 1000
                commit_start = time.perf_counter()
                task.duplicates = store.insert(task.run_id, task.events)
                task.database_commit_ms = (time.perf_counter() - commit_start) * 1000
            except Exception as exc:
                task.error = str(exc)
            finally:
                task.done.set()
                tasks.task_done()

    threading.Thread(target=worker, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_):
            return

        def reply(self, code: int, payload: dict):
            body = json.dumps(payload, separators=(',', ':')).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            with lock:
                stats['response_body_bytes'] += len(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == '/health':
                self.reply(200, {'ok': True, 'database': 'postgres' if store.postgres else 'sqlite'})
            elif parsed.path == '/events':
                run_id = parse_qs(parsed.query).get('run_id', [''])[0]
                self.reply(200, {'events': store.events(run_id)})
            elif parsed.path == '/stats':
                with lock:
                    snapshot = dict(stats)
                self.reply(200, snapshot)
            elif parsed.path == '/wire':
                self.reply(200, {'available': wire.available, 'counts': wire.snapshot()})
            else:
                self.reply(404, {'error': 'unknown path'})

        def do_POST(self):
            if self.path != '/batch':
                self.reply(404, {'error': 'unknown path'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                self.close_connection = True
                self.reply(400, {'error': 'invalid content length'})
                return
            if not 0 < length <= 2_000_000:
                self.reply(413, {'error': 'body length outside 1..2000000'})
                return
            body = self.rfile.read(length)
            try:
                payload = json.loads(body)
                if not isinstance(payload, dict) or not isinstance(payload.get('events'), list):
                    raise ValueError('object payload and event list required')
                run_id = str(payload['run_id'])
                events = payload['events']
                if not 0 < len(events) <= 256 or len(run_id) > 128:
                    raise ValueError('batch size or run ID invalid')
                keys = {(e['route_key'], e['tenant'], e['schema']) for e in events}
                if len(keys) != 1 or len({e['event_id'] for e in events}) != len(events):
                    raise ValueError('mixed compatibility keys or duplicate IDs in batch')
                if any(type(e['sequence']) is not int or e['sequence'] < 0 for e in events):
                    raise ValueError('sequence must be integer')
            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            task = Task(run_id, events)
            with lock:
                stats['batches'] += 1
                stats['request_body_bytes'] += len(body)
            try:
                tasks.put(task, timeout=10)
            except queue.Full:
                self.reply(503, {'error': 'queue full'})
                return
            if not task.done.wait(60):
                self.reply(504, {'error': 'database timeout'})
            elif task.error:
                self.reply(500, {'error': task.error})
            else:
                with lock:
                    stats['duplicate_attempts'] += task.duplicates
                self.reply(200, {'committed': len(events) - task.duplicates,
                                 'duplicate_attempts': task.duplicates,
                                 'queue_wait_ms': task.queue_wait_ms,
                                 'database_commit_ms': task.database_commit_ms})

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'Serving {"PostgreSQL" if store.postgres else "SQLite"} on {args.host}:{args.port}', flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def get_json(url: str) -> dict:
    with urlopen(url, timeout=60) as response:
        return json.load(response)


class BatchConnection:
    """Explicit connection reuse ablation; failures discard the old connection."""
    def __init__(self, url, transport):
        self.url = url.rstrip('/') + '/batch'
        self.parsed = urlparse(self.url)
        if self.parsed.scheme not in ('http', 'https'):
            raise ValueError('HTTP or HTTPS URL required')
        self.transport = transport
        self.connection = None

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def post(self, body):
        if self.transport == 'fresh':
            request = Request(self.url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
            with urlopen(request, timeout=65) as response:
                return response.read()
        try:
            if self.connection is None:
                cls = (http.client.HTTPSConnection if self.parsed.scheme == 'https'
                       else http.client.HTTPConnection)
                self.connection = cls(self.parsed.hostname, self.parsed.port, timeout=65)
            self.connection.request('POST', self.parsed.path, body=body,
                                    headers={'Content-Type': 'application/json'})
            response = self.connection.getresponse()
            payload = response.read()
            if response.status != 200:
                raise RuntimeError(f'HTTP {response.status}: {payload[:200]!r}')
            return payload
        except Exception:
            self.close()
            raise


def replay(args) -> None:
    with Path(args.events).open(newline='', encoding='utf-8') as stream:
        rows = [r for r in csv.DictReader(stream) if r['profile'] == args.profile]
    if not rows:
        raise ValueError(f'No replay events for {args.profile}')
    rows.sort(key=lambda r: (int(r['scheduled_offset_ms']), r['event_id']))
    if args.limit:
        rows = rows[:args.limit]
    run_id = args.run_id or f'{args.profile}-{uuid4().hex[:12]}'
    route_seq = defaultdict(int)
    pending = defaultdict(list)
    first_at = {}
    outbound = queue.Queue()
    latencies_ms = []
    errors = []
    timing = {key: [] for key in ('batch_hold_ms', 'sender_backlog_ms', 'http_attempt_ms',
                                  'queue_wait_ms', 'database_commit_ms')}
    max_outbound_batches = 0
    totals = {'request_body_bytes': 0, 'response_body_bytes': 0,
              'attempts': 0, 'batches': 0, 'duplicate_attempts': 0}
    expected = {r['event_id'] for r in rows}
    if len(expected) != len(rows):
        raise ValueError('Replay event IDs are not unique')

    def send_batches():
        client = BatchConnection(args.url, args.transport)
        while True:
            item = outbound.get()
            if item is None:
                client.close()
                outbound.task_done()
                return
            batch, queued_ns = item
            timing['sender_backlog_ms'].append((time.time_ns() - queued_ns) / 1e6)
            body = json.dumps({'run_id': run_id, 'events': batch}, separators=(',', ':')).encode()
            totals['batches'] += 1
            for attempt in range(3):
                totals['attempts'] += 1
                totals['request_body_bytes'] += len(body)
                try:
                    attempt_start = time.perf_counter()
                    reply_body = client.post(body)
                    totals['response_body_bytes'] += len(reply_body)
                    timing['http_attempt_ms'].append((time.perf_counter() - attempt_start) * 1000)
                    reply = json.loads(reply_body)
                    for key in ('queue_wait_ms', 'database_commit_ms'):
                        if reply.get(key) is not None:
                            timing[key].append(reply[key])
                    totals['duplicate_attempts'] += reply['duplicate_attempts']
                    acknowledged_ns = time.time_ns()
                    latencies_ms.extend((acknowledged_ns - e['emitted_ns']) / 1e6 for e in batch)
                    break
                except Exception as exc:
                    if attempt == 2:
                        errors.append(str(exc))
                    else:
                        time.sleep(.05 * 2**attempt)
            outbound.task_done()

    sender = threading.Thread(target=send_batches, daemon=True)
    sender.start()
    started_utc = utc_now()
    wire_start = get_json(args.url.rstrip('/') + '/wire')
    network_start = net_counters()
    start = time.monotonic()
    cpu_start = time.process_time()
    schedule_lag_ms = []
    max_wait = args.max_wait_ms / 1000

    def flush(route):
        nonlocal max_outbound_batches
        if pending[route]:
            queued_ns = time.time_ns()
            timing['batch_hold_ms'].extend((queued_ns - e['emitted_ns']) / 1e6 for e in pending[route])
            outbound.put((pending[route], queued_ns))
            max_outbound_batches = max(max_outbound_batches, outbound.qsize())
            pending[route] = []
            first_at.pop(route, None)

    for row in rows:
        target = start + int(row['scheduled_offset_ms']) / (1000 * args.speedup)
        while True:
            now = time.monotonic()
            due = min((t + max_wait for t in first_at.values()), default=float('inf'))
            if due <= now:
                for route in list(first_at):
                    if first_at[route] + max_wait <= now:
                        flush(route)
                continue
            if target <= now:
                break
            time.sleep(min(target, due) - now)
        route = row['route_key']
        sequence = route_seq[route]
        route_seq[route] += 1
        event = {'event_id': row['event_id'], 'route_key': route, 'tenant': 'study',
                 'schema': 'v1', 'sequence': sequence, 'emitted_ns': time.time_ns()}
        schedule_lag_ms.append(max(0, (time.monotonic() - target) * 1000))
        if not pending[route]:
            first_at[route] = time.monotonic()
        pending[route].append(event)
        if len(pending[route]) >= args.max_count or max_wait == 0:
            flush(route)
    while first_at:
        now = time.monotonic()
        due = min(t + max_wait for t in first_at.values())
        if due > now:
            time.sleep(due - now)
        for route in list(first_at):
            if first_at[route] + max_wait <= time.monotonic():
                flush(route)
    outbound.put(None)
    outbound.join()
    sender.join()
    network_end = net_counters()
    wire_end = get_json(args.url.rstrip('/') + '/wire')
    cpu_seconds = time.process_time() - cpu_start
    persisted = get_json(args.url.rstrip('/') + f'/events?run_id={run_id}')['events']
    stored_ids = [e['event_id'] for e in persisted]
    lost = len(expected - set(stored_ids))
    extra = len(set(stored_ids) - expected)
    duplicate_completions = len(stored_ids) - len(set(stored_ids))
    elapsed = time.monotonic() - start
    output = {'run_id': run_id, 'configuration': f'count={args.max_count},wait_ms={args.max_wait_ms}',
              'profile': args.profile, 'speedup': args.speedup, 'database': get_json(args.url.rstrip('/') + '/health')['database'],
              'machine': args.machine, 'transport': args.transport,
              'runtime': {'python': platform.python_version(), 'platform': platform.platform(),
                          'numpy': np.__version__},
              'event_limit': args.limit, 'started_utc': started_utc, 'ended_utc': utc_now(),
              'expected_tasks': len(rows), 'successful_tasks': len(stored_ids) - extra,
              'lost': lost, 'extra': extra, 'duplicate_completions': duplicate_completions,
              'duplicate_attempts': totals['duplicate_attempts'], 'send_errors': errors,
              'p50_latency_ms': float(np.quantile(latencies_ms, .5)) if latencies_ms else None,
              'p95_latency_ms': float(np.quantile(latencies_ms, .95)) if latencies_ms else None,
              'p99_latency_ms': float(np.quantile(latencies_ms, .99)) if latencies_ms else None,
              'timing_ms': {key: {'count': len(values),
                                  'p50': float(np.quantile(values, .5)) if values else None,
                                  'p95': float(np.quantile(values, .95)) if values else None,
                                  'max': max(values) if values else None}
                            for key, values in timing.items()},
              'max_outbound_batches': max_outbound_batches,
              'p95_schedule_lag_ms': float(np.quantile(schedule_lag_ms, .95)),
              'elapsed_s': elapsed, 'throughput_tasks_s': len(stored_ids) / elapsed,
              'producer_cpu_s': cpu_seconds, 'request_body_bytes': totals['request_body_bytes'],
              'response_body_bytes': totals['response_body_bytes'], 'application_batches': totals['batches'],
              'http_attempts': totals['attempts'], 'energy_j': None,
              'energy_boundary': 'unmeasured',
              'producer_interface': 'eth0' if network_start and network_end else None,
              'producer_interface_delta': ({key: network_end[key] - network_start[key] for key in network_start}
                                           if network_start and network_end else None),
              'producer_interface_scope': 'runner container interface, includes DNS and transport overhead; excludes verification request',
              'wire_capture_available': bool(wire_start['available'] and wire_end['available']),
              'wire_counter_delta': ({key: wire_end['counts'][key] - wire_start['counts'][key]
                                      for key in wire_start['counts']}
                                     if wire_start['available'] and wire_end['available'] else None),
              'wire_counter_scope': 'TCP Ethernet frames on isolated app eth0, classified by service port; includes control request overhead',
              'replay_sha256': hashlib.sha256(Path(args.events).read_bytes()).hexdigest(),
              'route_contract': 'homogeneous route_key,tenant,schema per batch; sequential per route; ACK after DB commit'}
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / f'{run_id}.json'
    path.write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(output, indent=2))
    if lost or extra or duplicate_completions or errors:
        raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    server = sub.add_parser('serve')
    server.add_argument('--host', default='127.0.0.1')
    server.add_argument('--port', type=int, default=8765)
    server.add_argument('--sqlite', default=':memory:')
    server.add_argument('--pg-dsn')
    client = sub.add_parser('replay')
    client.add_argument('--transport', choices=['fresh', 'persistent'], default='fresh')
    client.add_argument('--events', default='analysis/results/replay/replay_events.csv')
    client.add_argument('--profile', required=True)
    client.add_argument('--url', default='http://127.0.0.1:8765')
    client.add_argument('--max-count', type=int, required=True)
    client.add_argument('--max-wait-ms', type=int, required=True)
    client.add_argument('--speedup', type=float, default=60)
    client.add_argument('--limit', type=int)
    client.add_argument('--run-id')
    client.add_argument('--machine', default='local')
    client.add_argument('--output', type=Path, default=Path('analysis/results/experimental_runs'))
    args = parser.parse_args()
    if args.command == 'serve':
        serve(args)
    else:
        if args.max_count < 1 or args.max_count > 256 or args.max_wait_ms < 0 or args.speedup <= 0:
            parser.error('invalid batching or speedup settings')
        replay(args)


if __name__ == '__main__':
    main()
