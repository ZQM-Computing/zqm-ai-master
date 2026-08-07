# The Void AI Orchestration System — Pricing and Packaging

## Packages

### Starter
- 1 node license
- Local inference only
- Email support
- Includes: The Void app, Ollama, Meilisearch, Docker stack
- Excludes: multi-tenant control plane, billing gateway

### Business
- Up to 5 node licenses
- Multi-tenant isolation enabled
- Billing gateway ready
- Priority support
- Includes: Starter + tenant manager, branding layer, observability

### Enterprise
- Custom node count
- Private registry and release channel
- SLA-backed support and indemnification
- Onboarding and training
- Includes: Business + hardened security review, deployment automation

## Billing Integration
- Billing gateway stub is included at `/billing/*`
- Stripe/PayPal adapter config is environment-driven
- Subscription lifecycle: trial -> active -> past_due -> canceled
- Metered usage events are emitted for inference and document processing

## Reseller Terms
- Resale requires written agreement from ZQM Computing LLC
- Customer data ownership remains with the customer
- Platform uptime commitment is defined by the support agreement tier
