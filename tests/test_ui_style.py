"""Paper UI regression checks: assets served and no provider credentials leaked."""
from pathlib import Path
from fastapi.testclient import TestClient
from retailiq.api import app

client = TestClient(app)

def test_style_assets_are_served():
    css = client.get('/assets/styles.css')
    js = client.get('/assets/app.js')
    assert css.status_code == js.status_code == 200
    assert 'text/css' in css.headers['content-type']
    assert 'javascript' in js.headers['content-type']
    for color in ('#f8f5ed', '#ffda6e', '#6ece9d', '#000'):
        assert color in css.text
    assert 'linear-gradient(' not in css.text
    assert 'box-shadow:' not in css.text

def test_new_assistant_and_roi_markers_present():
    html = client.get('/').text
    for marker in ('id="q"', 'id="answer"', 'id="roi-form"', 'id="roi-net"',
                   'id="roi-sensitivity"', '/assets/styles.css', '/assets/app.js'):
        assert marker in html
    assert 'OPENAI_API_KEY' not in html
    assert 'LANGSMITH_API_KEY' not in html
