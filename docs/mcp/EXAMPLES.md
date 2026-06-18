# MCP Usage Examples

These walkthroughs show real interactions between a user, their AI assistant, and the The AI Counsel MCP server. All examples assume the MCP server is registered and the backend is running.

---

## Example 1: Ask the council a question

**What you say to your AI:**

> "Ask the council: what are the pros and cons of microservices architecture? Use web search."

**What happens behind the scenes:**

The AI recognizes this as a full deliberation request and calls `council_deliberate`:

```json
{
  "tool": "council_deliberate",
  "input": {
    "action": "full",
    "query": "What are the pros and cons of microservices architecture?",
    "web_search": true
  }
}
```

The MCP server streams the request through all three stages against the Council backend. After a minute or two (depending on council size and model speeds), the tool returns:

```json
{
  "conversation_id": "f8a2b3c1-...",
  "title": "Microservices: Pros and Cons",
  "stage1_responses": [
    {
      "model": "openai:gpt-4.1",
      "label": "Response A",
      "content": "Microservices offer independent deployability, team autonomy, and horizontal scalability per service. However they introduce significant operational complexity..."
    },
    {
      "model": "anthropic:claude-sonnet-4",
      "label": "Response B",
      "content": "The core tradeoff in microservices is flexibility vs complexity. On the benefits side..."
    },
    {
      "model": "groq:llama3-70b-8192",
      "label": "Response C",
      "content": "Pros: independent scaling, technology diversity, fault isolation..."
    }
  ],
  "aggregate_rankings": {
    "Response B": 1.3,
    "Response A": 2.0,
    "Response C": 2.7
  },
  "chairman_answer": "Microservices architecture offers compelling advantages for teams at scale — independent deployment, technology freedom, and fault isolation — but these benefits come at the cost of substantial operational overhead. The council's top-ranked response (Response B) correctly identifies that the decision hinges on team size and organizational maturity. Smaller teams are almost always better served by a well-structured monolith. The search results confirm this: Netflix and Uber moved to microservices only after reaching hundreds of engineers and millions of users..."
}
```

**What your AI presents to you:**

The AI surfaces the `chairman_answer` as the primary response and may offer to show you individual model responses or rankings if you ask. The top-level `cost_report` object tells you the run's total cost and per-model breakdown — surface it if the user is watching spend.

```json
"cost_report": {
  "currency": "USD",
  "total_cost": 0.002341,
  "input_tokens": 1842,
  "output_tokens": 671,
  "total_tokens": 2513,
  "total_calls": 7,
  "known_cost_calls": 7,
  "unknown_cost_calls": 0,
  "free_calls": 4,
  "has_unknown_costs": false,
  "has_estimates": true,
  "by_model": [
    {"name": "openai:gpt-4.1", "calls": 2, "total_cost": 0.0018, "estimated_calls": 0},
    {"name": "anthropic:claude-sonnet-4-6", "calls": 2, "total_cost": 0.0005, "estimated_calls": 0},
    {"name": "opencode-zen:deepseek-v4-flash-free", "calls": 2, "total_cost": 0.0, "free_calls": 2}
  ]
}
```

---

## Example 2: Configure a council for coding questions

**What you say to your AI:**

> "Set up a coding-focused council with GPT-4.1, Claude Sonnet, and Gemini Pro. Make sure full deliberation is on."

**What happens behind the scenes:**

The AI first checks what models are available:

```json
{"tool": "providers", "input": {"action": "list_models"}}
```

Response (abbreviated):
```json
{
  "models": [
    {"id": "openai:gpt-4.1", "provider": "openai", "name": "GPT-4.1"},
    {"id": "openrouter:anthropic/claude-sonnet-4", "provider": "openrouter", "name": "Claude Sonnet 4"},
    {"id": "openrouter:google/gemini-pro-1.5", "provider": "openrouter", "name": "Gemini Pro 1.5"},
    ...
  ]
}
```

The AI then maps your request to available model IDs and calls `council_settings`:

```json
{
  "tool": "council_settings",
  "input": {
    "action": "update",
    "models": [
      "openai:gpt-4.1",
      "openrouter:anthropic/claude-sonnet-4",
      "openrouter:google/gemini-pro-1.5"
    ],
    "execution_mode": "full"
  }
}
```

Response:
```json
{
  "status": "updated",
  "fields": ["council_models", "execution_mode"]
}
```

**What your AI presents to you:**

> "Your council is set. GPT-4.1, Claude Sonnet 4, and Gemini Pro 1.5 are now council members with full deliberation enabled. Your current chairman is Claude Opus 4. Ready to ask a coding question?"

