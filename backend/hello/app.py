"""Smoke-test Lambda: proves API Gateway -> Lambda -> CloudWatch works before the real API lands."""
import json
import os
from datetime import datetime, timezone


def lambda_handler(event, context):
    print(json.dumps({"msg": "hello called", "path": event.get("rawPath"), "requestId": getattr(context, "aws_request_id", None)}))
    body = {
        "service": "talaab",
        "message": "The sun drinks first.",
        "region": os.environ.get("AWS_REGION"),
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }
