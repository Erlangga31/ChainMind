#!/usr/bin/env python3
"""CDK application entry point for ChainMind infrastructure."""

from aws_cdk import App
from chainmind_stack import ChainMindStack

app = App()
ChainMindStack(app, "ChainMindStack")
app.synth()
