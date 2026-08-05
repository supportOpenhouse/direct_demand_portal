def test_rm_only_paths_can_reference_text():
    """`text` was missing from this module's imports, so every RM-scoped query in it
    raised NameError at runtime. Admins never hit those branches, which is why the
    WhatsApp page looked fine."""
    from app.routers import gupshup
    assert hasattr(gupshup, "text")
    assert str(gupshup._thread_scope({"role": "rm", "name": ""})) == "false"
