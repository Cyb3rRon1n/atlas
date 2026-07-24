# Atlas

**AI-powered operations platform for self-hosted infrastructure.**

Atlas is an extensible infrastructure intelligence platform designed to discover, understand, and eventually automate self-hosted environments.

The goal of Atlas is to provide a unified operational layer for homelabs, private clouds, and self-managed infrastructure by combining:

- Infrastructure discovery
- Operational inventory
- Service awareness
- Event-driven architecture
- Persistent infrastructure knowledge
- Plugin-based extensibility
- AI-assisted operations

Atlas is currently under active development.

---

# Project Status

Atlas is currently progressing through its foundation and intelligence architecture phases.

## Implemented

✅ Python CLI application  
✅ Configuration management  
✅ Hardware discovery  
✅ Operating system discovery  
✅ Storage discovery  
✅ Network discovery  
✅ Inventory generation  
✅ Reporting engine  
✅ Docker discovery  
✅ Service detection  
✅ Docker Compose analysis  
✅ Proxmox integration foundation  
✅ Plugin architecture  
✅ Event-driven system  
✅ Persistent operational history  
✅ Knowledge storage layer  

## In Development

🚧 AI analysis engine  
🚧 Infrastructure recommendations  
🚧 Automated operational workflows  
🚧 Agent-based capabilities  
🚧 Advanced monitoring integrations  

---

# Architecture

Atlas is built around a modular event-driven architecture.


The architecture is designed to allow new capabilities to be added without rewriting the core system.

---

# Features

## Infrastructure Discovery

Atlas can inspect the host system and generate infrastructure inventory.

Current discovery includes:

- Host information
- Operating system details
- CPU information
- Memory statistics
- Storage devices
- Filesystem usage
- Network information

Run:

atlas discover

Inventory is saved to:

inventory/generated/system-inventory.yaml

---

# Inventory System

Atlas stores discovered infrastructure information as structured inventory.

Inventory provides the foundation for:

- Reporting
- Analysis
- Change detection
- Future automation

---

# Docker Integration

Atlas can inspect Docker environments.

Run:

atlas docker

Provides visibility into:

- Containers
- Images
- Container status
- Container IDs

Atlas can also identify known services.

Run:

atlas services

Example:

Atlas Services

Service:
Plex

Category:
Media

Container:
plex

Status:
running

---

# Docker Compose Analysis

Atlas can analyze Docker Compose files.

Run:

atlas compose

Provides visibility into:

- Services
- Images
- Ports
- Volumes

---

# Proxmox Integration

Atlas includes the foundation for Proxmox infrastructure discovery.

Run:

atlas proxmox scan

Current capabilities:

- Proxmox configuration support
- Connection framework
- Node discovery foundation

Future versions will expand this into:

- Virtual machine inventory
- Container inventory
- Resource monitoring
- Change detection

---

# Plugin Architecture

Atlas uses a plugin-based design.

Plugins extend Atlas with:

- Discovery providers
- Infrastructure integrations
- Monitoring systems
- Automation capabilities

Current plugin system supports:

- Plugin registration
- Plugin discovery
- Plugin initialization
- Plugin events

Run:

atlas plugins

Example output:

Atlas Plugins

Docker (0.1.0)

---

# Event System

Atlas uses an internal event bus.

Events allow components to communicate without direct dependencies.

Example:

Discovery Engine

        |

        v

atlas.discovery.completed

        |

        v

Knowledge Store

Current events include:

- atlas.plugin.loaded
- atlas.discovery.completed

---

# Operational Memory

Atlas maintains persistent operational history.

Run:

atlas history

Atlas stores:

- Plugin events
- Discovery events
- Operational data
- Infrastructure observations

This memory layer provides the foundation for future intelligence features.

---

# CLI Reference

Current commands:

## Status

atlas status

Displays Atlas status information.

---

## Doctor

atlas doctor

Runs Atlas health checks.

---

## Configuration

atlas config

Displays Atlas configuration.

---

## Discovery

atlas discover

Discovers infrastructure information and generates inventory.

---

## Reporting

atlas report

Generates infrastructure reports.

---

## Docker

atlas docker

Displays Docker container information.

---

## Services

atlas services

Detects known infrastructure services.

---

## Compose

atlas compose

Analyzes Docker Compose files.

---

## Plugins

atlas plugins

Displays registered Atlas plugins.

---

## History

atlas history

Displays operational event history.

---

# Installation

Clone the repository:

git clone https://github.com/Cyb3rRon1n/atlas.git

Enter the project:

cd atlas

Create a virtual environment:

python -m venv .venv

Activate:

source .venv/bin/activate

Install:

pip install -e .

Verify:

atlas version

---

# Configuration

Atlas uses YAML configuration.

Example:

atlas:
  name: sentinel

discovery:
  hardware: true
  storage: true
  network: true

inventory:
  directory: inventory/generated

---

# Development

Atlas development follows incremental milestones.

Current development priorities:

1. Core architecture
2. Discovery framework
3. Plugin ecosystem
4. Operational memory
5. Intelligence layer
6. Automation framework

---

# Documentation

Additional documentation:

docs/

- ATLAS_CONTEXT.md
- ARCHITECTURE.md
- HOMELAB_DESIGN.md
- SERVICE_CATALOG.md
- AI_BOOTSTRAP.md

---

# Contributing

Contributions, ideas, and discussions are welcome.

Please read:

CONTRIBUTING.md

before submitting changes.

---

# Security

Security issues should be reported according to:

SECURITY.md

---

# License

Atlas is released under the MIT License.

See:

LICENSE

---

# Vision

Atlas aims to become an intelligent operations platform for self-hosted infrastructure.

The long-term vision:

Observe

|

Understand

|

Recommend

|

Automate

|

Optimize

Atlas is being built as a foundation for infrastructure intelligence.
