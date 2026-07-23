# Atlas Homelab Design

## Overview

This document describes the intended physical and logical design of the homelab environment managed by Atlas.

The goal is to build a reliable, scalable, AI-assisted infrastructure platform capable of running:

* Media services
* Automation services
* Self-hosted applications
* AI workloads
* Infrastructure management tools

Atlas should eventually understand this entire environment.

---

# Design Goals

The homelab should prioritize:

## Reliability

The system should:

* Recover from failures
* Maintain backups
* Document changes
* Avoid unnecessary complexity

---

## Scalability

The design should allow:

* Additional storage
* Additional compute nodes
* More services
* Future virtualization expansion

---

## Automation

The environment should support:

* Infrastructure as code
* Docker Compose deployments
* Automated monitoring
* AI-assisted operations

---

# High-Level Architecture

Target architecture:

```text id="m7j1yk"
                    User

                     |

              AI Assistant

                     |

                   Atlas

                     |

                 Proxmox VE

                     |

        --------------------------------

        Virtual Machines

        LXC Containers

        Storage Pools

        Networks

        --------------------------------

                     |

               Application Layer

                     |

        --------------------------------

        Jellyfin

        Sonarr

        Radarr

        Prowlarr

        Bazarr

        Jellyseerr

        --------------------------------
```

---

# Virtualization Strategy

Primary virtualization platform:

```text id="2qkz9w"
Proxmox VE
```

Proxmox provides:

* Virtual machines
* LXC containers
* Resource management
* Snapshots
* Backup integration
* Cluster capability

---

# Proxmox Layout

Target structure:

```text id="b9k0ve"
Proxmox Node

|

├── VM: Docker Host

│
├── VM: AI Services

│
├── LXC: Monitoring

│
├── LXC: Infrastructure Tools

│
└── Storage Containers
```

---

# Docker Host Design

The primary application host should run:

```text id="2j9s1s"
Docker

    |

    |

Docker Compose

    |

    |

Application Services
```

Recommended separation:

```text id="ytqj85"
docker-host

├── media-stack

├── monitoring-stack

├── utility-stack

└── ai-stack
```

---

# Media Stack Design

Primary objective:

Provide a complete self-hosted media environment.

## Core Services

```text id="6sp7po"
Jellyfin
```

Media streaming server

---

```text id="5p33rj"
Sonarr
```

TV automation

---

```text id="y9xqca"
Radarr
```

Movie automation

---

```text id="0c2l5s"
Prowlarr
```

Indexer management

---

```text id="4xqlwj"
Bazarr
```

Subtitle management

---

```text id="5hk3on"
Jellyseerr
```

Media request system

---

# Media Data Flow

Expected flow:

```text id="v5g6y1"
Request

 |

Jellyseerr

 |

Sonarr/Radarr

 |

Indexer

 |

Download Client

 |

Media Library

 |

Jellyfin

 |

User
```

---

# Storage Design

Storage should be separated by purpose.

Example:

```text id="t5g1t7"
Storage Pool

|

├── media

│   ├── movies

│   ├── tv

│   └── music


├── downloads

│   ├── incomplete

│   └── complete


├── backups


└── application-data
```

---

# Storage Principles

## Media Storage

Large capacity.

Optimized for:

* Read performance
* Reliability
* Expansion

---

## Application Storage

Contains:

* Databases
* Configuration
* Metadata

Should have:

* Backups
* Snapshots

---

## Backup Storage

Separate from primary storage.

Should protect against:

* Accidental deletion
* Configuration loss
* Hardware failure

---

# GPU Strategy

Jellyfin benefits from hardware acceleration.

Future considerations:

* GPU passthrough
* Intel Quick Sync
* NVIDIA NVENC
* AMD hardware encoding

Atlas should discover:

```text id="43w90q"
GPU

|

Driver

|

Available acceleration

|

Container access
```

---

# Network Design

Target network:

```text id="6ey6l5"
Internet

   |

Router

   |

Firewall

   |

Switch

   |

Homelab Network

   |

Proxmox

   |

Services
```

---

# Network Segmentation

Future VLAN design:

```text id="5otz07"
VLAN 10

Management


VLAN 20

Servers


VLAN 30

IoT


VLAN 40

Guest
```

---

# Security Design

The homelab should follow:

## Minimal Exposure

Only expose required services.

---

## Internal Services

Prefer:

* VPN access
* Reverse proxy
* Authentication

---

## Secrets

Store separately:

* Passwords
* Tokens
* API keys

Never commit secrets to Git.

---

# Monitoring Strategy

Future monitoring stack:

Possible services:

* Prometheus
* Grafana
* Loki
* Node Exporter

Atlas should consume:

* Metrics
* Alerts
* Logs

---

# AI Management Model

Atlas should understand the environment through:

```text id="u8m4ka"
Hardware Inventory

+

Proxmox Inventory

+

Docker Inventory

+

Service Inventory

+

Monitoring Data

=

Infrastructure Knowledge
```

---

# Resource Optimization Goals

Atlas should eventually answer:

Examples:

"Where should Jellyfin run?"

Consider:

* CPU availability
* GPU access
* Memory
* Storage location
* Network bandwidth

---

"Why is media buffering?"

Analyze:

* Container resources
* Transcoding
* Network
* Storage performance

---

"Can I add another service?"

Evaluate:

* Available RAM
* CPU capacity
* Storage space
* Current workload

---

# Deployment Philosophy

Every application should have:

```text id="2v1m5x"
service-name/

├── docker-compose.yml

├── .env.example

├── README.md

├── backups/

└── notes/
```

---

# Current Implementation Status

Completed:

```text id="h4n0ng"
Atlas Foundation

✓ Documentation
✓ CLI
✓ Discovery
✓ Inventory
✓ Docker Awareness
✓ Service Awareness
```

---

# Next Development Phase

## Proxmox Integration

Atlas will add:

* Proxmox API connection
* Node discovery
* VM discovery
* LXC discovery
* Resource monitoring
* Storage awareness

---

# Final Goal

The finished environment should become:

```text id="f4qk3x"
Human Goal

      |

      |

AI Assistant

      |

      |

Atlas

      |

      |

Infrastructure

      |

      |

Self-Healing Homelab
```

Atlas exists to make the homelab easier to understand, safer to operate, and easier to expand.
