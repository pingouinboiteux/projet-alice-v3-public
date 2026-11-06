"""Explicit persistent note storage; no opening or directory creation at import.

An OS lock is held while the wiki is running. The lock file stays in place:
unlinking it would let a second process lock a different file at the same path.
Process termination releases the OS lock without an unsafe stale-file override.
"""
from pathlib import Path
import os
import stat

ROOT = Path(__file__).resolve().parents[1]


class NotesStorage:
    def __init__(self, directory, *, personal=False):
        self.directory = Path(directory)
        self.is_personal = personal
        self._lock_file = None
        self._locked = False

    @classmethod
    def personal(cls):
        return cls(ROOT/'data/notes/wiki', personal=True)

    @classmethod
    def validation(cls, directory):
        result = cls(directory)
        result._validate_path()
        return result

    def _validate_path(self):
        root = ROOT.absolute()
        directory = self.directory.absolute()
        if self.is_personal:
            if directory != root/'data/notes/wiki':
                raise ValueError('notes_storage_outside_scope')
        else:
            base = root/'data/validation'
            try: relative = directory.relative_to(base)
            except ValueError: raise ValueError('validation_notes_path_required') from None
            if not relative.parts or not relative.parts[0].startswith('validation_'):
                raise ValueError('validation_notes_path_required')
        if '..' in directory.parts:
            raise ValueError('notes_storage_outside_scope')
        # Reject links/junctions at every controlled component, including a
        # non-existing leaf reached through a redirected existing parent.
        relative = directory.relative_to(root)
        cursor = root
        for component in relative.parts:
            cursor = cursor/component
            if cursor.exists() or cursor.is_symlink():
                details = cursor.lstat()
                if stat.S_ISLNK(details.st_mode) or getattr(details, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    raise ValueError('linked_notes_storage_refused')
                if not cursor.is_dir():
                    raise ValueError('notes_storage_directory_required')
        if directory.resolve() != directory:
            raise ValueError('notes_storage_outside_scope')
        return directory

    def acquire(self):
        if self._lock_file is not None:
            raise RuntimeError('notes_storage_already_acquired')
        directory = self._validate_path()
        directory.parent.mkdir(parents=True, exist_ok=True)
        self._validate_path()
        lock_path = directory.parent/('.'+directory.name+'.alice.lock')
        if lock_path.is_symlink() or (lock_path.exists() and
                getattr(lock_path.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError('linked_notes_lock_refused')
        stream = lock_path.open('a+b')
        self._lock_file = stream
        try:
            if lock_path.stat().st_size == 0:
                stream.write(b'0');stream.flush()
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._locked = True
            self._validate_path()
            directory.mkdir(exist_ok=True)
            info = directory/'tiddlywiki.info'
            if info.is_symlink():
                raise ValueError('linked_notes_storage_refused')
            if not info.is_file() and any(directory.iterdir()):
                raise ValueError('unrecognized_notes_storage')
            return directory
        except BaseException:
            self.release()
            raise

    def release(self):
        stream, self._lock_file = self._lock_file, None
        locked, self._locked = self._locked, False
        if stream is None:return
        try:
            if locked:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()
