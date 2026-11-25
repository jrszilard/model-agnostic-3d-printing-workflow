"""Whole-operation cgroup-v2 observer, not a launcher or a hard CPU-cap proof.

The trusted controller must place EVERY attributable helper below the fresh group,
prevent migration, and own all child handles. No worker may access this interface.
No CAD imports, CLI or activation switch. Polling can overshoot; report it in full.
"""
import os
from pathlib import Path
import threading
import time


class ObservationError(RuntimeError):
    pass


class LinuxGroup:
    def __init__(self, path):
        self.path = Path(path)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self.anchor = self.identity()
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def identity(self):
        fdstat, pathstat = os.fstat(self.fd), self.path.stat(follow_symlinks=False)
        if (fdstat.st_dev, fdstat.st_ino) != (pathstat.st_dev, pathstat.st_ino):
            raise ObservationError('group replaced')
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        info = Path(f'/proc/self/fdinfo/{self.fd}').read_text().splitlines()
        mount = [line for line in info if line.startswith('mnt_id:')]
        if len(mount) != 1:
            raise ObservationError('mount identity unavailable')
        # A cgroup-looking regular directory is not a kernel counter.
        mid = mount[0].split()[1]
        mounts = Path('/proc/self/mountinfo').read_text().splitlines()
        if not any(line.split()[0] == mid and ' - cgroup2 ' in line for line in mounts):
            raise ObservationError('not cgroup v2')
        return boot, mount[0], fdstat.st_dev, fdstat.st_ino

    def read(self, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            raw = os.read(fd, 8193)
            if len(raw) > 8192:
                raise ObservationError('counter too large')
            return raw.decode('ascii')
        finally:
            os.close(fd)

    def kill(self):
        fd = os.open('cgroup.kill', os.O_WRONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            if os.write(fd, b'1') != 1:
                raise ObservationError('short kill write')
        finally:
            os.close(fd)

    def remove(self):
        if self.identity() != self.anchor:
            raise ObservationError('cleanup identity changed')
        # rmdir refuses remaining descendants; never recursively delete an unknown
        # group. The stage controller must already have removed its child groups.
        os.rmdir(self.path)
        if self.path.exists():
            raise ObservationError('group survived removal')
        os.close(self.fd)
        self.fd = None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def field(raw, name):
    lines = [line.split() for line in raw.splitlines()]
    values = [parts[1] for parts in lines if len(parts) == 2 and parts[0] == name]
    if len(values) != 1 or not values[0].isascii() or not values[0].isdigit():
        raise ObservationError('missing or malformed counter')
    return int(values[0])


class OperationObserver:
    """Owned by one serialized controller; kernel/process doubles belong in tests."""
    def __init__(self, path, deadline):
        self.group = LinuxGroup(path)
        self.lock = threading.RLock()
        try:
            self.anchor = self.group.identity()
        except BaseException:
            self.group.close()
            raise
        self.deadline = deadline
        self.last = 0
        self.fenced = False
        self.armed = False
        self.failed = False
        self.removed = False
        self.children = []
        try:
            if self.sample() != 0 or self.populated():
                raise ObservationError('operation group not fresh and empty')
        except BaseException:
            self.group.close()
            raise

    def populated(self):
        value = field(self.group.read('cgroup.events'), 'populated')
        if value not in (0, 1):
            raise ObservationError('invalid populated state')
        return value == 1

    def sample(self):
        with self.lock:
            if self.failed or self.group.identity() != self.anchor:
                self.failed = True
                raise ObservationError('observation continuity lost')
            value = field(self.group.read('cpu.stat'), 'usage_usec')
            if value < self.last:
                self.failed = True
                raise ObservationError('counter regressed')
            self.last = value
            return value

    def arm(self):
        """Only AFTER the owner's durable START_INTENT. Does not start anything."""
        with self.lock:
            if self.armed or self.fenced or self.failed or time.monotonic() >= self.deadline:
                raise ObservationError('start fenced')
            self.sample()
            self.armed = True

    def register_child(self, child):
        # Future launcher must serialize fork+registration with this same lock.
        # This helper is NOT a launcher, containment or escaped-process proof.
        with self.lock:
            if not self.armed or self.fenced:
                raise ObservationError('start fenced')
            self.children.append(child)

    def needs_stop(self):
        return time.monotonic() >= self.deadline or self.sample() >= 180_000_000

    def finish(self, record_final):
        """Fence -> kill -> reap -> empty -> durable final -> remove -> terminal.

        record_final is the trusted owner's durable journal sink, not a receipt.
        Any failure leaves the observer permanently held and never returns usage.
        """
        with self.lock:
            if not self.armed or self.fenced or self.failed:
                raise ObservationError('terminal unavailable')
            self.fenced = True
            try:
                if self.group.identity() != self.anchor:
                    raise ObservationError('group identity changed')
                self.group.kill()
                for child in self.children:
                    child.wait(timeout=3)
                if self.populated():
                    raise ObservationError('descendants remain')
                usage = self.sample()
                record_final(dict(usage_usec=usage, identity=list(self.anchor),
                                  monotonic_ns=time.monotonic_ns()))
                self.group.remove()
                self.removed = True
                return usage
            except BaseException:
                self.failed = True
                raise

    def abort(self):
        """Best-effort safety termination after uncertainty; NEVER a terminal."""
        with self.lock:
            self.fenced = True
            self.failed = True
            if self.removed:
                return
            # Anchored handle, not a potentially reused pathname. A failed kill or
            # reap must not prevent attempts on the remaining owned children.
            error = None
            actions = [self.group.kill] + [lambda child=child: child.wait(timeout=3) for child in self.children]
            for action in actions:
                try:
                    action()
                except BaseException as exc:
                    if error is None:
                        error = exc
                    else:
                        error.add_note('Additional termination failure: '+type(exc).__name__)
            try:
                if self.populated():
                    raise ObservationError('descendants remain after abort')
            except BaseException as exc:
                if error is None:
                    error = exc
                else:
                    error.add_note('Population unknown: '+type(exc).__name__)
            if error is not None:
                raise error

    def close(self):
        self.fenced = True
        self.failed = True
        self.group.close()  # Never a cleanup proof or permission to release.
