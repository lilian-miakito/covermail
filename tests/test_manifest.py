from __future__ import annotations

import os
from pathlib import Path

import pytest

from covermail.errors import ModelProfileError
from covermail.models.manifest import build_artifact_manifest, verify_artifact_manifest


def test_manifest_build_and_verify_regular_files(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "config.json").write_bytes(b"{}")
    (tmp_path / "nested" / "weights.safetensors").write_bytes(b"safe weights")
    manifest = build_artifact_manifest(
        tmp_path,
        ["nested/weights.safetensors", "config.json"],
    )
    assert [entry["path"] for entry in manifest] == [
        "config.json",
        "nested/weights.safetensors",
    ]
    verify_artifact_manifest(tmp_path, manifest)


def test_manifest_detects_modified_file(tmp_path: Path) -> None:
    artifact = tmp_path / "config.json"
    artifact.write_bytes(b"before")
    manifest = build_artifact_manifest(tmp_path, ["config.json"])
    artifact.write_bytes(b"after")
    with pytest.raises(ModelProfileError, match="verification failed"):
        verify_artifact_manifest(tmp_path, manifest)


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="platform lacks O_NOFOLLOW")
def test_manifest_never_follows_file_or_directory_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(b"{}")
    (tmp_path / "linked.json").symlink_to(target)
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    (real_dir / "config.json").write_bytes(b"{}")
    (tmp_path / "linked-dir").symlink_to(real_dir, target_is_directory=True)
    with pytest.raises(ModelProfileError, match="safely"):
        build_artifact_manifest(tmp_path, ["linked.json"])
    with pytest.raises(ModelProfileError, match="safely"):
        build_artifact_manifest(tmp_path, ["linked-dir/config.json"])


@pytest.mark.parametrize("path", ["../x", "/x", "a//b", "a/./b", "a\\b"])
def test_manifest_rejects_unsafe_paths(tmp_path: Path, path: str) -> None:
    with pytest.raises(ModelProfileError, match="path"):
        build_artifact_manifest(tmp_path, [path])
