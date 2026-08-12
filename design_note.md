# Part 2 — A scalable, governed data layer (design)

Here is my proposed design for the problem addressing the different concerns:

---

# 1. Defining Data Ownership

The **original service** that owns a piece of data remains the **source of truth**. The AI system consumes a **governed projection** of that data.

**e.g** ledger service owns the balance and Transactions data and the behavioural analytics are owned by Product Analytics Platform.

---

# 2. Fetching Data

For this section I have selected a hybrid approach for fetching **live data** and **customer analytics**

## Live Customer Data using a Governed Data Access Layer:

- This layer wont own any of the records but will handle services like authentication, authorization and field filtering etc.
- The access layer provides a governed way for AI workloads to consume that data.
- I do understand that this adds a single point of failure in our system so we will focus more on making it highly available by distributing responsibilites using a load balancer to multiple access layers (servers).

```
                    ┌─────────────┐
                    │ Support AI  │
                    └──────┬──────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ Governed Customer Data │
              │     Access Layer       │
              └────────────┬───────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Account/Ledger│   │ Card Service  │   │  KYC Service  │
└───────┬───────┘   └───────────────┘   └───────────────┘
        │
        ▼
┌────────────────────┐
│ Transaction Service│
└────────────────────┘
```

## Customer Analytics using a data warehouse:

- Will have access to historical data so won't need to call a single service many many times

```
┌──────────┐
│ Services │
└────┬─────┘
     │
     v
┌──────────────┐
│ Data Pipeline│
└──────┬───────┘
       │
       v
┌───────────┐
│ Warehouse │
└─────┬─────┘
      │
      v
┌────────────────────────────┐
│ Analytics / ML / Reporting │
└────────────────────────────┘
```

## What I avoided here and why?

### Direct Calls to every owning service from the AI Service

- Coupling increases as the service grows and so it wont be easier to scale.

### Adding a central customer service

- It can become the owner of data or at least become heavily responsible for business logic around it making it the source of truth in a way.

### An event driven architecture

- It can contain old snapshots of data and can be a major risk where live data is important

---

# 3. making Sure unauthorized data is never accessed

- I have gone for multi-layer defense system here since security is a critical component in this

## 3.1 Layer 1: ID Authentication

- The system first identifies the requester through an authenticated identity. The customer ID supplied in the request is treated as a resource being accessed, not as proof of authorization. The system uses the authenticated identity to determine which customer records that requester is allowed to access.

## 3.2 Layer 2: Authorization at the Data Access Layer

- Before fetching any data, the access layer checks whether the authenticated principal is authorized to access the requested customer and data. This prevents a caller from changing the customer ID and accessing someone else's information.

## 3.3 Layer 3: Field Level Permissions

- Authorization also applies to individual fields. The access layer exposes only the fields required for the specific AI use case through a defined contract. Sensitive fields such as CNIC and IBAN are excluded, so the AI cannot read or return data it was never given access to.

## 3.4 Layer 4: Restriciting AI from calling arbitrary APIs.

- The AI will not have unrestricted access to backend APIs. Instead, it will use a small set of typed tools such as get_card_status or get_recent_transactions. Each tool is implemented by the application and calls the governed data access layer, where customer authorization and field-level access checks are enforced.

## Audit Logs for observability

- Audit log of every field access (who, which customer, which fields, when)

```
LLM decides what information it needs
        ↓
Application decides what operations are allowed
        ↓
Data access layer enforces authorization
        ↓
Owning service returns the approved data
```

---

# 4. What happens if a service is slow or down mid answer?

- We will set a timeout for the calls being made
- Use tags to label fields in the context of the question. And if any `critical field` is missing for the question we will not generate a partial answer and could ask the user to wait or escalate their query.
- We can also implement retries here with a cap

---

# 5. Data Residency

This is something I am unsure about since the data storage is subject to our laws as well.

But what we can do here is try to keep as much as data within our layer and only forward relevant fields to any external system (LLM) for processing

---

# 6. Adding New Signals Later on

A new service can add data to the gateway by defining its data contract and access rules. The gateway then checks the data classification and approved fields before making them available to an AI use case. This lets new signals be added without giving the AI direct access to new services.

```
New owning service
       ↓
Define contract
       ↓
Expose approved field
       ↓
Add adapter
       ↓
Register signal
       ↓
AI use case can request it
```

# 7. Scaling our System

- We can add versioning in our API contracts and the AI service explicitly asks for the contract version it supports.
- We will make our AI service stateless, so it does not depend on data stored inside one particular server. So we can run multiple copies.
- Implement caching for behavioural data
- shared data access layer will also prevent every AI use case from building its own service integrations, authorization, and field filtering
- Also upgrade our servers when needed

---

# Deliberate Deferrals

I am deliberately deferring:

1. Complex vector/database infrastructure since they are not needed for the data-access problem.
2. Letting the AI service discover APIs since it makes it harder to govern.

---

# Trade offs

The main trade-off in this design is choosing live fan-out over a materialized read model for balance, card, and KYC data. Calling each owning service on every request keeps the data always fresh and avoids a second copy that could drift from the source of truth, but it means every reply pays the latency and availability cost of the slowest service involved, which is exactly why the access layer needs timeouts, retries, and to run as multiple load-balanced instances instead of a single server. I made the opposite call for behavioural analytics: it goes through a batch warehouse pipeline instead of a live call, which means that data can be a few hours stale. I'm fine with that because behavioural signals don't need to be as fresh as a balance, and it keeps the access layer from having to fan out to yet another live service on every request. Restricting the AI to a small set of typed tools instead of letting it query the access layer freely is also a cost I'm accepting on purpose: it means every new AI use case that needs a new shape of data requires a new tool and a new contract, rather than being able to just ask for whatever it needs, but that inflexibility is what makes authorization and auditing enforceable in the first place. Finally, the four-layer authorization approach costs more to build and test than a single filtering step, but I'd rather pay that cost upfront than have the system's only protection against leaking a CNIC or IBAN depend on one single layer.
