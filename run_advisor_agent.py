"""Run the AWS Cloud Advisor agent against the local MCP server.

Requires OPENAI_API_KEY in the environment (never hardcode it).
"""
import asyncio
import os
import sys

from agents import Agent, Runner
from agents.mcp import MCPServerStdio

INSTRUCTIONS = (
    "You are a careful AWS cost and architecture advisor. "
    "ALWAYS call the available tools to get real data before answering "
    "any question about cost, idle resources, or Well-Architected findings. "
    "Never estimate or guess numbers - only report what the tools return. "
    "When you find an issue, briefly explain why it matters, citing the "
    "specific AWS Well-Architected pillar it relates to."
)

QUESTIONS = [
    "What has my AWS account spent money on in the last 7 days?",
    "Do I have any wasted resources I'm paying for right now?",
    "Run a basic Well-Architected check and tell me what to fix first.",
]


async def main() -> None:
    async with MCPServerStdio(
        params={"command": sys.executable, "args": ["aws_advisor_mcp_server.py"]},
    ) as aws_tools:
        advisor = Agent(
            name="AWS Cloud Advisor",
            instructions=INSTRUCTIONS,
            mcp_servers=[aws_tools],
        )
        for q in QUESTIONS:
            print(f"\n{'=' * 70}\nQ: {q}\n{'=' * 70}")
            result = await Runner.run(advisor, q)
            print(result.final_output)


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("Set OPENAI_API_KEY first (export OPENAI_API_KEY=...).")
    asyncio.run(main())
