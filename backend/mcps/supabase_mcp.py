import json
import os

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

_supabase_available = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)

if _supabase_available:
    try:
        from supabase import create_client, Client
    except ImportError:
        _supabase_available = False


class SupabaseMCP:
    def __init__(self):
        self._client = None

    def _get_client(self):
        if not _supabase_available:
            raise RuntimeError("Supabase non configuré. Vérifiez SUPABASE_URL et SUPABASE_SERVICE_KEY.")
        if self._client is None:
            self._client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        return self._client

    def _apply_filters(self, query, filters_json: str):
        """Applique les filtres JSON sur une query Supabase.

        filters_json format: [{"column": "id", "op": "eq", "value": "123"}]
        Opérateurs supportés : eq, neq, gt, gte, lt, lte, like, ilike, is, in
        """
        if not filters_json:
            return query
        try:
            filters = json.loads(filters_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"filters_json invalide : {e}")
        for f in filters:
            col = f["column"]
            op = f["op"]
            val = f["value"]
            if op == "eq":
                query = query.eq(col, val)
            elif op == "neq":
                query = query.neq(col, val)
            elif op == "gt":
                query = query.gt(col, val)
            elif op == "gte":
                query = query.gte(col, val)
            elif op == "lt":
                query = query.lt(col, val)
            elif op == "lte":
                query = query.lte(col, val)
            elif op == "like":
                query = query.like(col, val)
            elif op == "ilike":
                query = query.ilike(col, val)
            elif op == "is":
                query = query.is_(col, val)
            elif op == "in":
                query = query.in_(col, val)
            else:
                raise ValueError(f"Opérateur inconnu : {op}")
        return query

    # ─── READ ────────────────────────────────────────────────────────────────

    def query_table(self, table: str, filters_json: str = "", limit: int = 20, columns: str = "*") -> str:
        """SELECT avec filtres optionnels sur une table Supabase."""
        try:
            client = self._get_client()
            query = client.table(table).select(columns).limit(limit)
            query = self._apply_filters(query, filters_json)
            response = query.execute()
            rows = response.data
            if not rows:
                return f"Aucun résultat dans la table '{table}'."
            return json.dumps(rows, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Erreur Supabase query_table: {str(e)}"

    def list_tables(self) -> str:
        """Liste les tables de la base via information_schema."""
        try:
            client = self._get_client()
            response = (
                client.table("information_schema.tables")
                .select("table_name")
                .eq("table_schema", "public")
                .execute()
            )
            tables = [row["table_name"] for row in response.data]
            if not tables:
                return "Aucune table trouvée dans le schéma public."
            return "Tables disponibles :\n" + "\n".join(f"  - {t}" for t in sorted(tables))
        except Exception as e:
            return f"Erreur Supabase list_tables: {str(e)}"

    # ─── WRITE ───────────────────────────────────────────────────────────────

    def insert_row(self, table: str, data_json: str) -> str:
        """INSERT une ligne dans une table. data_json = JSON object."""
        try:
            client = self._get_client()
            data = json.loads(data_json)
            response = client.table(table).insert(data).execute()
            inserted = response.data
            return f"Insertion réussie dans '{table}' : {json.dumps(inserted, ensure_ascii=False)}"
        except Exception as e:
            return f"Erreur Supabase insert_row: {str(e)}"

    def update_row(self, table: str, filters_json: str, data_json: str) -> str:
        """UPDATE les lignes matchant les filtres avec les données fournies."""
        try:
            client = self._get_client()
            data = json.loads(data_json)
            query = client.table(table).update(data)
            query = self._apply_filters(query, filters_json)
            response = query.execute()
            updated = response.data
            return f"Mise à jour réussie dans '{table}' : {json.dumps(updated, ensure_ascii=False)}"
        except Exception as e:
            return f"Erreur Supabase update_row: {str(e)}"

    def delete_row(self, table: str, filters_json: str) -> str:
        """DELETE les lignes matchant les filtres."""
        try:
            client = self._get_client()
            query = client.table(table).delete()
            query = self._apply_filters(query, filters_json)
            response = query.execute()
            deleted = response.data
            return f"Suppression réussie dans '{table}' : {len(deleted)} ligne(s) affectée(s)."
        except Exception as e:
            return f"Erreur Supabase delete_row: {str(e)}"

    # ─── SQL ─────────────────────────────────────────────────────────────────

    def run_sql(self, query: str) -> str:
        """Exécute une requête SQL brute via la fonction RPC pg_query si disponible."""
        try:
            client = self._get_client()
            response = client.rpc("pg_query", {"query": query}).execute()
            result = response.data
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Erreur Supabase run_sql: {str(e)}"
