from chainmind.core.master_data import MaterialRecord
from chainmind.integrations.aws.master_data import DynamoDBMasterDataStore


class FakeDynamoTable:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, object]] = {}

    def put_item(self, *, Item: dict[str, object]) -> None:
        self.items[str(Item["run_id"])] = Item

    def get_item(self, *, Key: dict[str, str]) -> dict[str, object]:
        item = self.items.get(Key["run_id"])
        return {"Item": item} if item else {}


class FakeDynamoResource:
    def __init__(self, table: FakeDynamoTable) -> None:
        self.table = table

    def Table(self, _: str) -> FakeDynamoTable:
        return self.table


def test_dynamodb_master_data_persists_records_by_tenant(monkeypatch) -> None:
    import chainmind.integrations.aws.master_data as aws_master_data

    table = FakeDynamoTable()
    monkeypatch.setattr(
        aws_master_data.boto3,
        "resource",
        lambda *_args, **_kwargs: FakeDynamoResource(table),
    )
    store = DynamoDBMasterDataStore("chainmind-events", "us-east-1")
    material = MaterialRecord(
        component_id="board-1",
        component_name="Controller board",
        plant="Plant 1",
        current_stock=50,
        daily_consumption=10,
        line_stoppage_cost_per_day=1000,
        purchase_quantity=100,
    )

    store.put("materials", "tenant-a", material)

    assert store.get("materials", "tenant-a", "board-1") == material
    assert store.get("materials", "tenant-b", "board-1") is None
    assert "MASTER#tenant-a#materials#board-1" in table.items
    assert "MASTER#tenant-a#bootstrap" in table.items
