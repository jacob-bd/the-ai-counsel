"""Default system prompts for The AI Counsel."""

RESPONSE_LANGUAGE_DEFAULT = "English"

VALID_RESPONSE_LANGUAGES = (
    "English",
    "Spanish",
    "French",
    "German",
    "Italian",
    "Portuguese",
    "Dutch",
    "Polish",
    "Russian",
    "Ukrainian",
    "Arabic",
    "Hebrew",
    "Hindi",
    "Japanese",
    "Korean",
    "Chinese (Simplified)",
    "Chinese (Traditional)",
    "Greek",
)


def apply_response_language(content: str, language: str | None = None) -> str:
    """Prepend a response-language instruction to a model prompt."""
    lang = (language or RESPONSE_LANGUAGE_DEFAULT).strip() or RESPONSE_LANGUAGE_DEFAULT
    if lang == RESPONSE_LANGUAGE_DEFAULT:
        return content
    instruction = (
        f"You MUST respond in {lang}. "
        f"Use {lang} for all prose, critiques, synthesis, and explanations."
    )
    return f"{instruction}\n\n{content}"


STAGE1_PROMPT_DEFAULT = """You are a helpful AI assistant.
{search_context_block}
Question: {user_query}"""

STAGE1_SEARCH_CONTEXT_TEMPLATE = """You have access to the following real-time web search results.
You MUST use this information to answer the question, even if it contradicts your internal knowledge cutoff.
Do not say "I cannot access real-time information" or "My knowledge is limited to..." because you have the search results right here.

Search Results:
{search_context}
"""

STAGE2_PROMPT_DEFAULT = """You are evaluating different responses to the following question:

Question: {user_query}

{search_context_block}
Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...

FINAL RANKING:
1. Response A
2. Response B

Rank ONLY the responses listed above. Do not invent labels that were not provided.

Now provide your evaluation and ranking:"""

STAGE3_PROMPT_DEFAULT = """You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

{search_context_block}
STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""

TITLE_PROMPT_DEFAULT = """Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

QUERY_PROMPT_DEFAULT = """Extract the core search terms from the following question to use in a web search engine.
Return ONLY the search query, with no quotes, punctuation, or conversational text.

Question: {user_query}

Search Query:"""

STAGE1_ROUND_N_FREEFORM_PROMPT = """You are refining your answer in Round {round_number} of a multi-round deliberation.

Original question: {user_query}
{search_context_block}

Previous round's best synthesis:
{previous_synthesis}

Previous round's ranking results:
{previous_rankings_summary}

Consider the previous round's insights. You may:
- Strengthen arguments that were ranked highly
- Challenge weaknesses identified in the rankings
- Offer new perspectives not yet considered
- Refine your position based on peer feedback

Provide your revised, improved response."""

STAGE1_ROUND_N_CHAT_RANKING_PROMPT = """You are refining your answer in Round {round_number} of a multi-round deliberation.

Original question: {user_query}
{search_context_block}

Previous round's ranking results (how your peers ranked the responses):
{previous_rankings_summary}

Your previous response was ranked #{your_rank} out of {total_models} models.
{rank_feedback}

Provide your revised, improved response."""

STAGE3_FINAL_FREEFORM_PROMPT = """You are the Chairman delivering the FINAL verdict after {total_rounds} rounds of deliberation.

Original question: {user_query}

{search_context_block}

Previous round's synthesis:
{previous_synthesis}

This final round's individual responses:
{stage1_text}

This final round's peer rankings:
{stage2_text}

Deliver the definitive answer. Explain how the deliberation evolved across rounds and why the final position is strongest. Declare the winning perspective."""

# --- Phase 2: Claim & Paragraph Critique Mode Prompts ---

CLAIM_EXTRACTION_PROMPT = """Decompose each response into individual claims (specific, falsifiable statements). Each claim should be one clear assertion.

{responses_text}

Respond with ONLY valid JSON (no other text):
```json
{{
  "Response A": [
    {{"id": "A1", "claim": "specific falsifiable statement"}},
    {{"id": "A2", "claim": "another statement"}}
  ],
  "Response B": [
    {{"id": "B1", "claim": "statement"}}
  ]
}}
```"""

