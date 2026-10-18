"""Exercise generated local HTML with real Chromium, all network requests blocked."""
import hashlib
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def check(report_path, screenshot=None):
    started = time.monotonic()
    report_path = Path(report_path).resolve()
    raw = report_path.with_suffix('.json').read_bytes()
    data = json.loads(raw)
    requests, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context(accept_downloads=True, offline=True, viewport={'width': 1280, 'height': 960})
        def route_handler(route):
            if route.request.url.startswith(('http:', 'https:', 'ws:', 'wss:')):
                requests.append(route.request.url); route.abort()
            else: route.continue_()
        context.route('**/*', route_handler)
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: requests.append(r.url) if r.url.startswith(('http:', 'https:')) else None)
        page.goto(report_path.as_uri())
        page.locator('#load-status').wait_for(state='hidden')
        assert page.locator('#kind').inner_text() == 'SYNTHETIC DATA'
        assert page.locator('#summary tbody tr').count() == len(data['thresholds'])
        assert page.locator('#pairs tbody tr').count() <= 20
        # Walk every findings page, collect every explicit inspect control.
        seen = set()
        while True:
            for label in page.locator('#pairs button').evaluate_all('(buttons) => buttons.map(b => b.getAttribute("aria-label"))'):
                seen.add(label)
            if page.locator('#next-page').is_disabled(): break
            page.locator('#next-page').click()
        assert len(seen) == len(data['queries']), (len(seen), len(data['queries']))
        page.locator('#previous-page').click()
        # Source/target label filter including hostile markup, never interpreted.
        page.locator('#filter').fill('Hostile')
        assert '1 of ' in page.locator('#filter-count').inner_text()
        assert page.locator('img').count() == 0
        assert page.evaluate('window.pwned') is None
        assert '</script>' in page.locator('#pairs').inner_text()
        page.locator('#pairs button').click()
        assert page.locator('#path-heading').evaluate('(e) => e === document.activeElement')
        page.locator('#filter').fill('not-a-real-label')
        assert 'No matching queries' in page.locator('#pairs').inner_text()
        assert 'No query selected' == page.locator('#selected-pair').inner_text()
        # Long path edge pagination: all 64 witness hops are reachable, <=20 mounted.
        page.locator('#filter').fill('End of chain')
        page.locator('#threshold').select_option('1')
        page.locator('#pairs button').click()
        edges = []
        while True:
            assert page.locator('#path tbody tr').count() <= 20
            edges.extend(page.locator('#path tbody tr td:first-child').all_text_contents())
            if page.locator('#next-hop').is_disabled(): break
            page.locator('#next-hop').click()
        assert edges == [str(i) for i in range(1, 65)]
        page.locator('#previous-hop').click()
        failure_checks = {}
        if data.get('single_edge_failure'):
            assert not page.locator('#failure-section').is_hidden()
            visited = []
            while True:
                assert page.locator('#removals tbody tr').count() <= 20
                visited += page.locator('#removals button').evaluate_all('(bs) => bs.map(b => b.getAttribute("aria-label"))')
                if page.locator('#next-removal').is_disabled(): break
                page.locator('#next-removal').click()
            assert len(visited) == 64
            page.locator('#removals button').first.click()
            assert 'complete search exhausted' in page.locator('#alternative-status').inner_text()
            while not page.locator('#previous-removal').is_disabled(): page.locator('#previous-removal').click()
            page.locator('#removals button').first.focus(); page.keyboard.press('Enter')
            assert page.locator('#alternative-heading').evaluate('(e) => e === document.activeElement')
            assert 'verified alternative' in page.locator('#alternative-status').inner_text()
            alt = []
            while True:
                assert page.locator('#alternative tbody tr').count() <= 20
                alt += page.locator('#alternative tbody tr td:first-child').all_text_contents()
                if page.locator('#next-alternative').is_disabled(): break
                page.locator('#next-alternative').click()
            assert alt == [str(i) for i in range(1, 90)]
            page.locator('#previous-alternative').click()
            failure_checks = {'candidate_rows_visited': len(visited), 'alternative_edges_visited': len(alt),
                              'dom_elements': page.locator('*').count()}
        node_checks = {}
        if data.get('single_node_failure'):
            assert not page.locator('#node-failure-section').is_hidden()
            visited = []
            while True:
                assert page.locator('#node-removals tbody tr').count() <= 20
                visited += page.locator('#node-removals button').evaluate_all('(bs) => bs.map(b => b.getAttribute("aria-label"))')
                if page.locator('#node-next-removal').is_disabled(): break
                page.locator('#node-next-removal').click()
            assert len(visited) == 63
            page.locator('#node-removals button').first.click()
            assert 'complete search exhausted' in page.locator('#node-alternative-status').inner_text()
            while not page.locator('#node-previous-removal').is_disabled(): page.locator('#node-previous-removal').click()
            page.locator('#node-removals button').first.focus(); page.keyboard.press('Enter')
            assert page.locator('#node-alternative-heading').evaluate('(e) => e === document.activeElement')
            assert 'verified alternative' in page.locator('#node-alternative-status').inner_text()
            assert '</script>' in page.locator('#node-removals').inner_text()
            assert '</script>' in page.locator('#node-alternative').inner_text()
            assert page.locator('img').count() == 0 and page.evaluate('window.pwned') is None
            alt = []
            while True:
                assert page.locator('#node-alternative tbody tr').count() <= 20
                alt += page.locator('#node-alternative tbody tr td:first-child').all_text_contents()
                if page.locator('#node-next-alternative').is_disabled(): break
                page.locator('#node-next-alternative').click()
            assert alt == [str(i) for i in range(1, 89)]
            page.locator('#node-previous-alternative').click()
            node_checks = {'candidate_rows_visited': len(visited), 'alternative_edges_visited': len(alt),
                              'dom_elements': page.locator('*').count()}
        # Threshold can be changed by overview and keyboard-operated select.
        page.get_by_role('button', name='Select threshold 6', exact=True).click()
        assert page.locator('#threshold').input_value() == '6'
        assert 'No path in the supplied graph' in page.locator('#path-status').inner_text()
        assert page.locator('#witness').is_hidden()
        if data.get('single_edge_failure'):
            assert 'Initially unreachable' in page.locator('#failure-status').inner_text()
        if data.get('single_node_failure'):
            assert 'Initially unreachable' in page.locator('#node-failure-status').inner_text()
        page.locator('#threshold').focus(); page.keyboard.press('Home'); page.keyboard.press('Enter')
        assert page.locator('#threshold').input_value() == '1'
        # Filter status separates missing identifiers from no supplied-graph path.
        page.locator('#filter').fill('')
        page.locator('#status').select_option('missing_node')
        assert '1 of ' in page.locator('#filter-count').inner_text()
        assert 'Unresolved' in page.locator('#path-status').inner_text()
        page.locator('#status').select_option('no_path_in_supplied_graph')
        assert 'No path in supplied graph' in page.locator('#pairs').inner_text()
        page.locator('#status').select_option('reachable')
        # Native keyboard button activation and query navigation across page boundary.
        page.locator('#next-query').focus(); before = page.locator('#selected-pair').inner_text()
        page.keyboard.press('Enter'); assert page.locator('#selected-pair').inner_text() != before
        page.locator('#previous-query').click(); assert page.locator('#selected-pair').inner_text() == before
        for _ in range(23): page.locator('#next-query').click()
        assert 'Page 2' in page.locator('#page-label').inner_text()
        assert page.locator('#pairs tbody tr').count() <= 20
        # Download must preserve exact bytes even literal backslash-u sequences.
        with page.expect_download() as info: page.locator('#download').click()
        download = info.value
        assert download.suggested_filename == 'connectome-audit.json'
        assert Path(download.path()).read_bytes() == raw
        # Small screens: document does not overflow; tables have their own scrollers.
        page.set_viewport_size({'width': 360, 'height': 800})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'page overflow'
        page.locator('#filter').fill('Hostile')
        page.locator('#pairs button').click()
        assert page.locator('#pairs tbody tr').count() == 1
        # All actionable controls remain reachable through native focus navigation.
        page.keyboard.press('Tab')
        assert page.evaluate('document.activeElement.tagName') != 'BODY'
        if screenshot:
            page.set_viewport_size({'width': 1280, 'height': 960})
            page.locator('#filter').fill('End of chain')
            page.screenshot(path=str(screenshot), full_page=True)
        assert not requests, requests
        assert not errors, errors
        result = {'elapsed_seconds': round(time.monotonic() - started, 6), 'browser': browser.version, 'single_edge_failure': failure_checks, 'single_node_failure': node_checks, 'dom_elements': page.locator('*').count(), 'external_request_attempts': len(requests),
                  'javascript_errors': len(errors), 'queries_visited': len(seen),
                  'path_edges_visited': len(edges), 'max_mounted_rows_per_paged_table': 20,
                  'viewports': ['1280x960', '360x800'], 'download_sha256': hashlib.sha256(raw).hexdigest(),
                  'checks': ['threshold select and summary buttons', 'all query pages', 'query navigation',
                             'all witness edge pages', 'ID and label filtering', 'status filtering',
                             'native keyboard controls', 'focus after inspection', 'narrow viewport',
                             'hostile labels inert', 'byte-identical JSON download', 'zero external requests']}
        browser.close()
        return result


