# SEO — agent context

> Maintained by: Marketing Manager. Read by: Marketing Manager
> (primary), Technical Writer (read-only — for documentation pages
> targeting informational keywords), UI Developer (read-only — for
> `<title>`, meta description, structured-data hints per page).
>
> Purpose: target keyword clusters per audience, search intent,
> competitive landscape, and per-page keyword mapping. The page
> itself does not carry its target keyword in source — it carries
> the rendered copy. The mapping lives here so that one change of
> intent does not require a multi-file refactor.

## Conventions

- Group keywords into **clusters** (3–8 related queries) rather
  than tracking each keyword individually.
- Tag each cluster with **intent**: `informational` / `transactional`
  / `navigational` / `commercial`.
- Map **one** cluster per page. Multiple-cluster pages don't rank
  for any of them.

## Keyword clusters — OSS audience

### Cluster: <!-- name, e.g. "PKI ops pain" -->
- **Intent**: informational
- **Queries**:
  - <!-- "how to rotate a CRL" -->
  - <!-- "managing a CA hierarchy at scale" -->
- **Mapped page**: <!-- e.g. /blog/crl-rotation-pitfalls -->
- **Competitors ranking**: <!-- top 3 + the angle they take -->
- **Our angle**: <!-- the gap we're playing into — what they don't
  cover, what we cover better -->

## Keyword clusters — Enterprise audience

### Cluster: <!-- name, e.g. "enterprise PKI compliance" -->
- **Intent**: commercial
- **Queries**:
  - <!-- "PKI for SOC 2" -->
  - <!-- "audit-ready certificate authority" -->
- **Mapped page**: <!-- e.g. /security or /pricing -->
- **Competitors ranking**: ...
- **Our angle**: ...

## Page → cluster index

| Page | Cluster | Last reviewed |
|---|---|---|
| <!-- /blog/crl-rotation-pitfalls --> | <!-- PKI ops pain --> | <!-- YYYY-MM-DD --> |

## Watch list

<!-- Keywords or competitor moves we are monitoring but not yet
     targeting. Helps decide what to take on next without
     rediscovering the landscape each quarter. -->
