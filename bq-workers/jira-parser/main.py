# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os

from flask import Flask, request

import shared

app = Flask(__name__)


@app.route("/", methods=["POST"])
def index():
    """
    Receives messages from a push subscription from Pub/Sub.
    Parses the message, and inserts it into BigQuery.
    """
    event = None
    envelope = request.get_json()

    # Check that data has been posted
    if not envelope:
        raise Exception("Expecting JSON payload")
    # Check that message is a valid pub/sub message
    if "message" not in envelope:
        raise Exception("Not a valid Pub/Sub Message")
    msg = envelope["message"]

    if "attributes" not in msg:
        raise Exception("Missing pubsub attributes")

    try:
        attr = msg["attributes"]
        # Header Event info
        if "headers" in attr:
            headers = json.loads(attr["headers"])
            event = process_jira_event(headers, msg)

        # [Do not edit below]
        shared.insert_row_into_bigquery(event)

    except Exception as e:
        entry = {
            "severity": "WARNING",
            "msg": "Data not saved to BigQuery",
            "errors": str(e),
            "json_payload": envelope
        }
        print(json.dumps(entry))

    return "", 204


def process_jira_event(headers, msg):
    signature = headers["X-Atlassian-Webhook-Identifier"]
    metadata = json.loads(base64.b64decode(
        msg["data"]).decode("utf-8").strip())
    event_type = metadata["webhookEvent"]
    print(metadata)

    types = {"jira:issue_created",
             "jira:issue_updated",
             "jira:issue_deleted"}

    if event_type not in types:
        raise Exception("Unsupported Jira event: '%s'" % event_type)

    if event_type == "jira:issue_created":
        time_created = generate_time()
        e_id = signature

    if event_type == "jira:issue_updated" and metadata["issue"]["fields"]["status"]["name"] == "Done":
        time_created = generate_time()
        e_id = signature

    if event_type == "jira:issue_deleted":
        time_created = generate_time()
        e_id = signature

    # [TODO: Parse the msg data to map to the event object below]
    jira_event = {
        "event_type": event_type,  # Event type, eg "push", "pull_reqest", etc
        "id": e_id,  # Object ID, eg pull request ID
        "metadata": json.dumps(metadata),  # The body of the msg
        "time_created": time_created,  # The timestamp of with the event
        "signature": signature,  # The unique event signature
        "msg_id": msg["message_id"],  # The pubsub message id
        "source": "jira",  # The name of the source, eg "github"
    }

    return jira_event


def generate_time():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+00:00")


if __name__ == "__main__":
    PORT = int(os.getenv("PORT")) if os.getenv("PORT") else 8080

    # This is used when running locally. Gunicorn is used to run the
    # application on Cloud Run. See entrypoint in Dockerfile.
    app.run(host="127.0.0.1", port=PORT, debug=True)
