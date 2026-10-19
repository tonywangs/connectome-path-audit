import json
import unittest
from connectome_audit.core import AuditError, Budget, Limits
from connectome_audit.explorer import make_explorer, render
from connectome_audit.ingest import Graph


class ExplorerTests(unittest.TestCase):
    def graph(self):
        return Graph({'a': '</script><img src=x onerror=alert(1)>@@SCRIPT@@', 'b': 'B'},
                     {('a', 'b'): 3}, 1, 0, 0, {}, {})

    def test_embedded_untrusted_labels_cannot_close_data_script(self):
        graph = self.graph()
        doc = make_explorer(graph, 'a', 'b')
        raw, html = render(doc, Budget(Limits()))
        self.assertEqual(json.loads(raw)['nodes'][0]['label'], graph.nodes['a'])
        self.assertNotIn(b'</script><img', html)
        self.assertIn(b'\\u003c/script\\u003e', html)
        self.assertEqual(html.count(b'<script'), 2)
        self.assertIn(b'@@SCRIPT@@', html)  # Never expand a token inside user data.

    def test_rejects_missing_endpoint_and_browser_limits(self):
        graph = self.graph()
        with self.assertRaises(AuditError): make_explorer(graph, 'absent', 'b')
        graph.nodes = {str(i): '' for i in range(2001)}
        with self.assertRaises(AuditError): make_explorer(graph, '0', '1')
        graph.nodes = {'a': '', 'b': ''}
        graph.edges = {(str(i), 'b'): 1 for i in range(50001)}
        with self.assertRaises(AuditError): make_explorer(graph, 'a', 'b')


if __name__ == '__main__': unittest.main()
