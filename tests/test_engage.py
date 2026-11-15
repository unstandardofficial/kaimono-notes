from bot import engage

def test_checked_ids():
    body = "- [x] **コメント** a → hi [d:0123abcd]\n- [ ] **コメント** b → yo [d:89abcdef]\n- [X] c → z [d:deadbeef] ✅投稿済み"
    assert engage.checked_ids(body) == ["0123abcd", "deadbeef"]
