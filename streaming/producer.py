# streaming/producer.py
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from confluent_kafka import Producer
from dotenv import load_dotenv

load_dotenv()

TOPIC = "corpus-doc-events"
CORPUS_DIR = Path("corpus/clean")
MANIFEST_PATH = Path("streaming/.manifest.json")


conf = {
    "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
    "security.protocol": os.environ["KAFKA_SECURITY_PROTOCOL"],
    "sasl.mechanism": os.environ["KAFKA_SASL_MECHANISM"],
    "sasl.username": os.environ["KAFKA_SASL_USERNAME"],
    "sasl.password": os.environ["KAFKA_SASL_PASSWORD"],

    # If NOT using the environment variable, explicitly point to the CA here:
    'ssl.ca.location': os.environ["KAFKA_SASL_CA_LOCATION"]
}

def delivery_report(err, msg):
    if err is not None:
        print(f"Delivery failed for {msg.key()}: {err}")
    else:
        print(f"Delivered to {msg.topic()} [partition {msg.partition()}] @ offset {msg.offset()}")

def make_event(doc_id: str, action: str) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "doc_id": doc_id,
        "action": action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {}


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


def find_changed_docs(manifest: dict) -> list[dict]:
    events = []
    for path in CORPUS_DIR.glob("*.txt"):
        doc_id = path.stem
        mtime = path.stat().st_mtime

        if doc_id not in manifest:
            action = "created"
        elif mtime > manifest[doc_id]:
            action = "updated"
        else:
            continue  # unchanged since last run

        events.append(make_event(doc_id, action))
        manifest[doc_id] = mtime

    return events


def main():
    manifest = load_manifest()
    events = find_changed_docs(manifest)

    if not events:
        print("No new or changed documents found.")
        return


    producer = Producer(conf)

    producer = Producer(conf)
    for event in events:
        producer.produce(
            topic=TOPIC,
            key=event["doc_id"],
            value=json.dumps(event),
            callback=delivery_report,
        )
        producer.poll(0)

    producer.flush()  # block until all messages are delivered
    save_manifest(manifest)
    print(f"Published {len(events)} event(s).")

if __name__ == "__main__":
    main()
