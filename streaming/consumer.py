# streaming/consumer.py
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import requests
from confluent_kafka import Consumer, KafkaError, KafkaException, TopicPartition
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()

TOPIC = "corpus-doc-events"
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2
retry_counts = defaultdict(int)

conf = {
    "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
    "security.protocol": os.environ["KAFKA_SECURITY_PROTOCOL"],
    "sasl.mechanism": os.environ["KAFKA_SASL_MECHANISM"],
    "sasl.username": os.environ["KAFKA_SASL_USERNAME"],
    "sasl.password": os.environ["KAFKA_SASL_PASSWORD"],

    # If NOT using the environment variable, explicitly point to the CA here:
    'ssl.ca.location': os.environ["KAFKA_SASL_CA_LOCATION"],
    'group.id': "standalone-consumer-group",
    'enable.auto.commit': False,
    'auto.offset.reset': 'earliest'
}

AIRFLOW_BASE_URL = os.environ.get("AIRFLOW_BASE_URL", "http://localhost:8081")
AIRFLOW_USER = os.environ.get("AIRFLOW_USER", "admin")
AIRFLOW_PASSWORD = os.environ.get("AIRFLOW_PASSWORD", "admin")
DAG_ID = "ingest_docs"

def trigger_dag_run(dag_id: str = DAG_ID) -> str:
    dag_run_id = f"kafka_triggered__{uuid.uuid4()}"
    resp = requests.post(
        f"{AIRFLOW_BASE_URL}/api/v1/dags/{dag_id}/dagRuns",
        json={
            "dag_run_id": dag_run_id,
            "logical_date": datetime.now(timezone.utc).isoformat(),
        },
        auth=HTTPBasicAuth(AIRFLOW_USER, AIRFLOW_PASSWORD),
        timeout=10,
    )
    resp.raise_for_status()
    print(f"Triggered DAG run: {resp.json()['dag_run_id']}")
    return resp.json()["dag_run_id"]


def build_consumer() -> Consumer:
    consumer = Consumer(conf)
    consumer.subscribe([TOPIC])

    return consumer


def run(consumer: Consumer):
    try:
        while True:
            # poll(timeout) expects seconds. 
            # 1.0 means it will block for up to 5 second waiting for a message.
            msg = consumer.poll(timeout=5.0)

            if msg is None:
                # Timeout reached with no new messages
                print("No message received within the timeout window...")
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    # End of partition event
                    print(f"Reached end of partition: {msg.topic()} [{msg.partition()}]")
                else:
                    raise KafkaException(msg.error())
            else:
                # Successfully received message
                print(f"Received message: {msg.value().decode('utf-8')} from key: {msg.key()}")
                offset_key = (msg.topic(), msg.partition(), msg.offset())
                try:
                    trigger_dag_run(DAG_ID)
                    consumer.commit(msg)
                    retry_counts.pop(offset_key, None)
                except Exception as e:
                    retry_counts[offset_key] += 1
                    attempt = retry_counts[offset_key]
                    print(f"Trigger failed (attempt {attempt}/{MAX_RETRIES}): {e}")
                    if attempt >= MAX_RETRIES:
                        print(f"Giving up on offset {msg.offset()} after {MAX_RETRIES} attempts — committing past it.")
                        consumer.commit(msg)
                        retry_counts.pop(offset_key, None)
                    else:
                        time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                        consumer.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))
                    raise
    except KeyboardInterrupt:
        print("Aborted by user.")
    finally:
        consumer.close()

if __name__ == "__main__":
    consumer = build_consumer()
    run(consumer)
