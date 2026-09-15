"""Independent expected bootstrap policies; no AWS or environment access."""

import json
from urllib.parse import unquote


def canonical_policy(value):
    if isinstance(value, str):
        value = json.loads(unquote(value))

    def normalize(item):
        if isinstance(item, dict):
            return {key: normalize(val) for key, val in sorted(item.items())}
        if isinstance(item, list):
            return sorted(
                (normalize(val) for val in item), key=lambda val: json.dumps(val, sort_keys=True)
            )
        return item

    return normalize(value)


def boundary_policy(account, region):
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:ConditionCheckItem",
                    "dynamodb:Query",
                    "dynamodb:DescribeStream",
                    "dynamodb:GetRecords",
                    "dynamodb:GetShardIterator",
                ],
                "Resource": [f"arn:aws:dynamodb:{region}:{account}:table/ai-interview-*"],
            },
            {"Effect": "Allow", "Action": ["dynamodb:ListStreams"], "Resource": ["*"]},
            {
                "Effect": "Allow",
                "Action": [
                    "sqs:SendMessage",
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                ],
                "Resource": [f"arn:aws:sqs:{region}:{account}:ai-interview-*"],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": [
                    f"arn:aws:logs:{region}:{account}:log-group:/aws/lambda/ai-interview-*:*"
                ],
            },
            {
                "Effect": "Allow",
                "Action": ["lambda:InvokeFunction"],
                "Resource": [
                    f"arn:aws:lambda:{region}:{account}:function:ai-interview-*-dispatcher:recovery"
                ],
            },
        ],
    }


def trust_policy(provider, subject):
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Principal": {"Federated": provider},
                "Condition": {
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                        "token.actions.githubusercontent.com:sub": subject,
                    }
                },
            }
        ],
    }
