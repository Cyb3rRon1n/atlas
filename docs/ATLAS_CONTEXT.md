# Atlas Context

## Project Overview

Atlas is an AI-assisted homelab infrastructure management platform.

The purpose of Atlas is to provide a central intelligence layer that can understand, monitor, document, optimize, and eventually assist with managing a complete homelab environment.

Atlas is designed around the principle:

> Observe first. Understand second. Recommend third. Automate with approval.

Atlas should never blindly modify infrastructure. It should gather information, build context, explain decisions, and require appropriate approval before destructive actions.

---

# Project Vision

The long-term goal is an AI-powered homelab operator capable of:

* Understanding hardware capabilities
* Monitoring infrastructure health
* Managing containerized applications
* Assisting with deployments
* Optimizing resource allocation
* Maintaining documentation automatically
* Helping troubleshoot issues
* Providing recommendations based on actual infrastructure state

The primary target environment is:

* Proxmox virtualization
* Docker-based application workloads
* Jellyfin media server ecosystem
* *arr automation stack
* AI-assisted infrastructure management

---

# Current Development Status

## Atlas Version

Current milestone:

```
v0.1 Foundation
```

Completed components:

* GitHub project structure
* CLI framework
* Configuration system
* Hardware discovery
* Inventory generation
* Reporting engine
* Health checks
* Docker awareness
* Service discovery
* Docker Compose awareness

---

# Current Architecture

```
                 Atlas

                   |
                   |

              CLI Interface

                   |

        -----------------------

        Configuration Layer

        Discovery Layer

        Health Layer

        Docker Layer

        Compose Layer

        Service Layer

        Inventory Layer

        Reporting Layer

        -----------------------

                   |

             AI Knowledge Base
```

---

# Repository Structure

Current intended layout:

```
atlas/

├── atlas/
│
├── cli/
│
├── config/
│
├── discovery/
│
├── docker/
│
├── compose/
│
├── services/
│
├── health/
│
├── inventory/
│
├── reporting/
│
└── docs/

```

---

# Development Philosophy

Atlas follows these principles:

## 1. Infrastructure Awareness

Atlas must understand:

* Hardware
* Operating system
* Storage
* Network
* Containers
* Applications
* Dependencies

---

## 2. Documentation First

Every major discovery or change should create documentation.

Atlas should maintain knowledge files such as:

* Hardware inventory
* Service inventory
* Network layout
* Application relationships
* Configuration state

---

## 3. Safe Automation

Atlas should:

* Observe before changing
* Explain before acting
* Backup before modifying
* Request approval for risky operations

---

# Target Homelab Environment

## Virtualization

Primary virtualization platform:

```
Proxmox VE
```

Expected usage:

* Virtual machines
* LXC containers
* Storage management
* Resource allocation

---

# Container Platform

Primary container runtime:

```
Docker
```

Potential future support:

* Podman
* Kubernetes
* Proxmox LXC

---

# Planned Application Stack

## Media Server

Primary:

```
Jellyfin
```

Purpose:

* Media streaming
* Hardware accelerated transcoding
* User media access

---

## Media Automation Stack

Planned services:

```
Sonarr
```

TV automation

```
Radarr
```

Movie automation

```
Prowlarr
```

Indexer management

```
Bazarr
```

Subtitle automation

```
Jellyseerr
```

Media request management

---

# AI Management Goals

The future AI layer should be able to:

## Understand

* Available CPU resources
* Available memory
* GPU capabilities
* Storage capacity
* Network topology
* Running applications

---

## Assist With

* Building containers
* Creating Compose files
* Configuring services
* Troubleshooting issues
* Finding missing dependencies
* Optimizing resources

---

## Manage

Potential future capabilities:

* Start/stop services
* Update containers
* Monitor failures
* Recommend upgrades
* Maintain documentation

All actions should have safety controls.

---

# Current Atlas Commands

Expected commands:

```
atlas discover
```

Collect system information.

---

```
atlas config
```

Display configuration.

---

```
atlas report
```

Generate infrastructure reports.

---

```
atlas doctor
```

Run health checks.

---

```
atlas docker
```

Display Docker containers.

---

```
atlas services
```

Identify known homelab applications.

---

```
atlas compose
```

Analyze Docker Compose projects.

---

# Future Development Roadmap

## Phase 1 — Foundation

Completed:

* CLI
* Configuration
* Discovery
* Inventory
* Reporting
* Health
* Docker awareness

---

## Phase 2 — Infrastructure Intelligence

Next:

* Proxmox integration
* VM discovery
* LXC discovery
* Storage pool awareness
* Network mapping

---

## Phase 3 — AI Control Plane

Planned:

* AI agent integration
* Knowledge retrieval
* Infrastructure reasoning
* Recommendation engine
* Natural language management

---

## Phase 4 — Automation

Planned:

* Compose generation
* Deployment assistance
* Container lifecycle management
* Resource optimization

---

# AI Bootstrap Information

When an AI assistant loads Atlas context, it should understand:

Atlas is not simply a container manager.

Atlas is an infrastructure intelligence system.

Its responsibility is:

1. Understand the environment.
2. Maintain accurate knowledge.
3. Provide recommendations.
4. Assist the operator.
5. Preserve system stability.

---

# Current Build Position

Current completed milestone:

```
Atlas Foundation Layer

Observation:
COMPLETE

Knowledge Storage:
COMPLETE

Reporting:
COMPLETE

Container Awareness:
COMPLETE

Application Awareness:
COMPLETE
```

Next planned milestone:

```
Proxmox Integration Layer
```

This will allow Atlas to understand the actual homelab virtualization environment.
