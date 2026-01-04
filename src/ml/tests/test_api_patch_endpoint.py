def test_apply_patch_partial_deck_ok(api_client):
    client = api_client

    body = {
        "game": "magic",
        "deck": {
            "deck_id": "ex1",
            "format": "Modern",
            "partitions": [{"name": "Main", "cards": [{"name": "Lightning Bolt", "count": 4}]}],
        },
        "patch": {
            "ops": [
                {
                    "op": "add_card",
                    "partition": "Main",
                    "card": "Lava Spike",
                    "count": 1,
                }
            ]
        },
    }

    r = client.post("/v1/deck/apply_patch", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["is_valid"] is True
    assert data["deck"] is not None
