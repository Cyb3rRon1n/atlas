# Atlas Architecture

## Overview

Atlas is an AI-assisted infrastructure intelligence platform designed to understand, monitor, document, and assist with managing homelab environments.

The architecture follows a layered approach:

```text
Hardware
   |
   |
Virtualization
   |
   |
Operating System
   |
   |
Container Runtime
   |
   |
Applications
   |
   |
AI Intelligence Layer
```

Each layer provides information to the layer above it.

---

# Design Philosophy

Atlas is built around five principles:

## 1. Awareness Before Automation

Atlas must understand the environment before attempting to manage it.

The information flow is:

```text
Discover
   |
Inventory
   |
Analyze
   |
Recommend
   |
Approve
   |
Execute
   |
Document
```

---

## 2. Single Source of Truth

Atlas maintains infrastructure knowledge through:

```text
docs/
inventory/
reports/
configuration files
```

Generated information should always be reproducible.

---

## 3. Modular Architecture

Each capability should exist as an independent module.

Example:

```text
atlas/

├── discovery
├── inventory
├── health
├── docker
├── compose
├── services
├── reporting
└── future_ai
```

Modules communicate through defined interfaces.

---

# Current System Architecture

```text
                     Atlas CLI

                        |

                Command Interface

                        |

        --------------------------------

        Configuration Layer

        Discovery Layer

        Health Layer

        Docker Layer

        Compose Layer

        Service Layer

        Inventory Layer

        Reporting Layer

        --------------------------------

                        |

                Knowledge Storage
```

---

# Component Breakdown

# CLI Layer

Purpose:

Provide operator interaction.

Examples:

```bash
atlas discover
atlas doctor
atlas report
atlas docker
atlas services
atlas compose
```

Responsibilities:

* Accept commands
* Display results
* Trigger modules

---

# Configuration Layer

Location:

```text
atlas/config/
```

Purpose:

Provide centralized configuration.

Current configuration:

```yaml
atlas:
  name: sentinel

discovery:
  hardware: true
  storage: true
  network: true

inventory:
  directory: inventory/generated
```

Future configuration:

```yaml
ai:
  enabled: true

proxmox:
  enabled: true

docker:
  enabled: true
```

---

# Discovery Layer

Location:

```text
atlas/discovery/
```

Purpose:

Collect raw infrastructure information.

Current modules:

```text
system.py

hardware.py

storage.py

network.py
```

Information collected:

* Hostname
* Operating system
* Kernel
* CPU
* Memory
* Storage
* Network information

---

# Inventory Layer

Location:

```text
atlas/inventory/
```

Purpose:

Store Atlas knowledge.

Flow:

```text
Discovery Data

      |

Inventory Generator

      |

system-inventory.yaml
```

Example:

```yaml
hostname: sentinel

hardware:
  cpu:
    cores: 16

  memory:
    total: 64GB
```

Inventory is the foundation of AI reasoning.

---

# Reporting Layer

Location:

```text
atlas/reporting/
```

Purpose:

Convert infrastructure information into readable documentation.

Example:

```bash
atlas report
```

Produces:

```text
reports/

└── atlas-report.md
```

Reports are intended for:

* Human review
* AI context
* Troubleshooting
* Historical tracking

---

# Health Layer

Location:

```text
atlas/health/
```

Purpose:

Evaluate infrastructure condition.

Current checks:

* Python environment
* Memory
* Storage
* Docker availability
* Inventory availability

Future checks:

* Disk health
* Network latency
* Container health
* Backup status
* Security posture

---

# Container Intelligence Layer

Location:

```text
atlas/docker/
```

Purpose:

Understand container environments.

Current capabilities:

* Detect Docker
* List containers
* Identify status
* Identify images

Future:

* Container lifecycle
* Logs
* Updates
* Resource optimization

---

# Compose Intelligence Layer

Location:

```text
atlas/compose/
```

Purpose:

Understand application stacks.

Example:

```text
Compose Project

      |

      |

Services

      |

      |

Containers

      |

      |

Volumes
```

This allows Atlas to understand relationships.

Example:

```text
Media Stack

Jellyfin
 |
Storage

Sonarr
 |
Download Client
 |
Media Library
```

---

# Service Intelligence Layer

Location:

```text
atlas/services/
```

Purpose:

Convert containers into meaningful applications.

Example:

Raw:

```text
container:
lscr.io/linuxserver/sonarr
```

Becomes:

```text
Service:

Sonarr

Category:

Media Automation

Purpose:

TV Management
```

This provides application context to AI.

---

# Future Proxmox Layer

Planned:

```text
atlas/proxmox/
```

Purpose:

Understand virtualization infrastructure.

Capabilities:

* Connect to Proxmox API
* Discover nodes
* Discover VMs
* Discover LXC containers
* Monitor resources
* Understand storage pools

Architecture:

```text
Proxmox Cluster

        |

        |

Atlas Proxmox Module

        |

        |

Infrastructure Inventory
```

---

# Future AI Control Plane

Planned architecture:

```text
                    AI Agent

                       |

              Reasoning Engine

                       |

             Knowledge Retrieval

                       |

              Atlas Inventory

                       |

        Infrastructure Modules

                       |

       Proxmox / Docker / Services
```

---

# AI Knowledge Flow

The AI should reason from:

```text
Hardware Data

+

Virtualization Data

+

Container Data

+

Application Data

+

Historical Reports
```

Example reasoning:

Input:

```text
Jellyfin buffering
```

AI analyzes:

```text
Jellyfin container

+

CPU usage

+

GPU availability

+

Network throughput

+

Storage performance
```

Output:

```text
Recommendation:

Enable GPU transcoding.
Current CPU load suggests software transcoding.
```

---

# Future Automation Architecture

Automation should follow:

```text
Request

   |

Analyze

   |

Generate Plan

   |

Explain Plan

   |

Approval

   |

Execute

   |

Verify

   |

Document
```

---

# Security Architecture

Atlas should follow:

## Principle of Least Privilege

Avoid unnecessary permissions.

---

## Secrets Separation

Never store:

* Passwords
* API keys
* Tokens

in Git.

---

## Approval-Based Actions

Destructive operations require confirmation.

Examples:

Require approval:

* Delete containers
* Remove storage
* Modify networking
* Destroy virtual machines

---

# Target Homelab Architecture

Expected final environment:

```text
                 User

                  |

              AI Assistant

                  |

                Atlas

                  |

              Proxmox

                  |

        -----------------

        VM / LXC Layer

        -----------------

                  |

              Docker Host

                  |

        -----------------

        Jellyfin

        Sonarr

        Radarr

        Prowlarr

        Bazarr

        Jellyseerr

        -----------------
```

---

# Current Development Milestone

Completed:

```text
Foundation Layer

✓ CLI
✓ Configuration
✓ Discovery
✓ Inventory
✓ Reporting
✓ Health
✓ Docker
✓ Compose
✓ Service Awareness
```

Next:

```text
Proxmox Integration Layer
```

After Proxmox:

```text
AI Control Plane
```

---

# Atlas Long-Term Goal

Atlas becomes the intelligence layer between the administrator and the infrastructure.

The operator describes goals.

Atlas understands the environment.

Atlas recommends solutions.

Atlas assists implementation.

Atlas maintains knowledge.
