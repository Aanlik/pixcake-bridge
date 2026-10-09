import errno
from pathlib import Path
from unittest.mock import patch

import pytest

from pixcake_bridge.files import RAW_EXTENSIONS, Stability, index_files, match_raw, materialize, safe_name, sha256, snapshot


@pytest.mark.parametrize("ext", sorted(RAW_EXTENSIONS))
def test_match_case_insensitive(tmp_path, ext):
    p = tmp_path / ("DSC00125" + ext.upper())
    p.write_bytes(b"raw")
    assert match_raw("dsc00125.JPG", index_files(tmp_path, RAW_EXTENSIONS)) == p


def test_conflict_and_missing(tmp_path):
    (tmp_path / "A.ARW").write_bytes(b"a")
    (tmp_path / "a.NEF").write_bytes(b"b")
    with pytest.raises(ValueError, match="冲突"):
        match_raw("a.jpg", index_files(tmp_path, RAW_EXTENSIONS))
    with pytest.raises(ValueError, match="未找到"):
        match_raw("b.jpg", index_files(tmp_path, RAW_EXTENSIONS))


def test_delivery_subtree_is_not_an_original_and_collision_lists_both_paths(tmp_path):
    (tmp_path / "DSC001.ARW").write_bytes(b"camera raw")
    nested = tmp_path / "PixCakeDelivery" / "event-7" / "03_SELECTED_RAW" / "DSC001.ARW"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"selected copy")

    index = index_files(tmp_path, RAW_EXTENSIONS, {"PixCakeDelivery"})
    assert match_raw("DSC001.JPG", index, tmp_path) == tmp_path / "DSC001.ARW"

    second = tmp_path / "Subfolder" / "DSC001.NEF"
    second.parent.mkdir()
    second.write_bytes(b"second original")
    with pytest.raises(ValueError, match=r"DSC001.*DSC001\.ARW.*Subfolder/DSC001\.NEF"):
        match_raw("DSC001.JPG", index_files(tmp_path, RAW_EXTENSIONS, {"PixCakeDelivery"}), tmp_path)


@pytest.mark.parametrize("name", ["../x.jpg", "a/b.jpg", "a\\b.jpg", "a\0.jpg", ".", "..", "C:x.jpg", "a\n.jpg", "x" * 241])
def test_illegal_name(name):
    with pytest.raises(ValueError):
        safe_name(name)


def test_symlink_refused(tmp_path):
    (tmp_path / "a.ARW").symlink_to(__file__)
    with pytest.raises(ValueError):
        index_files(tmp_path, RAW_EXTENSIONS)


def test_hardlink_and_no_overwrite(tmp_path):
    source, dest = tmp_path / "a.ARW", tmp_path / "out.ARW"
    source.write_bytes(b"original")
    source.chmod(0o444)
    before = sha256(source)
    assert materialize(source, dest) == "hardlink"
    assert source.stat().st_ino == dest.stat().st_ino
    assert sha256(source) == before
    with pytest.raises(FileExistsError):
        materialize(source, dest)


def test_writable_original_uses_copy(tmp_path):
    source, dest = tmp_path / "a.ARW", tmp_path / "out.ARW"
    source.write_bytes(b"original")
    with patch("pixcake_bridge.files.subprocess.run", side_effect=OSError()):
        assert materialize(source, dest) == "copy"
    assert source.stat().st_ino != dest.stat().st_ino
    assert source.stat().st_mode & 0o200
    assert not dest.stat().st_mode & 0o222


def test_exdev_fallback(tmp_path):
    source, dest = tmp_path / "a.ARW", tmp_path / "out.ARW"
    source.write_bytes(b"original")
    source.chmod(0o444)
    real_link = __import__("os").link
    def link(src, dst, **kw):
        if Path(src) == source:
            raise OSError(errno.EXDEV, "cross mount")
        return real_link(src, dst, **kw)
    with patch("pixcake_bridge.files.os.link", side_effect=link), patch("pixcake_bridge.files.subprocess.run", side_effect=OSError()):
        assert materialize(source, dest) == "copy"
    assert sha256(source) == sha256(dest)


def test_reflink_fallback(tmp_path):
    source, dest = tmp_path / "a.ARW", tmp_path / "out.ARW"
    source.write_bytes(b"original")
    def clone(args, **kw):
        __import__("shutil").copyfile(args[-2], args[-1])
    with patch("pixcake_bridge.files.subprocess.run", side_effect=clone):
        assert materialize(source, dest) == "reflink"


def test_stability_requires_quiet_period(tmp_path):
    p = tmp_path / "a.jpg"
    p.write_bytes(b"a")
    s = Stability(10)
    assert not s.ready(p, 0)
    assert not s.ready(p, 9)
    assert s.ready(p, 10)
    p.write_bytes(b"ab")
    assert not s.ready(p, 11)
    assert s.ready(p, 21)


def test_size_limit(tmp_path):
    p, dest = tmp_path / "a.jpg", tmp_path / "snapshot"
    with p.open("wb") as f:
        f.truncate(100 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="限制"):
        snapshot(p, dest, 100 * 1024 * 1024)
    assert not dest.exists()

