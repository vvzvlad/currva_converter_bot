# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""The plain key-value API of KeyValueStore."""

from src.storage import KeyValueStore


def test_set_and_get_roundtrip(store):
    store.set("user:1:currencies", ["USD", "RUB"])
    assert store.get("user:1:currencies") == ["USD", "RUB"]


def test_get_missing_key_returns_none(store):
    assert store.get("nope") is None


def test_get_missing_key_returns_given_default(store):
    assert store.get("nope", 0) == 0


def test_set_overwrites_existing_value(store):
    store.set("k", 1)
    store.set("k", 2)
    assert store.get("k") == 2


def test_stores_nested_structures_and_non_ascii(store):
    value = {"chats": {"-100": {"title": "Тестовый чат", "requests": 39}}}
    store.set("chats", value)
    assert store.get("chats") == value


def test_falsy_values_survive_the_roundtrip(store):
    # These matter: the managers store 0 and {} as legitimate values.
    for key, value in (("zero", 0), ("empty_dict", {}), ("empty_list", []), ("false", False)):
        store.set(key, value)
        assert store.get(key) == value
        assert store.exists(key)


def test_exists(store):
    assert not store.exists("k")
    store.set("k", None)
    assert store.exists("k")


def test_rem_deletes_and_reports_whether_key_was_there(store):
    store.set("k", "v")
    assert store.rem("k")
    assert not store.exists("k")
    assert store.get("k") is None
    assert not store.rem("k")


def test_set_many_writes_everything(store):
    store.set_many({"a": 1, "b": {"x": True}})
    assert store.get("a") == 1
    assert store.get("b") == {"x": True}


def test_set_many_with_empty_dict_is_a_noop(store):
    store.set_many({})  # must not raise, must not open a transaction
    store.set("a", 1)
    assert store.get("a") == 1


def test_data_survives_reopening(tmp_path, make_store):
    path = tmp_path / "state.db"
    first = KeyValueStore(str(path))
    first.set("k", ["v"])
    first.close()

    second = make_store()
    assert second.get("k") == ["v"]


def test_creates_missing_parent_directory(tmp_path, closers):
    nested = tmp_path / "deep" / "nested" / "state.db"
    store = KeyValueStore(str(nested))
    closers.append(store.close)
    store.set("k", "v")
    assert nested.exists()
