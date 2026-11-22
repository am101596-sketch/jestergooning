"""Install the verified full research database from its GitHub release ZIP."""
import argparse
import hashlib
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path,help='Path to FirstStep_Database.zip')
    args=p.parse_args()
    expected=json.loads((ROOT/'data'/'release.json').read_text())
    with args.archive.open('rb') as f:
        actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=expected['sha256']:
        raise SystemExit('Archive checksum mismatch; no database was installed.')
    destination=ROOT/'data'/'research.sqlite'
    stage=destination.with_suffix('.sqlite.part')
    try:
        with zipfile.ZipFile(args.archive) as z:
            with z.open('FirstStep_Database/firststep_research.sqlite') as src,stage.open('wb') as dst:
                shutil.copyfileobj(src,dst)
        db=sqlite3.connect(stage.resolve().as_uri()+'?mode=ro',uri=True)
        try:
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                raise ValueError('SQLite integrity check failed.')
            if db.execute('SELECT count(*) FROM geography').fetchone()[0]!=330954:
                raise ValueError('Unexpected geography count.')
        finally:
            db.close()
        stage.replace(destination)
    finally:
        stage.unlink(missing_ok=True)
    print(f'Installed {destination} ({destination.stat().st_size:,} bytes). Restart FirstStep.')


if __name__=='__main__':main()
