"""Safe regular-file artifact manifest construction and verification."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import TypedDict

from covermail.errors import ModelProfileError

_CHUNK_SIZE = 1024 * 1024


class ArtifactRecord(TypedDict):
    path: str
    size: int
    sha256: str


def _validate_relative_path(value: str) -> tuple[str, ...]:
    if "\x00" in value or "\\" in value or value.startswith("/"):
        raise ModelProfileError("artifact path is not a safe relative POSIX path")
    parts = value.split("/")
    if not value or any(part in {"", ".", ".."} for part in parts):
        raise ModelProfileError("artifact path is not a safe relative POSIX path")
    if PurePosixPath(value).is_absolute():
        raise ModelProfileError("artifact path is not relative")
    return tuple(parts)


def _open_regular_nofollow(root: Path, relative_path: str) -> int:
    parts = _validate_relative_path(relative_path)
    if not hasattr(os, "O_NOFOLLOW"):
        raise ModelProfileError("platform cannot enforce no-symlink artifact verification")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY
    nofollow = os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        current = os.open(root, directory_flags | nofollow)
        descriptors.append(current)
        for part in parts[:-1]:
            current = os.open(part, directory_flags | nofollow, dir_fd=current)
            descriptors.append(current)
        descriptor = os.open(parts[-1], os.O_RDONLY | nofollow, dir_fd=current)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ModelProfileError(f"artifact is not a regular file: {relative_path}")
        return descriptor
    except OSError as error:
        raise ModelProfileError(f"artifact cannot be opened safely: {relative_path}") from error
    finally:
        for descriptor_to_close in reversed(descriptors):
            os.close(descriptor_to_close)


def _measure_and_hash(root: Path, relative_path: str) -> tuple[int, str]:
    descriptor = _open_regular_nofollow(root, relative_path)
    digest = hashlib.sha256()
    size = 0
    try:
        while chunk := os.read(descriptor, _CHUNK_SIZE):
            size += len(chunk)
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return size, digest.hexdigest()


def build_artifact_manifest(root: Path, paths: Iterable[str]) -> list[ArtifactRecord]:
    """Hash a selected qualified tree without following any symlink."""
    ordered = sorted(set(paths))
    if not ordered:
        raise ModelProfileError("artifact manifest is empty")
    manifest: list[ArtifactRecord] = []
    for relative_path in ordered:
        size, digest = _measure_and_hash(root, relative_path)
        manifest.append({"path": relative_path, "size": size, "sha256": digest})
    return manifest


def verify_artifact_manifest(
    root: Path, artifacts: Sequence[Mapping[str, object]]
) -> None:
    """Fail closed unless each addressed artifact is the exact regular file."""
    if not artifacts:
        raise ModelProfileError("artifact manifest is empty")
    seen: set[str] = set()
    for artifact in artifacts:
        relative_path = artifact.get("path")
        expected_size = artifact.get("size")
        expected_digest = artifact.get("sha256")
        if not isinstance(relative_path, str) or relative_path in seen:
            raise ModelProfileError("artifact manifest has an invalid or duplicate path")
        if isinstance(expected_size, bool) or not isinstance(expected_size, int):
            raise ModelProfileError(f"artifact has an invalid size: {relative_path}")
        if not isinstance(expected_digest, str):
            raise ModelProfileError(f"artifact has an invalid digest: {relative_path}")
        seen.add(relative_path)
        size, digest = _measure_and_hash(root, relative_path)
        if size != expected_size or digest != expected_digest:
            raise ModelProfileError(f"artifact verification failed: {relative_path}")


def materialize_artifact_tree(source: Path, destination: Path, paths: Iterable[str]) -> None:
    """Create a no-symlink qualified tree from a user-trusted snapshot source.

    Existing destinations are rejected. Hard links avoid duplicating large local
    blobs; a regular file copy is the cross-filesystem fallback.
    """
    ordered = sorted(set(paths))
    if not ordered:
        raise ModelProfileError("artifact selection is empty")
    try:
        destination.mkdir(mode=0o700, parents=True, exist_ok=False)
        for relative_path in ordered:
            parts = _validate_relative_path(relative_path)
            source_path = source.joinpath(*parts).resolve(strict=True)
            if not source_path.is_file():
                raise ModelProfileError(f"snapshot artifact is not a regular file: {relative_path}")
            destination_path = destination.joinpath(*parts)
            destination_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                os.link(source_path, destination_path, follow_symlinks=False)
            except OSError:
                with source_path.open("rb") as source_stream, destination_path.open(
                    "xb"
                ) as destination_stream:
                    shutil.copyfileobj(source_stream, destination_stream, _CHUNK_SIZE)
    except FileExistsError as error:
        raise ModelProfileError("qualified artifact destination already exists") from error
    except OSError as error:
        raise ModelProfileError("artifact tree could not be materialized") from error