if __name__ == '__main__':
    import sys
    print(json.dumps(check(sys.argv[1]), indent=2))


def check_partial(report_path, kind="edge"):
    """Partial outcomes remain visible in a network-blocked browser."""
    prefix = "node-" if kind == "node" else ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context(offline=True)
        requests, errors = [], []
        context.route('**/*', lambda route: route.abort() if route.request.url.startswith(('http:', 'https:')) else route.continue_())
        page = context.new_page()
        page.on('request', lambda r: requests.append(r.url) if r.url.startswith(('http:', 'https:')) else None)
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(Path(report_path).resolve().as_uri())
        page.locator('#load-status').wait_for(state='hidden')
        page.locator('#filter').fill('motor')
        assert 'PARTIAL' in page.locator(f'#{prefix}failure-status').inner_text()
        page.locator(f'#{prefix}removals button').last.click()
        assert 'unresolved' in page.locator(f'#{prefix}alternative-status').inner_text()
        assert page.locator(f'#{prefix}alternative tbody tr').count() == 0
        assert not requests and not errors
        result = {'partial_visible': True, 'unresolved_without_witness': True,
                  'external_request_attempts': len(requests), 'javascript_errors': len(errors),
                  'dom_elements': page.locator('*').count(), 'browser': browser.version}
        browser.close()
        return result


