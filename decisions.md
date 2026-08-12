# DECISIONS.md

## 1. Overall architecture

- `knowledge.md` is split based on `##` headings since the Markdown headings already represent semantic boundaries in this knowledge base using the `chunker.py` file.
- `build_router_options()` drops the preamble chunk (the H1 title and intro blockquote above the first `##`, which has no `section` key and isn't an addressable topic)
- `llm.py` does two separate LLM calls: `classify()` (routes the question to an intent + optional section) and `generate()` (writes the customer-facing reply from only the approved context for that intent).
- `rules.py` enforces the safe/restricted data split and does a keyword-based pre-check for direct requests for restricted fields.

---

### Code flow

                    Customer ID + Question
                              |
                              v
                 Check restricted request
                              |
                   +----------+----------+
                   |                     |
                 YES                    NO
                   |                     |
                   v                     v
          Refuse + escalate         LLM Classifier
                                           |
             +-----------------------------+-----------------------------+
             |                             |                             |
             v                             v                             v
      knowledge_section              account_data                    unclear
             |                             |                             |
             v                             v                             v
       Select KB section          Get safe customer data       Get safe customer data
             |                             |                             |
             v                             v                             v
        LLM Generator                 LLM Generator               LLM Generator
             |                             |                             |
             v                             v                             v
          Reply                       Reply + no escalation      Reply + escalation


                              LLM Classifier
                                    |
                                    v
                              out_of_scope
                                    |
                                    v
                            Fixed decline response
                                No generation
                                No escalation

---

## 2. Retrieval strategy: LLM router over enumerated sections, not embeddings

- **Decision:** since we have a really small semantically distributed knowledge base, I let the LLM pick the matching `section id` from a list rather than building a vector DB.
- **Alternatives considered:** embedding-based retrieval.
- **Why:** For a small knowledge base it would increase the computation cost and add unwanted complexities

---

## 3. Restricted data never enters the LLM context, structurally

- **Decision:** `customers.json` splits each customer into `safe` and `restricted`. Every
  function that talks to the LLM does not have access to the restricted fields

**Alternatives considered:**
- Pass the full customer record to the model and instruct it not to repeat restricted
  fields. Rejected. This makes safety dependent on the model following an instruction
  correctly, every time, under any phrasing of the question, including adversarial
  phrasing.
- Redact restricted fields with a placeholder string before sending, in case the model
  needs to know they exist. Rejected as unnecessary. Nothing in the approved use cases
  requires the model to know a restricted field exists, only that it can't share it.

- **Why this way:** if the field is never in the prompt, there's nothing for the model to
  leak, whether through a bug in my prompt, a jailbreak attempt in the customer's question, or
  plain hallucination.

---

## 4. Catching restricited calls by a deterministic keyword rule, before the LLM sees the question at all

- **Decision:** `is_restricted_request()` in `rules.py` checks the raw question against a
  keyword list (cnic, iban, card number, cvv, etc.) and short-circuits straight to a refusal
  and a human-escalation flag, before `classify()` is ever called.

**Alternatives considered:**
- Do both: keyword rule _and_ let it flow into the classifier as a backstop. Considered, but
  once the keyword rule fires, there is nothing left for the classifier to safely add, since
  the reply is already decided.

- **Why this way:** as a simple trigger to prevent an LLM call since it is not needed here

---

## 5. Four-way intent classification: `knowledge_section`, `account_data`, `unclear`, `out_of_scope`

- **Decision:** every question that isn't a restricted-field request gets classified into
  exactly one of four buckets, each with its own generation prompt and its own escalation
  rule.

**Alternatives considered:**
- Two buckets: "answerable" and "not answerable." Rejected, but this makes it too broad. It collapses "this
  is a normal question, just outside our product" (interest rates) with "this is on-topic
  and a human should look at it" (duplicate Netflix charge), and those need opposite
  behavior: one is a plain decline, the other is an acknowledgment plus a handoff.
- A single "escalate" bucket instead of splitting `account_data` from `unclear`. Rejected.
  Most account-data questions (balance, card status) have a clean, fully-approved answer
  with zero ambiguity. Routing those to a human would be needless friction for the large
  majority of ordinary questions.

**Trade-off I'm accepting:** 
- The routing decision itself is blind to account data. `classify()`
  only ever sees the question text and the six section titles, never `safe_data`, so whether a
  question gets routed to `unclear` depends on how it's phrased, not on what's actually in the
  account. "I was charged twice for Netflix" (cust_002) routes to `unclear` because the wording
  implies a problem, not because the router looked at the transaction list and spotted the
  duplicate itself.

- This doesn't mean the duplicate goes unacknowledged, though. Once routed, `generate()` for
  `unclear` (and `account_data`) receives that customer's full `safe_data`, including the
  transaction list, so the reply can and does cite the two literal PKR 250 Netflix entries. What
  it's told not to do is diagnose why there are two, or promise a refund. So the split is real
  but narrower than it first looks: the _routing_ decision is phrasing-based, the _answer_ is
  still grounded in the actual data, just constrained to acknowledging facts rather than
  resolving them.

---

## 6. Answer-vs-escalate is a property of the intent, not a separate decision pass

- **Decision:** The issue is only esclated based on the intent i.e `unclear` always escalates.
  `knowledge_section` and `account_data` never do (their answers are fully grounded in
  approved content or literal safe fields, so there's nothing for a human to adjudicate).
  `out_of_scope` declines without escalating, since it's explicitly not a servicing matter.
  `restricted_request` and `unknown_customer` always escalate, decided at the point they're
  detected rather than through this function.

- **Alternatives considered:** a general-purpose risk score or confidence threshold on every
  answer, but since the brief asks for a clear boundary between "answer confidently" and "a human should take this," and intent already draws that
  boundary cleanly, since I designed the categories around it. A separate scoring layer would
  add a threshold to tune.

---

## 7. Fail-safe checks to not completely trust the LLM's output

- **Decision:** `classify()` can fail in two different ways, and both are handled the same
  way (fall back to `unclear`, never guess): the response isn't valid JSON, or the response is
  valid JSON that isn't a dict with a recognized `intent`, or has a `section_id` that's out of
  range or not an integer. `_validate_classifier_result()` does that second check explicitly.

- **Why the second check exists:** in review, I found that the original version only wrapped
  `json.loads()` in a try/except. A response that parsed as valid JSON but wasn't shaped the
  way the code expected (missing key, wrong type, unrecognized intent string) crashed
  downstream instead of being caught, which would have taken down the whole batch run on one
  bad model response. I added explicit validation of the parsed object's shape (dict, valid
  intent, section_id in range) inside the same try block that already handled the parse
  failure, so both failure modes now fail the same safe way.

---

## 8. Two LLM calls (classify, then generate), never one combined call

- **Decision:** routing and answering are separate calls, and the generation call only ever
  receives the context appropriate to the intent that was already decided (approved content
  alone, or safe account data alone, never both at once).

- **Alternatives considered:** a single call that both decides how to answer and answers in
  one pass. A combined call would need to see knowledge content and account data
  simultaneously to make the routing decision, which creates a blending risk: the model inferring or diagnosing by mixing "what policy says" with "what I
  notice about this account," which is the behavior `GENERATE_PROMPT_UNCLEAR` explicitly
  forbids elsewhere. Keeping the calls separate keeps each one's job single-purpose and its
  inputs auditable.

---

## 9. Language matching, and treating the customer's question as untrusted input

- **Decision:** the system prompt instructs the model to reply in the same language and
  script the customer used (including Roman Urdu, without switching to native script unless
  the customer did), and explicitly tells the model never to follow instructions embedded
  inside the customer's question.

- **Why:** `cust_002 | mera card freeze kaise karun?` is in the test set specifically to check
  this. A support bot that replies in English to a Roman Urdu question may confuse the customer.

---

## 10. Some Assumptions/Gaps

- **Cross-referencing account state with policies:** e.g if a user asks how they can freeze their even if their card is already frozen this question would be answered from the knowledge without checking the actual status of their card. I assumed here that the customer just wants to know a specific piece of information and nothing more.

If a user also asks why their card is not working it would not be mapped to their data to check if their card is forzen or not instead it only goes to the knowledge section.

- **No deterministic guard for an abnormal account state:** `cust_003` has `accountStatus: "restricted"` and `kyc: "pending"`. Whether that question gets `account_data` or `unclear` (escalate) is currently left entirely to the classifier's judgment.

- **No conversation memory across turns.** Each question in `questions.txt` is independent
  and the brief scopes this as a single-turn Q&A exercise. Multi-turn context (e.g., "what
  about the other one" referring to a previous answer) is out of scope here.

- **The classifier sees only section titles, not section content:** With six short,
  clearly-named sections this carries enough signal for routing. It won't scale as the
  knowledge base grows or if sections start overlapping in topic; at that point I'd want the
  router seeing content, or real embedding-based retrieval feeding it, instead of a title
  list.

- **Handling requests which may ask for both safe and restricted data in one prompt:** A partial-answer version would need to detect _which part_ is restricted and answer only the rest, which is a much harder guarantee to make safely so it just flags entire request right now as restricted.

- **Handling vague Quesitons:** A partial-answer version would need to detect _which part_ is restricted and answer only the rest, which is a much harder guarantee to make safely so it just flags entire request right now as restricted.
