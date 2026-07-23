A good roadmap should communicate direction without locking you into rigid deadlines. I'd organize it around milestones and capabilities rather than dates.

# Atlas Roadmap

> **Know Your Homelab.**

This roadmap outlines the long-term vision for Atlas. Features and priorities may evolve as the project grows, but the guiding philosophy remains the same:

> **Understand first. Document continuously. Automate carefully.**

---

# Vision

Atlas aims to become an AI-powered operations platform for self-hosted infrastructure.

Rather than acting as another dashboard, Atlas continuously discovers, documents, understands, and assists in managing your homelab through safe, explainable AI.

---

# Guiding Principles

Every feature should support at least one of these goals:

* Improve infrastructure understanding
* Keep documentation synchronized
* Reduce operational complexity
* Protect user data
* Enable safe automation
* Remain local-first whenever practical

---

# Version Roadmap

## v0.1.0 — Foundation

**Goal:** Build the project's foundation and developer experience.

### Repository

* Project structure
* Documentation framework
* Branding
* GitHub templates
* MkDocs documentation site

### CLI

* `atlas --help`
* `atlas version`
* `atlas config`
* Command framework

### Documentation

* Architecture overview
* Installation guides
* Project philosophy
* Initial runbooks

**Status:** 🚧 In Progress

---

## v0.2.0 — Discovery Engine

**Goal:** Atlas understands the machine.

### Hardware Discovery

* CPU
* Memory
* GPU
* Motherboard
* Storage devices
* Operating system

### Docker Discovery

* Containers
* Images
* Networks
* Volumes
* Compose projects

### Inventory

Automatically generate:

* Hardware inventory
* Service inventory
* Storage inventory
* Network inventory

### Reports

Generate:

* Infrastructure report
* Health report
* Resource summary

---

## v0.3.0 — Infrastructure Intelligence

**Goal:** Atlas begins reasoning about the environment.

### Knowledge

* Infrastructure graph
* Service relationships
* Dependency mapping
* Historical inventory

### Recommendations

* Capacity planning
* Resource optimization
* Configuration review
* Storage planning

### Documentation

* Detect configuration drift
* Update inventories
* Suggest documentation improvements

---

## v0.4.0 — Platform Integrations

**Goal:** Connect Atlas to core infrastructure.

### Proxmox

* VM discovery
* Resource usage
* Snapshots
* Cluster awareness

### Docker

* Health monitoring
* Compose management
* Container inspection
* Update planning

### Monitoring

* Prometheus
* Grafana
* Uptime Kuma

---

## v0.5.0 — AI Platform

**Goal:** Atlas becomes an AI assistant.

### Local AI

* Ollama integration
* Open WebUI integration
* Local models

### Knowledge Base

* Retrieval-Augmented Generation (RAG)
* Documentation search
* Historical context

### AI Features

* Ask questions about infrastructure
* Explain system state
* Generate deployment plans
* Troubleshooting assistance

---

## v0.6.0 — Media Platform

**Goal:** Deep integration with common homelab services.

### Media

* Jellyfin
* Sonarr
* Radarr
* Prowlarr
* Bazarr
* Jellyseerr

### Storage

* Library analysis
* Capacity forecasting
* Organization recommendations

---

## v0.7.0 — Operations

**Goal:** Atlas assists with day-to-day administration.

### Workflows

* Deployment planning
* Backup verification
* Update planning
* Maintenance scheduling

### Reports

* Daily health summaries
* Weekly optimization reports
* Monthly capacity reports

---

## v0.8.0 — Safe Automation

**Goal:** Atlas performs approved tasks.

Examples:

* Restart unhealthy containers
* Create snapshots
* Update documentation
* Rotate logs
* Verify backups
* Execute maintenance workflows

Every action should be:

* Explainable
* Logged
* Reversible whenever possible
* Subject to configurable approval policies

---

## v1.0.0 — Atlas Platform

The first stable release.

### Core Features

* Infrastructure discovery
* Inventory management
* Documentation generation
* AI knowledge base
* Safe operational workflows
* Local-first AI integration
* Monitoring integrations
* Media stack support

---

# Future Vision

Potential future capabilities include:

## Infrastructure

* Multi-node Proxmox clusters
* Kubernetes
* NAS platforms
* Cloud integrations
* Hybrid infrastructure

## AI

* Multi-agent orchestration
* Knowledge graph
* Predictive maintenance
* Capacity forecasting
* Root cause analysis

## Home Automation

* Home Assistant integration
* Energy monitoring
* Smart device awareness

## Security

* Configuration auditing
* Vulnerability awareness
* Security recommendations
* Compliance reporting

## Plugins

A plugin system allowing Atlas to support additional services without modifying the core platform.

Examples:

* Immich
* Frigate
* Paperless-ngx
* Nextcloud
* AdGuard Home
* Pi-hole
* Gitea
* Forgejo

---

# Development Philosophy

Atlas follows an incremental approach.

Each release should leave the platform:

* More understandable
* Better documented
* Easier to maintain
* More reliable

New features should improve the operator's understanding before introducing additional automation.

---

# Success Criteria

Atlas succeeds when it helps users answer questions like:

* What is running?
* Why is it running?
* How is it connected?
* What changed recently?
* What resources are available?
* What can I safely deploy next?
* What should I fix first?
* How can I improve my homelab?

---

# Long-Term Mission

Atlas is not intended to replace system administrators.

Its purpose is to make self-hosted infrastructure easier to understand, operate, and evolve.

The long-term vision is an AI-assisted platform that continuously builds and maintains an accurate understanding of the infrastructure it serves—helping users make informed decisions with confidence.

---

## Current Milestone

**Sprint 1 — Foundation**

Current priorities:

* Repository setup
* Documentation
* CLI framework
* Project branding
* Development tooling
* Initial release preparation

**Target Release:** `v0.1.0-alpha`
