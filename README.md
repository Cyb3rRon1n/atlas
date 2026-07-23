# Atlas

> **Know Your Homelab.**
>
> *An AI-powered platform that discovers, documents, understands, and assists in managing self-hosted infrastructure.*

---

## Vision

Modern homelabs are powerful—but they quickly become difficult to maintain.

Virtual machines multiply. Docker containers accumulate. Storage expands. Documentation becomes outdated. Six months later, it's hard to remember why something was configured a certain way or whether changing it will break another service.

Atlas was created to solve that problem.

Rather than acting as another dashboard or a collection of Docker Compose files, Atlas aims to become an AI-assisted operations platform that continuously builds an understanding of your infrastructure.

The long-term goal is simple:

> **Build a homelab that understands itself.**

---

# What is Atlas?

Atlas is an open-source platform designed to help self-hosted environments become easier to understand, maintain, and improve.

Atlas combines:

* Infrastructure discovery
* Documentation generation
* Inventory management
* Operational guidance
* Resource analysis
* AI-assisted administration
* Safe automation workflows

Instead of asking:

> "How do I install another container?"

Atlas helps answer questions like:

* What hardware do I actually have?
* Which containers are using the most resources?
* Can my server handle another workload?
* Why is Jellyfin buffering?
* What changed since last week?
* Which services depend on this container?
* What should I back up before making this change?

---

# Project Goals

## Discover

Automatically inspect your environment.

* Hardware
* Storage
* Network
* Docker
* Virtual machines
* Services
* Applications

---

## Document

Keep documentation synchronized with reality.

* Infrastructure inventory
* Hardware profiles
* Network topology
* Storage layout
* Service catalog
* Architectural decisions
* Change history

---

## Understand

Build a complete picture of your infrastructure.

Atlas should understand:

* What exists
* Why it exists
* How it connects
* What depends on it
* How healthy it is

---

## Assist

Provide context-aware recommendations before changes are made.

Examples include:

* Resource planning
* Capacity forecasting
* Service deployment guidance
* Troubleshooting assistance
* Performance optimization
* Backup planning

---

## Automate

Only after the environment is understood.

Automation in Atlas follows a simple philosophy:

> **Understand first. Automate carefully.**

---

# Core Principles

## Documentation First

Infrastructure that isn't documented becomes difficult to maintain.

Atlas treats documentation as part of the infrastructure—not an afterthought.

---

## Explain Every Recommendation

Atlas should always explain:

* Why a recommendation is being made
* Expected impact
* Potential risks
* Rollback considerations

---

## Human Approval

Atlas is designed to assist operators—not replace them.

Destructive or high-impact actions should require explicit approval.

---

## Local-First

Whenever practical, Atlas is designed to work with locally hosted services and models.

Examples include:

* Ollama
* Local LLMs
* Self-hosted monitoring
* Self-hosted media services

---

## Modular Architecture

Users should be able to adopt Atlas incrementally.

Use only the components you need.

---

# Planned Architecture

```text
                    Physical Server
                           │
                    Proxmox VE
                           │
                  Ubuntu Server VM
                           │
                    Docker Compose
                           │
      ┌───────────────┬───────────────┬───────────────┐
      │               │               │
   AI Platform     Media Stack     Monitoring
      │               │               │
   Ollama         Jellyfin        Grafana
   Open WebUI     Sonarr          Prometheus
   n8n            Radarr          Uptime Kuma
   Atlas          Prowlarr
                  Bazarr
                  Jellyseerr
```

---

# Roadmap

## Phase 1 — Foundation

* Project structure
* Documentation
* CLI framework
* Repository setup

---

## Phase 2 — Discovery

* Hardware discovery
* Docker discovery
* Storage discovery
* Network discovery
* Inventory generation

---

## Phase 3 — Intelligence

* Knowledge base
* Infrastructure understanding
* Documentation synchronization
* Resource recommendations

---

## Phase 4 — Operations

* Docker integrations
* Proxmox integrations
* Monitoring integrations
* Safe operational workflows

---

## Phase 5 — AI Assistance

* Local AI integration
* Context-aware conversations
* Deployment planning
* Troubleshooting assistance

---

## Phase 6 — Automation

* Scheduled maintenance
* Health reporting
* Capacity forecasting
* Documentation updates
* Approved operational tasks

---

# Planned Features

## Infrastructure

* Proxmox
* Docker
* Docker Compose
* Linux
* Networking
* Storage

## AI

* Local language models
* Retrieval-Augmented Generation (RAG)
* Multi-agent architecture
* Knowledge graph
* Context-aware assistance

## Media

* Jellyfin
* Sonarr
* Radarr
* Prowlarr
* Bazarr
* Jellyseerr

## Monitoring

* Grafana
* Prometheus
* Uptime Kuma

## Documentation

* Markdown generation
* Inventory synchronization
* Architecture diagrams
* Decision logs
* Change history

---

# Project Status

Atlas is currently in early development.

The initial focus is building a solid foundation:

* Repository structure
* Documentation
* Discovery engine
* CLI framework
* Inventory system

Automation and AI-driven operations will be added incrementally as the platform matures.

---

# Contributing

Contributions are welcome.

Whether you're interested in:

* Python development
* Documentation
* Infrastructure
* Docker
* Proxmox
* Monitoring
* AI
* Testing

there are many ways to help shape Atlas.

See `CONTRIBUTING.md` for guidelines.

---

# Philosophy

Atlas is built around one question:

> **"Does this help the platform understand the infrastructure better?"**

If the answer is yes, it probably belongs.

If not, it should be reconsidered.

---

# License

Atlas is released under the MIT License.

See the `LICENSE` file for details.

---

# The Journey

Atlas started as a personal homelab project.

It evolved into a vision for a platform that combines infrastructure management, documentation, and local AI into a single, cohesive system.

If Atlas helps someone build a homelab that is easier to understand, maintain, and enjoy, then it has achieved its purpose.

---

**Welcome to Atlas.**

**Know Your Homelab.**
