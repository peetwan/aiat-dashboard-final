
import pytest

from tools.f2_pipeline.common import output_directory, rename_new_directory


def test_native_commit_preserves_the_complete_staged_directory(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "destination"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (nested / "built.json").write_bytes(b'{"count": 7}\n')
    rename_new_directory(source, destination)
    assert not source.exists()
    assert (destination / "nested/built.json").read_bytes() == b'{"count": 7}\n'




def test_native_commit_never_replaces_existing_empty_directory(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    inode = destination.stat().st_ino
    (source / "built.json").write_text("{}")
    with pytest.raises(FileExistsError):
        rename_new_directory(source, destination)
    assert destination.stat().st_ino == inode
    assert not (destination / "built.json").exists()
    assert (source / "built.json").exists()


def test_output_context_cleans_only_its_own_failed_staging(tmp_path):
    output = tmp_path / "release"
    with pytest.raises(RuntimeError, match="synthetic"):
        with output_directory(output, ()) as stage:
            (stage / "incomplete.json").write_text("{}")
            raise RuntimeError("synthetic build failure")
    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


def test_concurrent_output_creation_survives_commit_race(tmp_path, monkeypatch):
    from tools.f2_pipeline import common

    output = tmp_path / "release"
    destination_inodes = []

    def concurrent_creation(source, destination):
        destination.mkdir()
        destination_inodes.append(destination.stat().st_ino)
        rename_new_directory(source, destination)

    monkeypatch.setattr(common, "rename_new_directory", concurrent_creation)
    with pytest.raises(FileExistsError):
        with output_directory(output, ()) as stage:
            (stage / "built.json").write_text("{}")
    assert output.stat().st_ino == destination_inodes[0]
    assert list(output.iterdir()) == []
    assert list(tmp_path.iterdir()) == [output]
