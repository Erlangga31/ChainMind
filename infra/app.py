#!/usr/bin/env python3
"""CDK application entry point for ChainMind infrastructure."""

from pathlib import Path

from aws_cdk import App, Aspects
from cdk_nag import AwsSolutionsChecks
from chainmind_stack import ChainMindStack
from lambda_package import prepare_lambda_package

app = App()
project_root = Path(__file__).resolve().parents[1]
lambda_asset = prepare_lambda_package(project_root)
stack = ChainMindStack(app, "ChainMindStack", lambda_asset=lambda_asset)
Aspects.of(app).add(AwsSolutionsChecks())
stack.add_nag_suppressions()
app.synth()
