"""Read-only comparison of one immutable snapshot with its Neo4j projection."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.kg_global.publish import label
from app.kg_global.projection import build_projection,verify_projection
from app.direct_import.service import configured_store
from app.modules.kg_import.config import Settings

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',help='Defaults to the active snapshot')
    args=parser.parse_args();store=configured_store()
    try:
        active=store.active();sid=args.snapshot or (active or {}).get('id')
        if not sid:raise ValueError('Chưa có snapshot active; chỉ định --snapshot.')
        projection=build_projection(store.snapshot(sid));settings=Settings.from_env()
        from neo4j import GraphDatabase
        with GraphDatabase.driver(settings.neo4j_uri,auth=(settings.neo4j_username,settings.neo4j_password)) as driver:
            with driver.session(database=settings.neo4j_database) as session:
                result=session.execute_read(lambda tx:verify_projection(tx,label(sid),projection))
        print(json.dumps({'snapshot_id':sid,**result},ensure_ascii=False,indent=2))
    finally:store.db.close()
