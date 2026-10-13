"""Deterministic keyword-driven function-calling mock."""

import json
from typing import Any

from src.llm.base import ChatResponse, ToolCall


class MockLLMClient:
    """Produce repeatable enrichment tool calls without network access."""

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatResponse:
        """Return enrichment calls using the latest product and prior tool outputs."""
        del tools
        user = next((message.get("content", "") for message in messages if message.get("role") == "user"), "")
        context = json.loads(user) if user else {}
        product = context.get("product", context)
        title = str(product.get("title", "Product"))
        description = self._description(title)
        definitions = context.get("definitions", [])
        categories = context.get("categories", [])
        tool_results = [message.get("name") for message in messages if message.get("role") == "tool"]
        if not tool_results:
            calls = [
                ("generate_description", {"title": title, "context": product}),
                ("suggest_tags", {"title": title, "description": description}),
                ("extract_attributes", {"title": title, "description": description, "definitions": definitions}),
                ("categorize", {"title": title, "description": description, "categories": categories}),
            ]
        else:
            calls = []
        return ChatResponse(tool_calls=[ToolCall(f"mock-{index}", name, json.dumps(args)) for index, (name, args) in enumerate(calls)])

    @staticmethod
    def _description(title: str) -> str:
        base = f"Discover the thoughtful design of {title}, created to bring dependable performance and everyday convenience to your routine. Carefully selected materials and practical details help this product deliver a comfortable, reliable experience at home, at work, or on the go. Its versatile style fits easily into your existing setup, while straightforward operation makes it simple to enjoy from the moment it arrives. Whether you are upgrading your essentials or choosing a useful gift, {title} offers a balanced combination of quality, function, and value. Add a capable, well considered option to your collection and enjoy dependable performance for the tasks that matter each day. The careful finish and useful design make it a practical addition for people who appreciate comfort, lasting value, and a consistently dependable experience during busy days."
        return base

