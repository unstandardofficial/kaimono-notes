import json
from datetime import datetime
from bot import manual_post as mp

def test_posts_due_once_per_slug(tmp_path):
    q = tmp_path / "q.json"
    q.write_text(json.dumps([
        {"slug": "a", "text": "1"}, {"slug": "a", "text": "2"},
        {"slug": "b", "text": "3", "at": "2099-01-01T00:00"}]), encoding="utf-8")
    sent = []
    n = mp.run(datetime(2026, 11, 15, 15, tzinfo=mp.JST), q, lambda t, i, tok: sent.append(t) or "id")
    assert n == 1 and sent == ["1"]
    data = json.loads(q.read_text(encoding="utf-8"))
    assert data[0]["posted_id"] == "id" and "posted_id" not in data[1]
