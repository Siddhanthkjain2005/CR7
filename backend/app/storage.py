"""Local SQLite audit log, retaining exact inputs, model versions and measurements."""
from pathlib import Path
import json
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, MetaData, Table, Column, String, Text, select

ROOT=Path(__file__).resolve().parents[2]
DB_PATH=Path(os.environ.get('IMPULSETWIN_DB',ROOT/'artifacts/impulsetwin.sqlite3'))
DB_PATH.parent.mkdir(parents=True,exist_ok=True)
engine=create_engine('sqlite:///'+str(DB_PATH),connect_args={'check_same_thread':False})
metadata=MetaData()
records=Table('records',metadata,Column('id',String,primary_key=True),Column('kind',String,index=True),
    Column('created_at',String),Column('payload',Text))
metadata.create_all(engine)

def put(kind,id,payload):
    stamp=datetime.now(timezone.utc).isoformat(); result={**payload,'id':id,'created_at':stamp}
    with engine.begin() as c: c.execute(records.insert().values(id=id,kind=kind,created_at=stamp,payload=json.dumps(result,allow_nan=False)))
    return result

def get(id,kind=None):
    query=select(records.c.payload).where(records.c.id==id)
    if kind: query=query.where(records.c.kind==kind)
    with engine.connect() as c: row=c.execute(query).first()
    if not row: raise KeyError(id)
    return json.loads(row[0])

def list_records(kind,limit=100):
    with engine.connect() as c:
        rows=c.execute(select(records.c.payload).where(records.c.kind==kind).order_by(records.c.created_at.desc()).limit(limit)).all()
    return [json.loads(r[0]) for r in rows]

def list_prefix(kind,prefix,limit=1000):
    """Records of one kind whose id starts with prefix, oldest id first (revision histories)."""
    escaped=prefix.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
    with engine.connect() as c:
        rows=c.execute(select(records.c.payload).where(records.c.kind==kind)
                       .where(records.c.id.like(escaped+'%',escape='\\')).order_by(records.c.id).limit(limit)).all()
    return [json.loads(r[0]) for r in rows]
