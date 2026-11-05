"""Retry vector synchronization after a graph merge. Never mutates Neo4j or MongoDB."""
from app.modules.kg_import.config import Settings
from app.modules.kg_import.adapters.neo4j import Neo4jKGStore
from app.modules.kg_import.entity_vector import QdrantEntityIndex
from neo4j import GraphDatabase

def main():
    settings=Settings.from_env();index=QdrantEntityIndex(settings.entity_embedding);count=0
    try:
        with GraphDatabase.driver(settings.neo4j_uri,auth=(settings.neo4j_username,settings.neo4j_password)) as driver:
            graph=Neo4jKGStore(driver,settings.neo4j_database);after=''
            while True:
                rows=graph.list_entities(after,500)
                if not rows:break
                after=rows[-1]['id']
                for row in rows:
                    ids=row.get('merge_member_ids')
                    if ids:
                        index.delete_entities(list(set(ids+[row['id']])));index.upsert_entities([row]);count+=1
        print(f'Synchronized {count} merged entities')
    finally:index.close()
if __name__=='__main__':main()
