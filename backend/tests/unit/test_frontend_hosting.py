"""Exercise the deployed CloudFront rewrite code without AWS or credentials."""

import json
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "uri,expected",
    [
        ("/", "/index.html"),
        ("/interview", "/interview/index.html"),
        ("/interview/", "/interview/index.html"),
        ("/_next/static/app.js", "/_next/static/app.js"),
        ("/404.html", "/404.html"),
        ("/favicon.ico", "/favicon.ico"),
    ],
)
def test_static_export_route_preserves_query_and_headers(uri, expected):
    source = Path(__file__).resolve().parents[3] / "terraform/modules/frontend/rewrite.js"
    script = (
        "const fs=require('fs'),vm=require('vm');const c={};"
        "vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),c);"
        "const request=JSON.parse(fs.readFileSync(0,'utf8'));"
        "console.log(JSON.stringify(c.handler({request})));"
    )
    request = {
        "uri": uri,
        "querystring": {"session": {"value": "synthetic"}},
        "headers": {"host": {"value": "synthetic.example.invalid"}},
    }
    result = subprocess.run(
        ["node", "-e", script, str(source)],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    actual = json.loads(result.stdout)
    assert actual == {**request, "uri": expected}


@pytest.mark.parametrize("now,closed", [(99999, False), (100000, True), (100001, True)])
def test_expiry_blocks_cached_and_uncached_viewer_requests_at_boundary(now, closed):
    source = Path(__file__).resolve().parents[3] / "terraform/modules/frontend/rewrite.js"
    script = (
        "const fs=require('fs'),vm=require('vm');"
        f"const c={{releaseExpiresAt:100,Date:{{now:()=>{now}}}}};"
        "vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),c);"
        "console.log(JSON.stringify(c.handler({request:{uri:'/_next/static/app.js'}})));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(source)], capture_output=True, text=True, check=True, timeout=10
    )
    actual = json.loads(result.stdout)
    if closed:
        assert actual["statusCode"] == 403
        assert actual["headers"]["cache-control"]["value"] == "no-store"
    else:
        assert actual["uri"] == "/_next/static/app.js"
