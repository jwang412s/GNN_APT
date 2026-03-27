from neo4j import GraphDatabase
from contextlib import contextmanager
from typing import Optional

from . import config


class Neo4jClient:
    """Wrapper around the Neo4j Python driver with connection pooling."""

    def __init__(
        self,
        uri: str = config.NEO4J_URI,
        user: str = config.NEO4J_USER,
        password: str = config.NEO4J_PASSWORD,
    ):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self._driver.close()

    def verify_connectivity(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except Exception:
            return False

    def run_query(self, cypher: str, params: Optional[dict] = None) -> list[dict]:
        """Execute a read query and return list of record dicts."""
        with self._driver.session() as session:
            result = session.run(cypher, params or {})
            return [record.data() for record in result]

    def run_write(self, cypher: str, params: Optional[dict] = None) -> None:
        """Execute a write query."""
        with self._driver.session() as session:
            session.run(cypher, params or {})

    def get_graph_stats(self) -> dict:
        """Get node and edge counts by type."""
        node_counts = self.run_query(
            "MATCH (n) RETURN labels(n)[0] AS type, count(n) AS count ORDER BY count DESC"
        )
        edge_counts = self.run_query(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY count DESC"
        )
        return {
            "nodes": {r["type"]: r["count"] for r in node_counts},
            "edges": {r["type"]: r["count"] for r in edge_counts},
        }

    def get_events_per_apt(self) -> dict:
        """Get event count per APT group."""
        results = self.run_query(
            "MATCH (e:Event) WHERE e.apt IS NOT NULL "
            "RETURN e.apt AS apt, count(e) AS count ORDER BY count DESC"
        )
        return {r["apt"]: r["count"] for r in results}

    def run_schema_migration(self):
        """Create constraints and indexes for the TRAIL knowledge graph."""
        statements = [
            "CREATE CONSTRAINT domain_value IF NOT EXISTS FOR (d:Domain) REQUIRE d.value IS UNIQUE",
            "CREATE CONSTRAINT ip_value IF NOT EXISTS FOR (ip:IP) REQUIRE ip.value IS UNIQUE",
            "CREATE CONSTRAINT url_value IF NOT EXISTS FOR (u:URL) REQUIRE u.value IS UNIQUE",
            "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT asn_number IF NOT EXISTS FOR (a:ASN) REQUIRE a.number IS UNIQUE",
            "CREATE INDEX event_apt IF NOT EXISTS FOR (e:Event) ON (e.apt)",
        ]
        for stmt in statements:
            try:
                self.run_write(stmt)
            except Exception as e:
                # Constraints may already exist
                print(f"Schema migration note: {e}")
