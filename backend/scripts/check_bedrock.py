"""Confirm this AWS account can call Claude on Amazon Bedrock in us-west-2.

Usage (needs AWS credentials, e.g. after `aws configure`):
    pip install -r backend/scripts/requirements.txt
    python backend/scripts/check_bedrock.py

Optional env vars:
    AWS_REGION        default us-west-2
    BEDROCK_MODEL_ID  default anthropic.claude-opus-5-5

It (1) lists the Anthropic models Bedrock offers in the region (read-only) and
(2) sends one tiny prompt (a fraction of a cent). Exit code 0 = access works.
"""
import os
import sys

import boto3
from anthropic import AnthropicBedrockMantle, APIConnectionError, APIStatusError, NotFoundError, PermissionDeniedError
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

REGION = os.environ.get("AWS_REGION", "us-west-2")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-opus-5-5")

HOW_TO_ENABLE = f"""
How to fix:
  1. Credentials: run `aws configure` (or `aws sso login`) and check `aws sts get-caller-identity`.
  2. IAM: the identity needs bedrock:InvokeModel / bedrock:InvokeModelWithResponseStream
     (e.g. the AmazonBedrockFullAccess managed policy for the hackathon).
  3. Model access: AWS console -> Amazon Bedrock -> region {REGION} -> Model catalog
     -> pick the Anthropic Claude model -> request/enable access (first-time Anthropic use asks for
     a short use-case form). Usually approved within minutes.
  4. Try another model the listing above shows, e.g.  BEDROCK_MODEL_ID=anthropic.claude-sonnet-5-5
"""


def list_anthropic_models() -> None:
    try:
        bedrock = boto3.client("bedrock", region_name=REGION)
        models = bedrock.list_foundation_models(byProvider="Anthropic")["modelSummaries"]
    except NoCredentialsError:
        print("No AWS credentials found.")
        print(HOW_TO_ENABLE)
        sys.exit(2)
    except (ClientError, BotoCoreError) as e:
        print(f"Could not list models ({e}); continuing to the invoke test.")
        return
    print(f"Anthropic models listed in {REGION}:")
    for m in sorted(models, key=lambda m: m["modelId"]):
        print(f"  {m['modelId']:<50} {m.get('modelLifecycle', {}).get('status', '')}")


def invoke() -> bool:
    client = AnthropicBedrockMantle(aws_region=REGION)
    try:
        resp = client.messages.create(
            model=MODEL_ID,
            max_tokens=1024,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": "Reply with exactly: Talaab Bedrock OK"}],
        )
    except PermissionDeniedError as e:
        print(f"403 access denied for {MODEL_ID}: {e.message}")
        return False
    except NotFoundError as e:
        print(f"404 model not found in {REGION}: {MODEL_ID} ({e.message})")
        return False
    except APIStatusError as e:
        print(f"Bedrock returned HTTP {e.status_code}: {e.message}")
        return False
    except APIConnectionError as e:
        print(f"Could not reach Bedrock in {REGION}: {e}")
        return False

    if resp.stop_reason == "refusal":
        print("Model answered with a refusal (access works, but the prompt was declined).")
        return True
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    print(f"\n{MODEL_ID} replied: {text!r}")
    print(f"usage: in={resp.usage.input_tokens} out={resp.usage.output_tokens}")
    return True


if __name__ == "__main__":
    list_anthropic_models()
    print(f"\nInvoking {MODEL_ID} in {REGION} ...")
    if invoke():
        print("\nBedrock access OK.")
        sys.exit(0)
    print(HOW_TO_ENABLE)
    sys.exit(1)
