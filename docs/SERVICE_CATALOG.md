# Atlas Service Catalog

## Overview

This document defines the applications and services that Atlas should understand.

The purpose of the service catalog is to provide context beyond container names.

A container is not just:

```text
sonarr
```

It represents:

```text
Application:
Sonarr

Category:
Media Automation

Purpose:
Television library management

Dependencies:
Storage, download client, indexers
```

Atlas uses this knowledge to understand relationships between infrastructure components.

---

# Service Classification

Services are grouped into categories:

```text
Media

Automation

Infrastructure

Monitoring

Security

AI

Utilities
```

---

# Media Services

---

# Jellyfin

## Category

Media Streaming

## Purpose

Jellyfin is the primary media streaming platform.

It provides:

* Movie playback
* TV playback
* Music playback
* User libraries
* Streaming clients

---

## Infrastructure Requirements

Requires:

* Media storage
* Network access
* Database/config storage

Recommended:

* Hardware accelerated transcoding
* GPU access

---

## Dependencies

```text
Jellyfin

|

Media Library

|

Storage System
```

---

## Atlas Considerations

Monitor:

* CPU usage
* GPU utilization
* Transcoding activity
* Library size
* Network throughput

Potential recommendations:

* Enable hardware acceleration
* Increase resources during high usage
* Optimize media formats

---

# Sonarr

## Category

Media Automation

## Purpose

Sonarr manages television series.

Responsibilities:

* Track shows
* Monitor releases
* Organize files
* Maintain libraries

---

## Dependencies

```text
Sonarr

|

Indexer

|

Download Client

|

Storage

|

Jellyfin
```

---

## Atlas Considerations

Monitor:

* API connectivity
* Download paths
* Storage permissions
* Library organization

---

# Radarr

## Category

Media Automation

## Purpose

Radarr manages movie libraries.

Responsibilities:

* Track movies
* Monitor releases
* Organize files

---

## Dependencies

```text
Radarr

|

Indexer

|

Download Client

|

Storage

|

Jellyfin
```

---

## Atlas Considerations

Monitor:

* Storage capacity
* File organization
* Import failures

---

# Prowlarr

## Category

Indexer Management

## Purpose

Prowlarr manages indexer configuration.

Responsibilities:

* Centralize indexers
* Provide connections to automation services

---

## Dependencies

```text
Prowlarr

|

Sonarr

|

Radarr
```

---

## Atlas Considerations

Monitor:

* Connection status
* API health
* Indexer availability

---

# Bazarr

## Category

Media Automation

## Purpose

Bazarr manages subtitles.

Responsibilities:

* Subtitle searching
* Language management
* Synchronization

---

## Dependencies

```text
Bazarr

|

Sonarr

|

Radarr

|

Media Library
```

---

## Atlas Considerations

Monitor:

* Subtitle provider health
* Missing subtitles
* Permissions

---

# Jellyseerr

## Category

Media Requests

## Purpose

Jellyseerr provides user requests.

Responsibilities:

* User requests
* Approval workflows
* Integration with automation services

---

## Dependencies

```text
Jellyseerr

|

Sonarr

|

Radarr

|

Jellyfin
```

---

## Atlas Considerations

Monitor:

* API connections
* Request failures
* User access

---

# Download Services

Future supported services:

Examples:

```text
qBittorrent

SABnzbd

NZBGet
```

---

## Purpose

Handle media acquisition.

---

## Dependencies

```text
Automation Services

|

Download Client

|

Storage
```

---

## Atlas Considerations

Monitor:

* Disk usage
* Download speed
* Failed downloads
* Permissions

---

# Infrastructure Services

---

# Docker

## Category

Container Runtime

## Purpose

Provides application isolation and deployment.

---

## Atlas Responsibilities

Monitor:

* Running containers
* Images
* Volumes
* Networks
* Resource usage

---

# Proxmox

## Category

Virtualization Platform

## Purpose

Provides:

* Virtual machines
* LXC containers
* Storage management
* Networking

---

## Atlas Responsibilities

Monitor:

* Nodes
* VMs
* LXC containers
* CPU allocation
* Memory allocation
* Storage pools

---

# Portainer

## Category

Container Management

## Purpose

Provides a graphical Docker management interface.

---

## Atlas Considerations

Monitor:

* Container state
* Stack deployments
* User access

---

# Monitoring Services

Future services:

```text
Prometheus

Grafana

Loki

Node Exporter
```

---

# Prometheus

## Category

Monitoring

## Purpose

Metrics collection system.

Collects:

* CPU usage
* Memory usage
* Storage metrics
* Application metrics

---

# Grafana

## Category

Visualization

## Purpose

Creates dashboards from monitoring data.

---

# AI Services

Future category.

Possible services:

```text
OpenClaw

Local LLM

Vector Database

Agent Runtime
```

---

# AI Integration Model

Future architecture:

```text
Applications

      |

Metrics + Logs + State

      |

Atlas

      |

AI Agent

      |

Recommendations
```

---

# Service Dependency Map

The primary media environment:

```text
                 Jellyfin

                    |

              Media Library

                    |

               Storage


Sonarr ---------

                |

Radarr -----------> Download Client

                |

Prowlarr --------


                    |

                Bazarr


Jellyseerr

      |

      |

User Requests
```

---

# Service Health Expectations

Every service should eventually provide:

## Identity

```text
Name

Category

Purpose
```

---

## Runtime

```text
Container

Image

Version

Status
```

---

## Resources

```text
CPU

Memory

Storage

Network
```

---

## Dependencies

```text
Requires

Provides

Connected Services
```

---

# Atlas AI Reasoning Examples

## Example 1

Question:

"Why is Jellyfin slow?"

Atlas evaluates:

```text
Jellyfin

+

CPU

+

GPU

+

Network

+

Storage

+

Active Streams
```

---

## Example 2

Question:

"Can I add another service?"

Atlas evaluates:

```text
Available Memory

+

CPU Capacity

+

Storage

+

Network

+

Existing Workloads
```

---

## Example 3

Question:

"Can Jellyfin move?"

Atlas evaluates:

```text
GPU Availability

+

Storage Access

+

Network

+

Resource Availability
```

---

# Catalog Maintenance

This file should grow as the homelab grows.

New services should include:

* Purpose
* Category
* Dependencies
* Resource requirements
* Monitoring requirements
* AI considerations

---

# Current Supported Services

```text
✓ Jellyfin

✓ Sonarr

✓ Radarr

✓ Prowlarr

✓ Bazarr

✓ Jellyseerr

✓ Docker

✓ Proxmox (planned)

✓ Monitoring stack (planned)

✓ AI stack (planned)
```

---

# Atlas Goal

Atlas should not merely know that a service exists.

Atlas should understand:

* Why it exists
* What it needs
* What depends on it
* How it affects the rest of the environment
