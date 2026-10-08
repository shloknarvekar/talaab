"""Confirm this AWS account can call Claude on Amazon Bedrock in us-west-2.

Usage (needs AWS credentials, e.g. after `aws configure`):
    pip install -r backend/scripts/requirements.txt
    python backend/scripts/check_bedrock.py

Optional env vars:
    AWS_REGION        default us-west-2
    BEDROCK_MODEL_ID  default us.anthropic.claude-opus-5-5 (inference profile; Opus 5.5 has no
                      on-demand base-model access, so the bare anthropic.* id does not work)

Uses the Converse API, the same path the Strands plan agent uses. It (1) lists the Anthropic
inference profiles in the region, (2) shows the account's Bedrock token quota for the model,
(3) sends one tiny prompt (a fraction of a cent). Exit code 0 = access works.
"""
import os
import sys

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

REGION = os.environ.get("AWS_REGION", "us-west-2")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-opus-5-5")

HOW_TO_ENABLE = f"""
How to fix:
  1. Credentials: run `aws configure` and check `aws sts get-caller-identity`.
  2. IAM: the identity needs bedrock:InvokeModel / bedrock:InvokeModelWithResponseStream.
  3. Quota: new AWS accounts can start with Bedrock token quotas of 0, so every call fails with
     "Operation not allowed". A Service Quotas increase request is rejected (it only accepts values
     above the AWS default), so open a free Support case: Support Center -> Create case ->
     Account and billing -> Other Account Issues, asking AWS to lift the new-account restriction.
  4. Anthropic models need a one-time use-case form: Bedrock console -> Playground -> pick Claude.
  5. Try another inference profile from the listing above, e.g. BEDROCK_MODEL_ID=us.anthropic.claude-haiku-5-5
"""


def list_anthropic() -> None:
    bedrock = boto3.client("bedrock", region_name=REGION)
    try:
        profiles = bedrock.list_inference_profiles()["inferenceProfileSummaries"]
    except NoCredentialsError:
        print("No AWS credentials found.")
        print(HOW_TO_ENABLE)
        sys.exit(2)
    except (ClientError, BotoCoreError) as e:
        print(f"Could not list inference profiles ({e}); continuing.")
        return
    ids = sorted(p["inferenceProfileId"] for p in profiles if ".anthropic." in p["inferenceProfileId"])
    print(f"Anthropic inference profiles in {REGION}: {len(ids)}")
    for i in ids:
        if "claude-3" not in i and "-4-" not in i and "-4" != i[-2:]:
            print(f"  {i}")


def show_quota() -> None:
    model = MODEL_ID.split("anthropic.")[-1]  # e.g. claude-opus-5-5
    key = model.replace("claude-", "").replace("-", "")  # e.g. opus55
    try:
        sq = boto3.client("service-quotas", region_name=REGION)
        rows = [
            (q["QuotaName"], q["Value"])
            for page in sq.get_paginator("list_service_quotas").paginate(ServiceCode="bedrock")
            for q in page["Quotas"]
            if "tokens per minute" in q["QuotaName"]
            and key in q["QuotaName"].lower().replace(" ", "").replace(".", "").replace("claude", "").replace("anthropic", "")
        ]
    except (ClientError, BotoCoreError) as e:
        print(f"  could not read quotas ({e})")
        return
    for qname, value in rows:
        print(f"  {qname} = {value:g}")
    if rows and all(v == 0 for _, v in rows):
        print("  -> all token quotas are 0: calls will fail until AWS raises them (see step 3 below).")


def invoke() -> bool:
    rt = boto3.client("bedrock-runtime", region_name=REGION, config=Config(retries={"max_attempts": 2, "mode": "adaptive"}))
    try:
        resp = rt.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": "Reply with exactly: Talaab Bedrock OK"}]}],
            inferenceConfig={"maxTokens": 1024},
        )
    except ClientError as e:
        err = e.response["Error"]
        print(f"{err['Code']}: {err['Message']}")
        return False
    except BotoCoreError as e:
        print(f"Could not reach Bedrock in {REGION}: {e}")
        return False

    text = "".join(b.get("text", "") for b in resp["output"]["message"]["content"]).strip()
    print(f"\n{MODEL_ID} replied: {text!r}  (stopReason={resp['stopReason']})")
    print(f"usage: in={resp['usage']['inputTokens']} out={resp['usage']['outputTokens']}")
    return True


if __name__ == "__main__":
    list_anthropic()
    print(f"\nQuota check for {MODEL_ID}:")
    show_quota()
    print(f"\nInvoking {MODEL_ID} in {REGION} via Converse ...")
    if invoke():
        print("\nBedrock access OK.")
        sys.exit(0)
    print(HOW_TO_ENABLE)
    sys.exit(1)
