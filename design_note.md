# Part 2: A scalable, governed data layer (design)

Here is my proposed design for the problem addressing the different concerns:

---

# 1. Defining Data Ownership

The **original service** that owns a piece of data remains the **source of truth**. The AI service will consume a **governed view** of that data through explicit contracts.

**e.g** A ledger service owns the balance and Transactions data and the behavioural analytics are owned by Product Analytics Platform.

---

# 2. Fetching Data

For this section I have selected a hybrid approach for fetching **live data** and **customer analytics**

## Live Customer Data using a Governed Data Access Layer:

- This layer wont own any of the records but will handle services like authentication, authorization and field filtering etc.
- The access layer provides a governed way for our AI service to consume that data.
- I do understand that this adds central dependency in our system, so we will focus on keeping the access layer highly available by distributing requests (load) using a load balancer to multiple access layers (servers).

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
│Account service│   │ Card Service  │   │  KYC Service  │
└───────┬───────┘   └───────────────┘   └───────────────┘
        │
        ▼
Transaction Data
```

## Customer Analytics using an event driven data warehouse:

- Will store the historical data so won't need to call a single service many many times (saves computation cost by avoiding repeatedly querying services for analysis).
- Data will reach the store through an event-driven pipeline
- Data being stale for a short period of time does not have a major impact here

```
              Domain Services
                    │
                    ▼
          Event-Driven Data Pipeline
                    │
                    ▼
               ┌──────────┐
               │ Warehouse│
               └────┬─────┘
                    │
          ┌─────────┴─────────┐
          │                   │
          ▼                   ▼
 Analytics Data        Analytics / ML /
 Access Layer            Reporting
          │
          ▼
      Support AI
```

## What I deliberately avoided here and why?

### Direct Calls to every owning service from the AI Service

- Coupling increases as the service grows and so it wont be easier to scale.

### Adding a central customer service

- A central customer service can gradually become a new system of record or accumulate domain-specific business logic.

### An event driven architecture for live data

- For live financial data because it may introduce inconsistencies.

### Using a CDC pipeline for Analytics

- Although CDC can provide reliable change capture, but it reads the raw table, restricted fields and all, and pushes the job of filtering out CNIC/IBAN/PAN downstream into the pipeline instead of stopping it at the source and filtering is owned by the platform team running the connector, not by the service that actually knows which fields are sensitive.

---

# 3. making Sure unauthorized data is never accessed

- I have gone for multi-layer defense system here which will be supported by the built-in authorization of the owning services

## 3.1 Layer 1: ID Authentication

- The system first identifies the requester through an authenticated identity. The customer ID supplied in the request is treated as a resource being accessed, not as proof of authorization. The system uses the authenticated identity to determine which customer records that requester is allowed to access.

## 3.2 Layer 2: Authorization at the Data Access Layer

- Before fetching any data, the access layer checks whether the authenticated principal is authorized to access the requested customer and data. This prevents a caller from changing the customer ID and accessing someone else's information.

## 3.3 Layer 3: Field Level Permissions

- Authorization also applies to individual fields. The access layer exposes only the fields required for the specific AI use case through a defined contract. Sensitive fields such as CNIC and IBAN are excluded, so the AI cannot read or return data it was never given access to.

## 3.4 Layer 4: Restricting AI from calling arbitrary APIs.

- The AI will not have unrestricted access to backend APIs. Instead, it will use a small set of typed tools such as get_card_status or get_recent_transactions. Each tool will be implemented by the application and call the governed data access layer, where customer authorization and field-level access checks are enforced.

```
LLM decides what information it needs
        ↓
Application decides what operations are allowed
        ↓
Data access layer enforces authorization
        ↓
Owning service returns the approved data
```

## Maintaining Logs for tracking

- Audit log of every field access (who, which customer, which fields, when)
- written to a separate access-controlled logging system e.g a separate data base or something like amazon CloudTrail

---

# 4. What happens if a service is slow or down mid answer?

- We will set a timeout for the calls being made
- Use tags to label fields in the context of the question. And if any `critical field` is missing for the question we will not generate a partial answer and could ask the user to wait or escalate their query else we could generate a partial answer from the data we have collected without inventing facts for whatever's missing.
- Implement retries here with a cap

---

# 5. Data Residency

I would keep financial customer data within the required residency boundary and avoid sending raw financial or identity data to external systems. Where an external LLM is used, only the minimum required fields would be sent, and only if the provider and deployment model satisfy the compliance requirements (data storage is subject to our laws as well)

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

- Add versioning in our API contracts and the AI service explicitly asks for the contract version it supports.
- Make our AI service stateless, so it does not depend on data stored inside one particular server. So we can run multiple copies.
- Implement caching for behavioural data
- Shared data access layer also prevents every AI use case from building its own service integrations, authorization, and field filtering
- Horizontally scaling stateless AI and access-layer instances behind load balancers
- Use connection pooling and bounded downstream concurrency so increased AI traffic does not overwhelm the owning services.

---

# Deliberate Deferrals

I am deliberately deferring:

1. Complex vector/database infrastructure since they are not needed for the data-access problem.
2. Letting the AI service discover APIs since it makes it harder to govern.

---

# Trade offs

The biggest trade-off is calling each service live instead of storing a copy of the data ourselves. Calling each owning service on every request keeps the data always fresh and avoids a second copy that could drift from the source of truth, but it means every reply pays the latency and availability cost of the slowest service involved, which is exactly why the access layer needs timeouts, retries, and to run as multiple load-balanced instances instead of a single server.

I made the opposite call for behavioural analytics: it goes through a batch warehouse pipeline instead of a live call, which means that data can be a few hours stale. I'm fine with that because behavioural signals don't need to be as fresh as a balance, and it keeps the access layer from having to fan out to yet another live service on every request.

Restricting the AI to a small set of typed tools instead of letting it query the access layer freely is also a cost I'm accepting on purpose: it means every new AI use case that needs a new shape of data requires a new tool and a new contract, rather than being able to just ask for whatever it needs, but that inflexibility is what makes authorization and auditing enforceable in the first place.

Finally, the four-layer authorization approach costs more to build and test than a single filtering step, but I'd rather pay that cost upfront than have the system's only protection against leaking a CNIC or IBAN depend on one single layer.
