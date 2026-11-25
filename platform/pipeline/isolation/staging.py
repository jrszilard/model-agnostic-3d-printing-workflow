"""Bounded byte snapshots and artifact framing for trusted local evaluation.

No CAD, execution, repository fiction, authorization or manufacturing verdict.
The host independently hashes bytes. Workers never receive writable host paths.
"""
from __future__ import annotations

import fcntl
import hashlib
import io
import os
from pathlib import Path
import re
import stat
import struct

MiB = 1024 * 1024
MAX_FILE = 16 * MiB
MAX_TOTAL = 32 * MiB
MAX_INPUTS = 32                 # selected code + data, not a service quota
MAX_OUTPUTS = 8
MAX_WIRE = MAX_TOTAL + 2048
NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}\Z")
SEALS = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL


def require(condition, message):
    if not condition:
        raise ValueError(message)


def name_ok(name, *, nested=False):
    require(type(name) is str, "invalid file name")
    parts = name.split("/")
    require((nested or len(parts) == 1) and len(parts) <= 6
            and all(NAME.fullmatch(p) and p not in {".", ".."} for p in parts),
            "invalid file name")
    return name


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path, *, maximum=MAX_FILE):
    """No symlink traversal (including ancestors), hardlinks, FIFOs or unbounded reads."""
    path = Path(os.path.abspath(path))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            new = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    finally:
        os.close(fd)
    with os.fdopen(file_fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "not a private regular file")
        require(0 < before.st_size <= maximum, "file size limit")
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
        require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                and len(data) == before.st_size, "file changed while snapshotting")
    return data


def source(owner, relative, expected_sha256):
    """Caller selects canonical owner; identity is actual bytes, NOT a Git checkpoint."""
    name_ok(relative, nested=True)
    owner = Path(os.path.abspath(owner))
    data = read_regular(owner / relative)
    require(digest(data) == expected_sha256, "source digest mismatch")
    return data, {"kind": "selected-source", "owner": str(owner), "path": relative,
                  "sha256": digest(data), "bytes": len(data)}


def sealed_fd(data):
    require(type(data) is bytes and 0 < len(data) <= MAX_TOTAL, "invalid sealed bytes")
    fd = os.memfd_create("evaluation-input", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        with os.fdopen(os.dup(fd), "wb") as stream:
            stream.write(data)
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, SEALS)
        require(fcntl.fcntl(fd, fcntl.F_GET_SEALS) == SEALS, "input not sealed")
        return fd
    except BaseException:
        os.close(fd)
        raise


class SealedInputs:
    def __init__(self, inputs):
        require(type(inputs) is dict and 0 < len(inputs) <= MAX_INPUTS, "input count limit")
        names = [name_ok(name, nested=True) for name in inputs]
        require(len({n.casefold() for n in names}) == len(names), "ambiguous input names")
        require(not any(a.startswith(b + "/") for a in names for b in names), "input path collision")
        require(all(type(data) is bytes and 0 < len(data) <= MAX_FILE for data in inputs.values()),
                "input file size limit")
        require(sum(map(len, inputs.values())) <= MAX_TOTAL, "input total limit")
        self.fds = {}
        self.identities = {name: {"sha256": digest(data), "bytes": len(data)} for name, data in inputs.items()}
        try:
            for name, data in inputs.items():
                self.fds[name] = sealed_fd(data)
        except BaseException:
            self.close()
            raise

    def close(self):
        for fd in self.fds.values():
            os.close(fd)
        self.fds.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def output_names(names):
    require(type(names) in (list, tuple) and 0 < len(names) <= MAX_OUTPUTS, "output count limit")
    for name in names:
        name_ok(name)
    require(len({n.casefold() for n in names}) == len(names), "duplicate output name")
    return tuple(names)


def collect(directory, expected):
    """Called after the child exits and no living descendants remain. Still untrusted on host."""
    expected = output_names(expected)
    require(set(os.listdir(directory)) == set(expected), "unexpected/missing output")
    result = {}
    total = 0
    for name in expected:
        data = read_regular(Path(directory) / name, maximum=MAX_TOTAL - total)
        total += len(data)
        result[name] = data
    return result


def encode(files):
    names = output_names(list(files))
    require(all(type(data) is bytes and len(data) > 0 for data in files.values()), "empty output")
    require(sum(map(len, files.values())) <= MAX_TOTAL, "output total limit")
    stream = io.BytesIO()
    stream.write(bytes([len(names)]))
    for name in names:
        raw = name.encode("ascii")
        stream.write(struct.pack("!HQ", len(raw), len(files[name])))
        stream.write(raw)
        stream.write(files[name])
    return stream.getvalue()


def decode(wire, expected):
    """No archives, extraction paths, worker hashes or unbounded JSON parser."""
    names = output_names(expected)
    require(type(wire) is bytes and 0 < len(wire) <= MAX_WIRE, "artifact transport limit")
    stream = io.BytesIO(wire)
    require(stream.read(1) == bytes([len(names)]), "artifact count mismatch")
    result = {}
    total = 0
    for _ in names:
        header = stream.read(10)
        require(len(header) == 10, "truncated artifact header")
        name_length, length = struct.unpack("!HQ", header)
        require(0 < name_length <= 80 and 0 < length <= MAX_TOTAL - total, "artifact size limit")
        try:
            name = stream.read(name_length).decode("ascii")
        except UnicodeError as exc:
            raise ValueError("artifact name encoding") from exc
        name_ok(name)
        require(name in names and name not in result, "unexpected/duplicate artifact")
        data = stream.read(length)
        require(len(data) == length, "truncated artifact")
        total += length
        result[name] = data
    require(stream.read(1) == b"", "trailing artifact data")
    return result
