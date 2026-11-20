"""Durable single-database commit and failure injection. No distributed guarantee."""
from __future__ import annotations
import argparse,json,sqlite3,subprocess,sys,tempfile
from pathlib import Path

def connect(path):
    db=sqlite3.connect(path);db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE IF NOT EXISTS model(id INTEGER PRIMARY KEY, weight INTEGER NOT NULL)')
    db.execute('INSERT OR IGNORE INTO model VALUES (1,0)')
    db.execute('CREATE TABLE IF NOT EXISTS commits(batch TEXT PRIMARY KEY, delta INTEGER NOT NULL)');db.commit();return db

def commit(path,batch,delta,crash):
    db=connect(path)
    try:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT delta FROM commits WHERE batch=?',(batch,)).fetchone()
        if old:
            if old[0]!=delta:raise ValueError('same batch identity with conflicting content')
            db.rollback();return 'duplicate'
        db.execute('UPDATE model SET weight=weight+? WHERE id=1',(delta,))
        if crash=='before_commit':
            import os;os._exit(71)
        db.execute('INSERT INTO commits VALUES (?,?)',(batch,delta));db.commit()
        if crash=='after_commit':
            import os;os._exit(72)
        return 'committed'
    finally:db.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker');parser.add_argument('--crash',default='none');a=parser.parse_args()
    if a.worker:commit(a.worker,'batch-1',3,a.crash);return 0
    results=[]
    with tempfile.TemporaryDirectory(prefix='course-commit-') as folder:
        for mode,code in [('before_commit',71),('after_commit',72)]:
            path=str(Path(folder)/(mode+'.sqlite'));connect(path).close()
            p=subprocess.run([sys.executable,__file__,'--worker',path,'--crash',mode],timeout=20)
            assert p.returncode==code
            outcome=commit(path,'batch-1',3,'none');db=connect(path)
            weight=db.execute('SELECT weight FROM model').fetchone()[0];count=db.execute('SELECT COUNT(*) FROM commits').fetchone()[0];db.close()
            assert weight==3 and count==1
            try:commit(path,'batch-1',4,'none')
            except ValueError:conflict=True
            else:conflict=False
            assert conflict
            results.append({'crash':mode,'retry':outcome,'weight':weight,'commits':count,'conflicting_retry_rejected':conflict})
    report={'status':'passed','cases':results,'boundary':'Single SQLite transaction stores both toy model state and commit. Separate GPU weights, queues, leadership and multi-node failures are not covered.'}
    out=Path(__file__).with_name('results');out.mkdir(exist_ok=True);(out/'durable_commit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
