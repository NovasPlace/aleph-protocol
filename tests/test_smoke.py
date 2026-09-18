import os
import tempfile

TEST_DIR = tempfile.mkdtemp(prefix="aleph-ci-")
os.environ["ALEPH_OPERATOR"] = "ci"
os.environ["ALEPH_ROOT_SEED"] = "ci-root-seed"
os.environ["ALEPH_NODE_ID"] = "aleph-ci"
os.environ["ALEPH_NODE_URL"] = "http://testserver"
os.environ["ALEPH_DATA_DIR"] = TEST_DIR
os.environ["DB_PATH"] = os.path.join(TEST_DIR, "aleph.db")
os.environ["ALEPH_FEDERATION_ENABLED"] = "true"
os.environ["ALEPH_SEED_PEERS"] = ""

from fastapi.testclient import TestClient
import node


def test_nodeus_smoke():
    with TestClient(node.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        admin_headers = {"X-API-Key": "ci-root-seed"}
        provision = client.post(
            "/keys",
            headers=admin_headers,
            json={"agent_id": "ci-agent", "label": "CI Agent"},
        )
        assert provision.status_code == 200
        agent_key = provision.json()["key"]
        agent_headers = {"X-API-Key": agent_key}

        deposit = client.post(
            "/memories",
            headers=agent_headers,
            json={
                "type": "factual",
                "content": "ALEPH CI federation smoke memory",
                "tags": ["ci", "federation"],
                "source": "ci",
                "confidence": 1.0,
            },
        )
        assert deposit.status_code == 200
        chunk_id = deposit.json()["chunk_id"]

        search = client.post(
            "/memories/search",
            headers=agent_headers,
            json={"query": "", "tags": [], "limit": 10, "threshold": 0.0},
        )
        assert search.status_code == 200
        assert any(r["chunk_id"] == chunk_id for r in search.json()["results"])

        v1_query = client.post(
            "/aleph/v1/query",
            headers=agent_headers,
            json={"query": "", "tags": [], "limit": 10, "threshold": 0.0},
        )
        assert v1_query.status_code == 200

        export = client.get("/federation/export?after_seq=0&limit=10")
        assert export.status_code == 200
        assert any(c["chunk_id"] == chunk_id for c in export.json()["chunks"])

        status = client.get("/federation/status", headers=admin_headers)
        assert status.status_code == 200
        assert status.json()["enabled"] is True
