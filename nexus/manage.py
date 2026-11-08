"""Local interactive account management and non-destructive storage review."""
from getpass import getpass
from uuid import uuid4
import argparse
from .config import Settings
from .schemas import Credentials
from .security import password_hash
from .store import Store, now


def main():
    parser = argparse.ArgumentParser(description='NEXUS local management. Does not print passwords or delete user files.')
    parser.add_argument('command', choices=['add-user', 'reset-password', 'storage'])
    parser.add_argument('--username')
    args = parser.parse_args()
    settings = Settings()
    store = Store(settings.data_dir / 'nexus.sqlite3')
    if args.command == 'storage':
        for directory in settings.data_dir.iterdir():
            if directory.is_dir():
                files = [p for p in directory.rglob('*') if p.is_file()]
                print(directory.name, len(files), 'files', sum(p.stat().st_size for p in files), 'bytes; retained until owner removes them explicitly')
        return
    username = args.username or input('Username: ')
    password = getpass('Password (12+ characters): ')
    if password != getpass('Repeat password: '):
        raise SystemExit('Passwords do not match')
    credentials = Credentials(username=username, password=password)
    encoded = password_hash(credentials.password)
    with store.connect() as db:
        if args.command == 'add-user':
            user = uuid4().hex
            db.execute('INSERT INTO users VALUES(?,?,?,?)', (user, username, encoded, now()))
        else:
            row = db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
            if not row:
                raise SystemExit('User not found')
            user = row['id']
            db.execute('UPDATE users SET password=? WHERE id=?', (encoded, user))
            db.execute('DELETE FROM sessions WHERE user_id=?', (user,))
    store.audit(user, args.command)
    print('Account updated. Password was not logged.')


if __name__ == '__main__':
    main()