Note: The AI picks the closest available model IDs. If a model you named is not configured (e.g., you have no Google API key), the AI will flag this and suggest alternatives from what is available.

---

## Example 3: Quick check with a single model

**What you say to your AI:**

> "Ask GPT-4.1 directly: what's the difference between REST and GraphQL?"

**What happens behind the scenes:**

The AI recognizes you want a direct single-model response, not a full deliberation, and calls `model_chat`:

```json
{
  "tool": "model_chat",
  "input": {
    "action": "quick",
    "query": "What's the difference between REST and GraphQL?",
    "model": "openai:gpt-4.1",
    "web_search": false
  }
}
```

This uses the one-shot `/api/ask` endpoint internally. The completed run is
saved as a conversation visible in the UI, and the response includes its
`conversation_id`. No settings are mutated.

Response:
```json
{
  "conversation_id": "7c658b52-...",
  "model": "openai:gpt-4.1",
  "response": "REST and GraphQL are both approaches to building APIs, but they differ fundamentally in how clients request data.\n\n**REST** organizes endpoints around resources (e.g., `/users/123`, `/posts`). Each endpoint returns a fixed shape of data. If you need user data plus their posts, you typically make two requests.\n\n**GraphQL** provides a single endpoint where clients specify exactly what fields they need in a query. You can fetch a user and their posts in one request, getting precisely the fields you want — nothing more.\n\n**When to use REST:** Simpler CRUD APIs, public APIs where caching is important, teams unfamiliar with GraphQL.\n\n**When to use GraphQL:** Complex, nested data requirements; mobile clients sensitive to over-fetching; rapidly evolving frontends that need flexibility.",
  "error": null,
  "web_search_used": false
}
```

**What your AI presents to you:**

The AI presents the response directly, typically as a formatted answer. Because this is `model_chat` with action `quick` (single model, no deliberation), there are no rankings or chairman synthesis — you get the raw model output immediately.

---

## Example 4: Multi-turn conversation with follow-ups

**What you say to your AI:**

> "Chat with Claude about how async/await works in Python"

**What happens behind the scenes (first call):**

The AI uses `model_chat` with action `multi_turn` to start a new conversation:

```json
{
  "tool": "model_chat",
  "input": {
    "action": "multi_turn",
    "query": "How does async/await work in Python?",
    "model": "anthropic:claude-sonnet-4"
  }
}
```

Response:
```json
{
  "conversation_id": "conv-abc-123",
  "model": "anthropic:claude-sonnet-4",
  "response": "Python's async/await is built on coroutines and an event loop...",
  "error": null,
  "web_search_used": false
}
```

**You then ask a follow-up:**

> "Can you show me a concrete example with aiohttp?"

**What happens (second call):**

The AI passes the same `conversation_id` to continue the conversation:

```json
{
  "tool": "model_chat",
  "input": {
    "action": "multi_turn",
    "query": "Can you show me a concrete example with aiohttp?",
    "model": "anthropic:claude-sonnet-4",
    "conversation_id": "conv-abc-123"
  }
}
```

The model receives the full prior conversation as context and responds with a relevant example building on its previous explanation.

**Key behavior:**
- The `conversation_id` links follow-up messages to the same conversation
- The model sees all prior user/assistant turns automatically
- No need to repeat context or re-explain — the model remembers
- For one-off questions without memory, use `model_chat` with action `quick` instead

---

## Example 5: Ask with an attached document

**What you say to your AI:**

> "Ask GPT to summarize these notes and list follow-up questions."

**What happens behind the scenes:**

If the document text is already available, the AI can pass it directly:

```json
{
  "tool": "model_chat",
  "input": {
    "action": "quick",
    "query": "Summarize the attachment and list follow-up questions.",
    "model": "openai:gpt-4.1",
    "documents": [
      {
        "name": "notes.txt",
        "mime_type": "text/plain",
        "text": "Meeting notes: Alpha approved the plan. Beta needs legal review."
      }
    ]
  }
}
```

If the source file is still binary, the AI can pass `data_base64` instead. The MCP client asks the backend to extract text first; raw base64 is not sent to model providers.

---

## Example 6: Run an advisor debate

**What you say to your AI:**

> "Ask the advisors to debate whether we should migrate our backend from monolithic REST to distributed gRPC. Get The Skeptic and The Strategist to participate."

**What happens behind the scenes:**

The AI identifies that you want a multi-round debate among specific personas, mapping "The Skeptic" to `skeptic` and "The Strategist" to `strategist`. It calls `advisor_debate`:

```json
{
  "tool": "advisor_debate",
  "input": {
    "question": "Should we migrate our backend from monolithic REST to distributed gRPC?",
    "persona_ids": ["skeptic", "strategist"],
    "max_rounds": 3
  }
}
```