def check_combined(report_path):
    """The two inspectors coexist without sharing selection state."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context(offline=True, viewport={'width': 360, 'height': 800})
        requests, errors = [], []
        context.route('**/*', lambda route: route.abort() if route.request.url.startswith(('http:', 'https:')) else route.continue_())
        page = context.new_page()
        page.on('request', lambda r: requests.append(r.url) if r.url.startswith(('http:', 'https:')) else None)
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(Path(report_path).resolve().as_uri())
        page.locator('#load-status').wait_for(state='hidden')
        page.locator('#filter').fill('motor')
        page.locator('#threshold').select_option('5')
        assert '0 confirmed critical edges' in page.locator('#failure-status').inner_text()
        assert '1 confirmed critical nodes' in page.locator('#node-failure-status').inner_text()
        edge_before = page.locator('#alternative-status').inner_text()
        page.get_by_role('button', name='Inspect node removal shared', exact=True).focus()
        page.keyboard.press('Enter')
        assert page.locator('#node-alternative-heading').evaluate('(e) => e === document.activeElement')
        assert 'complete search exhausted' in page.locator('#node-alternative-status').inner_text()
        assert page.locator('#alternative-status').inner_text() == edge_before
        node_before = page.locator('#node-alternative-status').inner_text()
        page.locator('#removals button').last.click()
        assert page.locator('#node-alternative-status').inner_text() == node_before
        page.locator('#threshold').select_option('1')
        assert '0 confirmed critical nodes' in page.locator('#node-failure-status').inner_text()
        assert 'verified alternative' in page.locator('#node-alternative-status').inner_text()
        page.locator('#filter').fill('')
        page.get_by_role('button', name='Inspect sensor to sensor', exact=True).click()
        assert 'No intermediate candidates' in page.locator('#node-alternative-status').inner_text()
        assert page.locator('#node-removals tbody tr').count() == 0
        page.locator('#status').select_option('missing_node')
        assert 'Missing ID' in page.locator('#node-failure-status').inner_text()
        page.locator('#filter').fill('no match')
        assert 'No query selected' in page.locator('#node-failure-status').inner_text()
        assert page.locator('#node-alternative tbody tr').count() == 0
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert not requests and not errors
        result = {'independent_inspector_selection': True, 'identity_and_missing_states': True,
                  'external_request_attempts': len(requests), 'javascript_errors': len(errors),
                  'dom_elements': page.locator('*').count(), 'browser': browser.version}
        browser.close()
        return result
