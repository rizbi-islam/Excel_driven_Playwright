"""
app/database/models/collection.py

Full Postman-parity collection model:
- Collection-level auth, variables, pre/post scripts
- Per-request auth (inherit/override), pre/post scripts
- Collection runner: execute all requests sequentially, return full report
"""
import json
from app.database.connection import execute, query, query_one


def _j(v):
    if v is None: return None
    return json.dumps(v) if isinstance(v, (dict, list)) else v

def _parse(v, default=None):
    if v is None: return default
    if isinstance(v, (dict, list)): return v
    try: return json.loads(v)
    except: return default


class CollectionModel:

    @staticmethod
    def all_for_user(owner_id: int) -> list:
        return query(
            "SELECT c.*, COUNT(r.id) AS request_count "
            "FROM collections c "
            "LEFT JOIN collection_requests r ON c.id=r.collection_id "
            "WHERE c.owner_id=%s GROUP BY c.id ORDER BY c.created_at DESC",
            (owner_id,)
        )

    @staticmethod
    def get(col_id: int, owner_id: int) -> dict | None:
        row = query_one(
            "SELECT * FROM collections WHERE id=%s AND owner_id=%s",
            (col_id, owner_id)
        )
        if not row: return None
        r = dict(row)
        r['variables'] = _parse(r.get('variables'), [])
        return r

    @staticmethod
    def create(owner_id: int, data: dict) -> int:
        return execute(
            "INSERT INTO collections(owner_id,name,description,auth_type,auth_token,"
            "auth_key_name,variables,pre_request_script,tests_script) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (owner_id,
             data.get('name','New Collection'),
             data.get('description',''),
             data.get('auth_type','none'),
             data.get('auth_token',''),
             data.get('auth_key_name','X-API-Key'),
             _j(data.get('variables',[])),
             data.get('pre_request_script',''),
             data.get('tests_script',''))
        )

    @staticmethod
    def update(col_id: int, owner_id: int, data: dict) -> None:
        execute(
            "UPDATE collections SET name=%s,description=%s,auth_type=%s,auth_token=%s,"
            "auth_key_name=%s,variables=%s,pre_request_script=%s,tests_script=%s "
            "WHERE id=%s AND owner_id=%s",
            (data.get('name',''),
             data.get('description',''),
             data.get('auth_type','none'),
             data.get('auth_token',''),
             data.get('auth_key_name','X-API-Key'),
             _j(data.get('variables',[])),
             data.get('pre_request_script',''),
             data.get('tests_script',''),
             col_id, owner_id)
        )

    @staticmethod
    def delete(col_id: int, owner_id: int) -> None:
        execute("DELETE FROM collections WHERE id=%s AND owner_id=%s", (col_id, owner_id))

    @staticmethod
    def duplicate(col_id: int, owner_id: int) -> int:
        col = CollectionModel.get(col_id, owner_id)
        if not col: return None
        col['name'] = col['name'] + ' (copy)'
        new_id = CollectionModel.create(owner_id, col)
        reqs = CollectionRequestModel.all_for_collection(col_id, owner_id)
        for r in reqs:
            r_data = dict(r)
            for k in ('id','collection_id','created_at'):
                r_data.pop(k, None)
            CollectionRequestModel.save(owner_id, new_id, r_data)
        return new_id


class CollectionRequestModel:

    @staticmethod
    def all_for_collection(col_id: int, owner_id: int) -> list:
        rows = query(
            "SELECT * FROM collection_requests WHERE collection_id=%s AND owner_id=%s "
            "ORDER BY sort_order ASC, id ASC",
            (col_id, owner_id)
        )
        result = []
        for row in rows:
            r = dict(row)
            for k in ('headers','body','params'):
                r[k] = _parse(r.get(k), {} if k != 'body' else None)
            result.append(r)
        return result

    @staticmethod
    def get(req_id: int, owner_id: int) -> dict | None:
        row = query_one(
            "SELECT * FROM collection_requests WHERE id=%s AND owner_id=%s",
            (req_id, owner_id)
        )
        if not row: return None
        r = dict(row)
        for k in ('headers','body','params'):
            r[k] = _parse(r.get(k), {} if k != 'body' else None)
        return r

    @staticmethod
    def save(owner_id: int, col_id: int, data: dict) -> int:
        return execute(
            "INSERT INTO collection_requests(collection_id,owner_id,name,method,url,"
            "headers,body,body_type,params,auth_type,auth_token,auth_key_name,"
            "description,pre_request_script,tests_script,sort_order) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (col_id, owner_id,
             data.get('name','') or data.get('url',''),
             (data.get('method') or 'GET').upper(),
             data.get('url',''),
             _j(data.get('headers',{})),
             _j(data.get('body')),
             data.get('body_type','none'),
             _j(data.get('params',{})),
             data.get('auth_type','inherit'),
             data.get('auth_token',''),
             data.get('auth_key_name','X-API-Key'),
             data.get('description',''),
             data.get('pre_request_script',''),
             data.get('tests_script',''),
             data.get('sort_order',0))
        )

    @staticmethod
    def update(req_id: int, owner_id: int, data: dict) -> None:
        execute(
            "UPDATE collection_requests SET name=%s,method=%s,url=%s,headers=%s,"
            "body=%s,body_type=%s,params=%s,auth_type=%s,auth_token=%s,auth_key_name=%s,"
            "description=%s,pre_request_script=%s,tests_script=%s,sort_order=%s "
            "WHERE id=%s AND owner_id=%s",
            (data.get('name',''),
             (data.get('method') or 'GET').upper(),
             data.get('url',''),
             _j(data.get('headers',{})),
             _j(data.get('body')),
             data.get('body_type','none'),
             _j(data.get('params',{})),
             data.get('auth_type','inherit'),
             data.get('auth_token',''),
             data.get('auth_key_name','X-API-Key'),
             data.get('description',''),
             data.get('pre_request_script',''),
             data.get('tests_script',''),
             data.get('sort_order',0),
             req_id, owner_id)
        )

    @staticmethod
    def delete(req_id: int, owner_id: int) -> None:
        execute(
            "DELETE FROM collection_requests WHERE id=%s AND owner_id=%s",
            (req_id, owner_id)
        )

    @staticmethod
    def reorder(col_id: int, owner_id: int, ordered_ids: list) -> None:
        for i, rid in enumerate(ordered_ids):
            execute(
                "UPDATE collection_requests SET sort_order=%s "
                "WHERE id=%s AND collection_id=%s AND owner_id=%s",
                (i, rid, col_id, owner_id)
            )
