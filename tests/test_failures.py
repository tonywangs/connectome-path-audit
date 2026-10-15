from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from connectome_audit import cli
from connectome_audit.core import AuditError, Budget, LimitError, Limits, analyze
from connectome_audit.ingest import load_graph, provenance_from_bytes
from connectome_audit.report import canonical_json, html_report, write_bundle
from test_core import Fixtures, ROOT


class InputFailures(Fixtures):
    def test_malformed_connections(self):
        cases = [b'', b'source,target,count\na,b,1\n', b'source,target,synapses\na,b\n',
                 b'source,target,synapses\na,b,1,x\n', b'source,target,synapses\n\n',
                 b'source,target,synapses\n"a,b,1\n', b'source,target,synapses\n\xff,b,1\n']
        for id_value in ['', ' a', 'a ', 'a\x00', 'a\u202e', 'x' * 257]:
            cases.append(f'source,target,synapses\n{id_value},b,1\n'.encode())
        for count in ['0', '-1', '1.0', '1e2', '+1', ' 1', '01', 'nan', '９', '9007199254740992', '9' * 500]:
            cases.append(f'source,target,synapses\na,b,{count}\n'.encode())
        for content in cases:
            with self.subTest(content=content[:100]), self.assertRaises(AuditError):
                self.connections.write_bytes(content); self.load()
        self.connections.write_text('source,target,synapses\na,b,9007199254740991\na,b,1\n')
        with self.assertRaises(AuditError): self.load()

    def test_malformed_nodes(self):
        for text in ['node_id,label\na,x\na,y\n', 'node_id,label\na,' + 'x' * 513,
                     'node_id,label\na,"line\nbreak"\n', 'node_id,name\na,x\n']:
            with self.subTest(text=text[:100]), self.assertRaises(AuditError):
                self.nodes.write_text(text); self.load()

    def test_malformed_provenance(self):
        original = json.loads(self.provenance.read_text())
        for value in [[], {}, {'schema': 'no'}, {**original, 'extra': 1}, {**original, 'kind': 'real'},
                      {**original, 'limitations': []}, {**original, 'dataset': 7},
                      {**original, 'limitations': ['']}, {**original, 'kind': []}]:
            with self.subTest(value=value), self.assertRaises(AuditError):
                provenance_from_bytes(json.dumps(value).encode())
        for value in [b'{"schema": 1,"schema": 2}', b'{', b'\xff', b'[' * 1500]:
            with self.assertRaises(AuditError): provenance_from_bytes(value)

    def test_bom_crlf_and_hash_exact_bytes(self):
        raw = b'\xef\xbb\xbfsource,target,synapses\r\na,b,5\r\n'
        self.connections.write_bytes(raw)
        graph, _ = self.load()
        self.assertEqual(graph.inputs['connections'], {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
        self.assertEqual(graph.edges['a', 'b'], 5)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO test')
    def test_fifo_rejected_without_waiting(self):
        self.connections.unlink(); os.mkfifo(self.connections)
        start = time.monotonic()
        with self.assertRaises(AuditError): self.load()
        self.assertLess(time.monotonic() - start, 1)

    def test_input_limits(self):
        for limits in [{'input_bytes': 10}, {'nodes': 2}, {'edges': 1}, {'rows': 1}, {'operations': 1}]:
            with self.subTest(limits=limits), self.assertRaises(LimitError): self.load(**limits)

    def test_computation_runtime_witness_and_limit_validation(self):
        graph, _ = self.load()
        with self.assertRaises(LimitError):
            analyze(graph, ['a'], ['c'], [1], Budget(replace(Limits(), operations=1)))
        with self.assertRaises(LimitError):
            analyze(graph, ['a'], ['c'], [1], Budget(replace(Limits(), witness_nodes=2)))
        clock = iter([0, 1])
        budget = Budget(replace(Limits(), seconds=.5), clock=lambda: next(clock))
        with self.assertRaises(LimitError): budget.check()
        for changes in [{'seconds': float('nan')}, {'seconds': float('inf')}, {'nodes': 0},
                        {'queries': -1}, {'edges': 100001}, {'rows': 1.5}, {'operations': True}]:
            with self.subTest(changes=changes), self.assertRaises(AuditError): Budget(replace(Limits(), **changes))


class OutputFailures(Fixtures):
    def args(self, output=None):
        return [str(self.connections), '--nodes', str(self.nodes), '--provenance', str(self.provenance),
                '--source', 'a', '--target', 'c', '--thresholds', '1,5,6', '--output', str(output or self.root / 'out')]

    def test_cli_success_repeat_and_collision(self):
        self.assertEqual(cli.main(self.args()), 0)
        output = self.root / 'out'
        before = {p.name: p.read_bytes() for p in output.iterdir()}
        self.assertEqual(cli.main(self.args()), 2)
        self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})
        self.assertEqual(cli.main(self.args(self.root / 'second')), 0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / 'second').iterdir()})
        manifest = json.loads(before['COMPLETE.json'])
        for name, info in manifest['artifacts'].items():
            self.assertEqual(hashlib.sha256(before[name]).hexdigest(), info['sha256'])
        empty = self.root / 'empty'; empty.mkdir()
        self.assertEqual(cli.main(self.args(empty)), 2); self.assertEqual(list(empty.iterdir()), [])
        link = self.root / 'link'; link.symlink_to(self.connections)
        original = self.connections.read_bytes()
        self.assertEqual(cli.main(self.args(link)), 2); self.assertEqual(self.connections.read_bytes(), original)

    def test_serialization_failure_does_not_create_output(self):
        for target in ['connectome_audit.cli.canonical_json', 'connectome_audit.cli.html_report']:
            with patch(target, side_effect=ValueError('injected serialization failure')):
                self.assertEqual(cli.main(self.args()), 2)
            self.assertFalse((self.root / 'out').exists())
        with self.assertRaises(ValueError): canonical_json({'x': float('nan')}, Budget(Limits()))
        with self.assertRaises(TypeError): canonical_json({'x': object()}, Budget(Limits()))

    def test_cleanup_write_failure_and_cancellation(self):
        for error in [OSError('injected disk failure'), KeyboardInterrupt(), LimitError('timeout')]:
            for fail_at in [1, 2, 3]:
                counter = 0
                def fail(fd):
                    nonlocal counter
                    counter += 1
                    if counter == fail_at: raise error
                with self.subTest(error=error, fail_at=fail_at), patch('connectome_audit.report.os.fsync', side_effect=fail):
                    self.assertEqual(cli.main(self.args()), 130 if isinstance(error, KeyboardInterrupt) else 2)
                self.assertFalse((self.root / 'out').exists())

    def test_exhausted_report_and_runtime(self):
        self.assertEqual(cli.main(self.args() + ['--max-report-bytes', '100']), 2)
        self.assertFalse((self.root / 'out').exists())
        with self.assertRaises(LimitError): html_report(b'{}', Budget(replace(Limits(), report_bytes=100)))
        if hasattr(signal, 'setitimer'):
            def delay(*args): time.sleep(.2)
            with patch('connectome_audit.cli.load_graph', side_effect=delay):
                start = time.monotonic()
                self.assertEqual(cli.main(self.args() + ['--max-seconds', '.02']), 2)
                self.assertLess(time.monotonic() - start, .15)
        self.assertFalse((self.root / 'out').exists())

    def test_actual_sigint_and_sigterm_cleanup(self):
        # Pause at first fsync after output creation; real process signals must
        # unwind the writer and remove the incomplete directory.
        code = '''import time, sys
from connectome_audit import cli, report
def pause(fd):
 print("READY", flush=True)
 time.sleep(20)
report.os.fsync = pause
raise SystemExit(cli.main(sys.argv[1:]))
'''
        for sig in [signal.SIGINT, signal.SIGTERM]:
            proc = subprocess.Popen([sys.executable, '-c', code, *self.args()], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                import selectors
                with selectors.DefaultSelector() as selector:
                    selector.register(proc.stdout, selectors.EVENT_READ)
                    self.assertTrue(selector.select(timeout=5), 'child readiness timed out')
                self.assertEqual(proc.stdout.readline().strip(), 'READY')
                proc.send_signal(sig)
                _, stderr = proc.communicate(timeout=5)
                self.assertEqual(proc.returncode, 130, stderr)
                self.assertIn('INCOMPLETE', stderr)
                self.assertFalse((self.root / 'out').exists())
            finally:
                if proc.poll() is None: proc.kill(); proc.wait()

    def test_hostile_text_cannot_end_data_block(self):
        raw = canonical_json({'label': '</script><img src="https://invalid/" onerror="alert(1)"> & @@SCRIPT@@ \\u003c'}, Budget(Limits()))
        self.assertNotIn(b'<', raw)
        html = html_report(raw, Budget(Limits()))
        self.assertEqual(html.count(b'<script'), 2)
        self.assertIn(b'\\u003c/script', html)
        self.assertNotIn(b'<img', html)
