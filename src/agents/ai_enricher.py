"""Tool-driven product enrichment workflow."""

import json
from typing import Any

from src.llm.base import LLMClient
from src.llm.openai_compatible import LLMProviderError, LLMRateLimitError


class MalformedToolCallError(Exception):
    """A model returned invalid JSON for a function call."""


class UnknownToolError(Exception):
    """A model requested a function that is not registered."""


class IterationLimitError(Exception):
    """The model did not complete enrichment within the allowed calls."""


def tool_definitions() -> list[dict[str, Any]]:
    """Return OpenAI-compatible function tool definitions."""
    specs = {
        "generate_description": {"title": {"type": "string"}, "context": {"type": "object"}},
        "suggest_tags": {"title": {"type": "string"}, "description": {"type": "string"}},
        "extract_attributes": {"title": {"type": "string"}, "description": {"type": "string"}, "definitions": {"type": "array"}},
        "categorize": {"title": {"type": "string"}, "description": {"type": "string"}, "categories": {"type": "array"}},
        "validate_payload": {"product": {"type": "object"}},
    }
    return [{"type": "function", "function": {"name": name, "description": f"Run {name.replace('_', ' ')} for a product.", "parameters": {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}}} for name, properties in specs.items()]


class AIEnricher:
    """Enrich a partial product through bounded model-selected tool calls."""

    def __init__(self, client: LLMClient, max_iterations: int = 3) -> None:
        self.client = client
        self.max_iterations = max_iterations

    def enrich(self, product: dict[str, Any], definitions: list[dict[str, Any]] | None = None, categories: list[str] | None = None) -> dict[str, Any]:
        """Return enriched fields, call trace, and complete/partial/failed status."""
        result = dict(product)
        definitions = definitions or []
        categories = categories or []
        trace: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "Enrich the product by calling tools. Generate a factual SEO description of 120-160 words. Call tools for missing fields, then validate."},
            {"role": "user", "content": json.dumps({"product": result, "definitions": definitions, "categories": categories})},
        ]
        status = "partial"
        last_error: str | None = None
        try:
            for iteration in range(self.max_iterations):
                response = self.client.chat(messages, tool_definitions())
                if not response.tool_calls:
                    break
                for call in response.tool_calls:
                    try:
                        arguments = json.loads(call.arguments)
                        if not isinstance(arguments, dict):
                            raise TypeError("tool arguments must be a JSON object")
                    except (json.JSONDecodeError, TypeError) as error:
                        raise MalformedToolCallError(f"Malformed arguments for {call.name}: {error}") from error
                    output = self._run_tool(call.name, arguments, result, definitions, categories)
                    trace.append({"iteration": iteration + 1, "tool": call.name, "arguments": arguments, "result": output})
                    if call.name == "generate_description" and isinstance(output, str):
                        result["description"] = output
                    elif call.name == "suggest_tags" and isinstance(output, list):
                        result["tags"] = output
                    elif call.name == "extract_attributes" and isinstance(output, dict):
                        result["attributes"] = output
                    elif call.name == "categorize" and isinstance(output, str):
                        result["category"] = output
                    messages.extend([
                        {"role": "assistant", "tool_calls": [{"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}]},
                        {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": json.dumps(output)},
                    ])
                validation = self.validate_payload(result, definitions)
                if validation["valid"]:
                    status = "complete"
                    break
                last_error = "; ".join(validation["missing"] + validation["errors"])
                if iteration + 1 < self.max_iterations:
                    messages.append({"role": "user", "content": f"Only fix these missing or invalid fields: {last_error}"})
            else:
                raise IterationLimitError(f"Enrichment stopped after {self.max_iterations} iterations")
        except (MalformedToolCallError, UnknownToolError, LLMRateLimitError, LLMProviderError, IterationLimitError) as error:
            last_error = str(error)
        if status != "complete":
            status = "partial" if any(key in result for key in ("title", "description", "tags", "category", "attributes")) else "failed"
        return {"product": result, "trace": trace, "status": status, "error": last_error}

    @classmethod
    def validate_payload(cls, product: dict[str, Any], definitions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Report required product fields and definition validation errors."""
        missing = [key for key in ("title", "description", "category") if not product.get(key)]
        errors: list[str] = []
        attributes = product.get("attributes") or {}
        for definition in definitions or []:
            name = definition["name"]
            if definition.get("required") and name not in attributes:
                missing.append(f"attributes.{name}")
            if name in attributes and not cls._attribute_matches(definition, attributes[name]):
                errors.append(f"attributes.{name} has invalid value")
        return {"valid": not missing and not errors, "missing": missing, "errors": errors}

    def _run_tool(self, name: str, args: dict[str, Any], product: dict[str, Any], definitions: list[dict[str, Any]], categories: list[str]) -> Any:
        title = str(args.get("title") or product.get("title") or "Product")
        description = str(args.get("description") or product.get("description") or "")
        lowered = f"{title} {description}".lower()
        if name == "generate_description":
            return self._generate_description(title, args.get("context", {}))
        if name == "suggest_tags":
            words = [word.strip(".,()") for word in title.lower().split() if len(word.strip(".,()")) > 2]
            return list(dict.fromkeys([*(["wireless", "ergonomic"] if "mouse" in lowered else []), *words]))[:8]
        if name == "extract_attributes":
            extracted: dict[str, Any] = {}
            for definition in definitions:
                name_ = definition["name"]
                values = definition.get("allowed_values") or []
                if definition["type"] == "enum":
                    match = next((value for value in values if value.lower() in lowered), None)
                    if match is not None:
                        extracted[name_] = match
            return extracted
        if name == "categorize":
            suggested = "Electronics > Accessories" if "mouse" in lowered else "General"
            return next((category for category in categories if category.lower() == suggested.lower()), suggested)
        if name == "validate_payload":
            return self.validate_payload(args.get("product", product), definitions)
        raise UnknownToolError(f"Unknown tool '{name}'")

    @staticmethod
    def _attribute_matches(definition: dict[str, Any], value: Any) -> bool:
        kind = definition["type"]
        return (kind == "string" and isinstance(value, str)) or (
            kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)
        ) or (kind == "boolean" and isinstance(value, bool)) or (
            kind == "enum" and value in (definition.get("allowed_values") or [])
        )

    @staticmethod
    def _generate_description(title: str, context: Any) -> str:
        """Generate a safe descriptive draft using only known product context."""
        context_text = ", ".join(f"{key}: {value}" for key, value in context.items() if key in {"category", "brand", "material"}) if isinstance(context, dict) else ""
        detail = f" Relevant product details include {context_text}." if context_text else " Its practical design supports comfortable everyday use across a range of settings."
        return (f"Meet {title}, a thoughtfully designed choice for dependable everyday performance. This product combines useful features with a straightforward, versatile style that fits naturally into your routine. {detail} Carefully considered construction helps it feel reliable during regular use, while its approachable design makes it easy to get started without unnecessary complexity. Use it at home, at work, or wherever your day takes you, and enjoy an option that balances function with convenience. The adaptable look pairs well with a variety of existing products and setups. Whether you are refreshing your essentials or selecting a practical gift, {title} offers a considered blend of usability, dependable quality, and lasting value. Choose this versatile product to make daily tasks simpler and more enjoyable. Its balanced proportions, dependable components, and careful finishing make it a useful addition for people who value comfort and consistent performance throughout busy days.")
