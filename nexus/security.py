from collections import defaultdict, deque
from threading import Lock
import hashlib
import hmac
import secrets
import time


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()
    return 'scrypt$' + salt.hex() + '$' + digest


def password_check(password, encoded):
    try:
        scheme, salt, expected = encoded.split('$')
        if scheme != 'scrypt':
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class RateLimit:
    def __init__(self):
        self.entries = defaultdict(deque)
        self.lock = Lock()

    def allow(self, key, limit, period=60):
        current = time.monotonic()
        with self.lock:
            if len(self.entries) > 10000:
                self.entries = defaultdict(deque, {k: v for k, v in self.entries.items() if v and v[-1] > current - 3600})
            queue = self.entries[key]
            while queue and queue[0] <= current - period:
                queue.popleft()
            if len(queue) >= limit:
                return False
            queue.append(current)
            return True