The MCP server coordinates with the backend to run the structured debate and returns the full transcript and verdict:

Advisor debate is intended for prompts with real tradeoffs or disagreement. For direct factual or creative prompts, use `model_chat` or `council_deliberate` instead.

```json
{
  "conversation_id": "deb-555",
  "status": "completed",
  "rounds": [
    {
      "round": 1,
      "messages": [
        {
          "persona": "skeptic",
          "content": "gRPC adds massive complexity. You have to compile proto files, debug HTTP/2 issues, lose simple browser tooling (like curl), and handle complex load balancing. Our team isn't ready for distributed system failures."
        },
        {
          "persona": "strategist",
          "content": "While those operational hurdles are real, the long-term leverage is immense. Strongly-typed contracts prevent frontend-backend sync bugs, binary serialization dramatically cuts network costs, and streaming supports real-time features easily."
        }
      ]
    }
  ],
  "verdict": {
    "summary": "The Skeptic highlighted operational friction while the Strategist focused on contract safety and scale.",
    "verdict": "DO NOT MIGRATE YET. Keep the monolithic REST API but adopt strict schema validation (like Pydantic/Zod) to address contract safety without gRPC operational complexity.",
    "action_plan": [
      "1. Implement OpenAPI/Pydantic schemas on existing REST endpoints.",
      "2. Conduct a small gRPC prototype for service-to-service communication only if REST latency becomes a bottleneck."
    ]
  }
}
```

**What your AI presents to you:**

The AI synthesizes a clear narrative of the debate, highlighting the opening stances, the consensus reached (or split), and the final actionable verdict.

---

## Example 7: Customize and reset a persona

**What you say to your AI:**

> "Customize the Skeptic persona to make him extremely security-focused, then let me see his details."

**What happens behind the scenes:**

The AI updates the system prompt and description of the `skeptic` persona:

```json
{
  "tool": "personas",
  "input": {
    "action": "update",
    "persona_id": "skeptic",
    "role": "Security Auditor & Skeptic",
    "description": "Examines proposals exclusively through the lens of OWASP Top 10, data leaks, and access controls.",
    "system_prompt": "You are The Security Skeptic. Your single goal is to find security vulnerabilities, threat models, and architectural risks in every proposal."
  }
}
```

Response:
```json
{
  "id": "skeptic",
  "name": "The Skeptic",
  "role": "Security Auditor & Skeptic",
  "description": "Examines proposals exclusively...",
  "avatar_emoji": "🔍",
  "is_customized": true
}
```

The AI then confirms:
> "I've customized The Skeptic to be a Security Auditor & Skeptic. His system prompt has been updated to focus entirely on vulnerabilities, threat models, and OWASP. He will now critique all future debates from this perspective."

**To reset him later, you can say:**
> "Reset the Skeptic persona back to normal."

Behind the scenes:
```json
{
  "tool": "personas",
  "input": {
    "action": "reset",
    "persona_id": "skeptic"
  }
}
```

---

## Example 8: Configure advisors globally

**What you say to your AI:**

> "Configure the advisors to use deepseek-v4-flash-free as the default model, running 4 rounds."

**What happens behind the scenes:**

The AI calls `advisor_settings`:

```json
{
  "tool": "advisor_settings",
  "input": {
    "action": "update",
    "default_model": "custom:deepseek-v4-flash-free",
    "default_rounds": 4
  }
}
```

Response:
```json
{
  "status": "updated",
  "fields": ["advisor_default_model", "advisor_default_rounds"]
}
```

**What your AI presents to you:**

> "All advisor debates will now default to running 4 rounds of back-and-forth statements using the custom `deepseek-v4-flash-free` model. Ready to start a debate session?"

---

## Example 9: Save an advisor preset (MCP)

**What you say to your AI:**

> "Save my current advisor lineup as a preset called Startup Panel with The Skeptic, Pragmatist, and Innovator on gpt-4.1."

**What happens behind the scenes:**

The AI calls `advisor_settings` with action `save_preset`:

```json
{
  "tool": "advisor_settings",
  "input": {
    "action": "save_preset",
    "preset_name": "Startup Panel",
    "persona_ids": ["skeptic", "pragmatist", "innovator"],
    "default_model": "openai:gpt-4.1",
    "is_default": true
  }
}
```

**What your AI presents to you:**

> "Saved Startup Panel as your default advisor preset. Open Advisor Setup to load it on future debates."

See `skills/the-ai-counsel-api/SKILL.md` §18 for the full preset schema (max 20 presets; saves personas/models/rounds/search — not the debate question). REST fallback: `PUT /api/settings` with `advisor_presets`.