STAGE2_PARAGRAPH_PROMPT = """You are evaluating responses to: {user_query}

{search_context_block}
{responses_text}

Paragraphs are pre-numbered as [Para 1], [Para 2], etc. Rate each: STRONG, WEAK, or FLAWED.

Respond with valid JSON followed by your ranking:

```json
[
  {{"response": "Response A", "paragraph": 1, "verdict": "strong", "comment": "reason"}},
  {{"response": "Response A", "paragraph": 2, "verdict": "flawed", "comment": "reason"}}
]
```

FINAL RANKING:
1. Response A
2. Response B"""

STAGE2_CLAIM_PROMPT = """You are evaluating responses to: {user_query}

{search_context_block}
{responses_text}

These canonical claims have been extracted. Rate each one:
{canonical_claims_text}

Respond with valid JSON followed by your ranking:

```json
{{
  "A1": {{"verdict": "strong", "reason": "one sentence"}},
  "A2": {{"verdict": "flawed", "reason": "one sentence"}}
}}
```

FINAL RANKING:
1. Response A
2. Response B"""

STAGE1_ROUND_N_CLAIM_PROMPT = """You are refining your answer in Round {round_number} of a multi-round deliberation.

Original question: {user_query}
{search_context_block}

YOUR PREVIOUS RESPONSE had these claims evaluated by peers:
{own_claims_with_critiques}

TOP-RATED CLAIMS FROM OTHER MODELS (for your consideration):
{top_claims_from_others}

Your task:
- Fix or drop claims rated FLAWED
- Strengthen claims rated WEAK
- Keep claims rated STRONG
- Consider incorporating top-rated claims from others if they improve your argument
- You may add new claims not previously considered

Provide your revised, improved response."""

STAGE1_ROUND_N_PARAGRAPH_PROMPT = """You are refining your answer in Round {round_number} of a multi-round deliberation.

Original question: {user_query}
{search_context_block}

YOUR PREVIOUS RESPONSE had these paragraphs evaluated by peers:
{own_paragraphs_with_critiques}

TOP-RATED PARAGRAPHS FROM OTHER MODELS (for your consideration):
{top_paragraphs_from_others}

Your task:
- Rewrite paragraphs rated FLAWED
- Strengthen paragraphs rated WEAK
- Keep paragraphs rated STRONG
- Consider incorporating strong points from others

Provide your revised, improved response."""

STAGE3_FINAL_CLAIM_PROMPT = """You are the Chairman delivering the FINAL verdict after {total_rounds} rounds of deliberation.

Original question: {user_query}

{search_context_block}

Claim evolution across rounds:
{claim_evolution_summary}

Final round responses:
{stage1_text}

Final round rankings:
{stage2_text}

Deliver the definitive answer. Explain which claims survived scrutiny, which were dropped, and which were adopted across models. Declare the winner."""

STAGE4_CORRECTED_DRAFT_PROMPT = """You are the Chairman of an LLM Council. After {total_rounds} rounds of deliberation, the council has produced a final verdict with specific claim corrections.

Your task: produce a CORRECTED DRAFT of the original document that incorporates ALL corrections, fixes flawed claims, strengthens weak claims, and applies every recommendation from the verdict.

ORIGINAL DOCUMENT:
{original_text}

COUNCIL'S FINAL VERDICT (with claim corrections):
{verdict_text}

Instructions:
- Rewrite the original document incorporating every correction identified in the verdict
- Fix all claims marked FLAWED (replace with the corrected versions if provided)
- Strengthen all claims marked WEAK with proper qualification or sourcing
- Incorporate adopted improvements from the deliberation
- Preserve the original document's structure, tone, and intent
- Mark significant changes with [REVISED] or [NEW] inline so the author can see what changed
- Do NOT add commentary or meta-discussion — produce only the corrected document"""
