#!/usr/bin/env python3
"""Optional browser QA for a generated report (requires Playwright + Chromium)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.observatory_presentation import render


def check(report: Path, screenshots: Path | None = None) -> dict:
    from playwright.sync_api import sync_playwright
    failures = []
    requests = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: failures.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        page.goto(report.resolve().as_uri())
        page.wait_for_selector('.card')
        assert page.locator('.card').count() == 14
        assert page.locator('#overview').is_visible() and not page.locator('#timeline').is_visible()
        if screenshots:
            screenshots.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshots / 'desktop.png'))
        page.select_option('#checkpoint', '2')
        assert 'Day 72' in page.locator('#checkpoint-info').inner_text()
        page.click('a[href="#causes"]')
        assert page.locator('#trace-detail .verified').count() > 0
        page.click('a[href="#comparison"]')
        assert page.locator('#diff table').count() == 1
        page.select_option('#scenario', '1')
        assert page.locator('#trace option').count() >= 4
        page.click('a[href="#entities"]')
        page.fill('#entity-search', 'institution')
        assert page.locator('#entity-list button').count() > 0
        page.click('a[href="#timeline"]')
        page.fill('#event-id', 'ghost')
        assert page.locator('#page-info').inner_text().startswith('0 records')
        page.set_viewport_size({'width': 390, 'height': 844})
        page.click('a[href="#overview"]')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        if screenshots:
            page.screenshot(path=str(screenshots / 'mobile.png'))
        assert not failures, failures
        assert requests == [report.resolve().as_uri()], requests
        bundle = json.loads(page.locator('#observatory-data').text_content())
        bundle['scenarios'][0]['description'] = '</script><img src=https://example.invalid onerror="window.hostileExecuted=true">\ud800'
        with TemporaryDirectory(prefix='observatory-browser-') as temp:
            hostile = Path(temp) / 'hostile.html'
            hostile.write_text(render(bundle), encoding='utf-8')
            page.goto(hostile.as_uri())
            page.wait_for_selector('.card')
            assert page.locator('img').count() == 0
            assert page.evaluate('window.hostileExecuted === undefined')
            assert not failures, failures
            assert len(requests) == 2 and requests[-1] == hostile.as_uri()
        browser.close()
    return {'status': 'PASS', 'file_protocol': True, 'external_requests': 0,
            'javascript_errors': 0, 'desktop_width': 1440, 'mobile_width': 390,
            'hostile_script_context': 'rejected', 'sections': 6}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--screenshots', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.report, args.screenshots), indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
