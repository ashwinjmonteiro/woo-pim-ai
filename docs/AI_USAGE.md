# AI enrichment usage

AI enrichment is available in the **AI Enrich** tab and through `POST /ai/enrich`. The default `LLM_PROVIDER=mock` runs a deterministic local tool workflow, so descriptions, tags, categories, and traces can be explored without API credentials. Set `LLM_PROVIDER=groq` with `GROQ_API_KEY`, or `LLM_PROVIDER=ollama` with a local Ollama server, to use a real model.

Enable **Save product to catalog** in the UI, or call `/ai/enrich?persist=true`, to create a product draft from the enriched result. The API response includes the generated SKU and saved product under `persisted`.

WooCommerce synchronization is configured separately from AI. `WOO_MODE=mock` (the default) uses the seeded in-memory fake WooCommerce store for push, pull, retries, and webhook demonstrations. Set `WOO_MODE=live` and provide live store URL and credentials to connect to a real WooCommerce instance. See the README environment variable table for all settings.
